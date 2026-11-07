"""Netmiko + TextFSM backend for Part 3.

The test suite injects callables ``netmiko_get`` and ``netmiko_delete`` that
simulate real Netmiko interactions. When omitted, real Netmiko SSH transport
is used.
"""

import os
from typing import Any, Dict

try:
    from netmiko import ConnectHandler
    from netmiko.exceptions import (
        NetmikoAuthenticationException,
        NetmikoTimeoutException,
    )
    NETMIKO_AVAILABLE = True
except ImportError:
    NETMIKO_AVAILABLE = False


def _handle_netmiko_error(e):
    if isinstance(e, PermissionError):
        return {"status": "error", "result": "authentication_failed"}
    if isinstance(e, ConnectionError):
        return {"status": "error", "result": "connection_failed"}
    if NETMIKO_AVAILABLE:
        if isinstance(e, NetmikoAuthenticationException):
            return {"status": "error", "result": "authentication_failed"}
        if isinstance(e, NetmikoTimeoutException):
            return {"status": "error", "result": "connection_failed"}
    if isinstance(e, RuntimeError):
        return {"status": "error", "result": "backend_failed"}
    return {"status": "error", "result": "backend_failed"}


def _map_admin_state(link_status: str, protocol_status: str) -> str:
    """Map combined link/protocol status to ``up``/``down``."""
    lowered = f"{link_status} {protocol_status}".lower()
    return "down" if "down" in lowered else "up"


def _extract_scalar(value):
    """Extract a scalar from a value that might be a list (TextFSM quirk)."""
    if isinstance(value, list):
        return value[0] if value else None
    return value


def _port_matches(port_name: str, interface_name: str) -> bool:
    """Check if a short port name (e.g. Lo123) matches a full interface name
    (e.g. Loopback123). Also handles exact matches."""
    if port_name == interface_name:
        return True
    abbrevs = {
        "Lo": "Loopback",
        "Gi": "GigabitEthernet",
        "Fa": "FastEthernet",
        "Te": "TenGigabitEthernet",
        "Eth": "Ethernet",
    }
    for short, full in abbrevs.items():
        if interface_name.startswith(full) and port_name.startswith(short):
            if interface_name[len(full):] == port_name[len(short):]:
                return True
    return False


def get_interface_state(
    router: str,
    interface_name: str,
    netmiko_get: Any = None,
) -> Dict[str, Any]:
    """Return normalized interface state using Netmiko + TextFSM."""
    if netmiko_get is None:
        if not NETMIKO_AVAILABLE:
            raise RuntimeError("netmiko library is required")

        def _default_get(target_router, target_iface):
            device = {
                "device_type": "cisco_ios",
                "host": target_router,
                "username": os.environ.get("ROUTER_USER", ""),
                "password": os.environ.get("ROUTER_PASS", ""),
            }
            with ConnectHandler(**device) as net_connect:
                ip_info = net_connect.send_command(
                    f"show ip interface {target_iface}",
                    use_textfsm=True,
                )
                descriptions = net_connect.send_command(
                    "show interfaces description",
                    use_textfsm=True,
                )
                if isinstance(ip_info, str):
                    ip_info = []
                if isinstance(descriptions, str):
                    descriptions = []
                return (ip_info, descriptions)

        netmiko_get = _default_get

    try:
        ip_info, descriptions = netmiko_get(router, interface_name)
        iface_entry = next(
            (i for i in ip_info if i.get("interface") == interface_name), None
        )
        if not iface_entry:
            return {"status": "ok", "result": "not_found", "interface": None}

        ip_addr = _extract_scalar(iface_entry.get("ip_address"))
        prefix = _extract_scalar(iface_entry.get("prefix_length"))
        ipv4 = f"{ip_addr}/{prefix}" if ip_addr and prefix is not None else None
        desc_entry = next(
            (d for d in descriptions if _port_matches(d.get("port", ""), interface_name)),
            {},
        )
        description = desc_entry.get("description")
        admin_state = _map_admin_state(
            iface_entry.get("link_status", ""),
            iface_entry.get("protocol_status", ""),
        )
        normalized = {
            "name": interface_name,
            "ipv4": ipv4,
            "description": description,
            "admin_state": admin_state,
        }
        return {"status": "ok", "result": "found", "interface": normalized}
    except Exception as e:
        return _handle_netmiko_error(e)


def delete_interface(
    router: str,
    interface_name: str,
    netmiko_delete: Any = None,
) -> Dict[str, Any]:
    """Delete an interface using Netmiko."""
    if netmiko_delete is None:
        if not NETMIKO_AVAILABLE:
            raise RuntimeError("netmiko library is required")

        def _default_delete(target_router, target_iface):
            device = {
                "device_type": "cisco_ios",
                "host": target_router,
                "username": os.environ.get("ROUTER_USER", ""),
                "password": os.environ.get("ROUTER_PASS", ""),
            }
            with ConnectHandler(**device) as net_connect:
                output = net_connect.send_command(
                    f"show ip interface brief {target_iface}"
                )
                # Check if interface exists in output table
                has_iface = any(
                    line.strip().startswith(target_iface)
                    for line in output.splitlines()
                )
                if not has_iface:
                    return "not_found"

                net_connect.send_config_set([f"no interface {target_iface}"])
                return "deleted"

        netmiko_delete = _default_delete

    try:
        delete_res = netmiko_delete(router, interface_name)
        if delete_res == "deleted":
            return {"status": "ok", "result": "deleted"}
        if delete_res == "not_found":
            return {"status": "ok", "result": "not_found", "interface": None}
        return {"status": "error", "result": "backend_failed"}
    except Exception as e:
        return _handle_netmiko_error(e)
