"""NETCONF backend implementation."""

import os
import xml.etree.ElementTree as ET
from ipaddress import IPv4Interface

try:
    from ncclient import manager
    from ncclient.transport.errors import AuthenticationError, SSHError
    from ncclient.operations.errors import TimeoutExpiredError
    from ncclient.operations.rpc import RPCError
    NCCLIENT_AVAILABLE = True
except ImportError:
    NCCLIENT_AVAILABLE = False

from app.backends.planning import plan_interface as generic_plan

NETCONF_NS = "urn:ietf:params:xml:ns:netconf:base:1.0"
IF_NS = "urn:ietf:params:xml:ns:yang:ietf-interfaces"
IP_NS = "urn:ietf:params:xml:ns:yang:ietf-ip"
NATIVE_NS = "http://cisco.com/ns/yang/Cisco-IOS-XE-native"


def _handle_netconf_error(e):
    if isinstance(e, PermissionError):
        return {"status": "error", "result": "authentication_failed"}
    if isinstance(e, ConnectionError):
        return {"status": "error", "result": "connection_failed"}
    if NCCLIENT_AVAILABLE:
        if isinstance(e, AuthenticationError):
            return {"status": "error", "result": "authentication_failed"}
        if isinstance(e, (SSHError, TimeoutExpiredError)):
            return {"status": "error", "result": "connection_failed"}
        if isinstance(e, RPCError):
            return {"status": "error", "result": "backend_failed"}
    if isinstance(e, RuntimeError):
        return {"status": "error", "result": "backend_failed"}
    return {"status": "error", "result": "backend_failed"}


def get_interface_state(
    router,
    interface_name,
    netconf_get_config=None,
):
    """Return normalized interface status using NETCONF."""
    filter_xml = f"""<interfaces xmlns="{IF_NS}">
  <interface>
    <name>{interface_name}</name>
  </interface>
</interfaces>"""

    if netconf_get_config is None:
        if not NCCLIENT_AVAILABLE:
            raise RuntimeError("ncclient library is required for NETCONF")

        def _default_get_config(target_router, target_filter_xml):
            with manager.connect(
                host=target_router,
                port=830,
                username=os.getenv("ROUTER_USER", ""),
                password=os.getenv("ROUTER_PASS", ""),
                hostkey_verify=False,
                timeout=10,
            ) as m:
                return m.get_config(source="running", filter=("subtree", target_filter_xml)).data_xml

        netconf_get_config = _default_get_config

    try:
        xml_data = netconf_get_config(router, filter_xml)
    except Exception as e:
        return _handle_netconf_error(e)

    try:
        root = ET.fromstring(xml_data)
    except Exception:
        return {"status": "error", "result": "backend_failed"}

    iface_elem = root.find(f".//{{{IF_NS}}}interface")
    if iface_elem is None:
        return {
            "status": "ok",
            "result": "not_found",
            "interface": None,
        }

    name_elem = iface_elem.find(f"{{{IF_NS}}}name")
    name = name_elem.text if name_elem is not None else interface_name

    desc_elem = iface_elem.find(f"{{{IF_NS}}}description")
    description = desc_elem.text if desc_elem is not None else None

    enabled_elem = iface_elem.find(f"{{{IF_NS}}}enabled")
    enabled = enabled_elem.text.lower() == "true" if enabled_elem is not None else True
    admin_state = "up" if enabled else "down"

    ip_elem = iface_elem.find(f".//{{{IP_NS}}}ip")
    mask_elem = iface_elem.find(f".//{{{IP_NS}}}netmask")
    if ip_elem is not None and ip_elem.text and mask_elem is not None and mask_elem.text:
        ipv4_str = str(IPv4Interface(f"{ip_elem.text}/{mask_elem.text}"))
    else:
        ipv4_str = None

    return {
        "status": "ok",
        "result": "found",
        "interface": {
            "name": name,
            "ipv4": ipv4_str,
            "description": description,
            "admin_state": admin_state,
        },
    }


def plan_interface(
    router,
    desired_interface,
    netconf_get_config=None,
):
    """Return create/update/no_change plan using NETCONF status."""
    def _fetch_state(target_router, target_iface_name):
        return get_interface_state(target_router, target_iface_name, netconf_get_config=netconf_get_config)

    return generic_plan(router, desired_interface, _fetch_state)


def apply_interface(
    router,
    desired_interface,
    netconf_edit_config=None,
):
    """Apply complete desired interface state using NETCONF."""
    name = desired_interface["name"]
    number = name[len("Loopback"):]
    description = desired_interface["description"]
    ipv4 = IPv4Interface(desired_interface["ipv4"])
    address = str(ipv4.ip)
    mask = str(ipv4.network.netmask)
    shutdown_elem = "<shutdown/>" if desired_interface.get("admin_state") == "down" else ""

    config_xml = f"""<config xmlns="{NETCONF_NS}" xmlns:nc="{NETCONF_NS}">
  <native xmlns="{NATIVE_NS}">
    <interface>
      <Loopback nc:operation="replace">
        <name>{number}</name>
        <description>{description}</description>
        <ip>
          <address>
            <primary>
              <address>{address}</address>
              <mask>{mask}</mask>
            </primary>
          </address>
        </ip>
        {shutdown_elem}
      </Loopback>
    </interface>
  </native>
</config>"""

    if netconf_edit_config is None:
        if not NCCLIENT_AVAILABLE:
            raise RuntimeError("ncclient library is required for NETCONF")

        def _default_edit_config(target_router, target_config_xml):
            with manager.connect(
                host=target_router,
                port=830,
                username=os.getenv("ROUTER_USER", ""),
                password=os.getenv("ROUTER_PASS", ""),
                hostkey_verify=False,
                timeout=10,
            ) as m:
                m.edit_config(target="running", config=target_config_xml)

        netconf_edit_config = _default_edit_config

    try:
        netconf_edit_config(router, config_xml)
    except Exception as e:
        return _handle_netconf_error(e)

    return {
        "status": "ok",
        "result": "applied",
    }
