"""RESTCONF backend implementation."""

import os
from ipaddress import IPv4Interface

try:
    import requests
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False

from app.backends.planning import plan_interface as generic_plan


def _handle_request_error(e):
    if isinstance(e, PermissionError):
        return {"status": "error", "result": "authentication_failed"}
    if isinstance(e, ConnectionError):
        return {"status": "error", "result": "connection_failed"}
    if REQUESTS_AVAILABLE:
        if isinstance(e, (requests.exceptions.ConnectionError, requests.exceptions.Timeout)):
            return {"status": "error", "result": "connection_failed"}
    if isinstance(e, RuntimeError):
        return {"status": "error", "result": "backend_failed"}
    return {"status": "error", "result": "backend_failed"}


def get_interface_state(
    router,
    interface_name,
    http_get=None,
):
    """Return normalized interface status using RESTCONF."""
    url = f"https://{router}/restconf/data/ietf-interfaces:interfaces/interface={interface_name}"

    if http_get is None:
        if not REQUESTS_AVAILABLE:
            raise RuntimeError("requests library is required for RESTCONF")

        def _default_get(target_url):
            return requests.get(
                target_url,
                auth=(os.getenv("ROUTER_USER", ""), os.getenv("ROUTER_PASS", "")),
                headers={"Accept": "application/yang-data+json"},
                verify=False,
                timeout=10,
            )
        http_get = _default_get

    try:
        response = http_get(url)
    except Exception as e:
        return _handle_request_error(e)

    status_code = getattr(response, "status_code", 500)

    if status_code == 200:
        json_data = response.json()
        iface_data = json_data.get("ietf-interfaces:interface", {})
        name = iface_data.get("name", interface_name)
        description = iface_data.get("description")
        enabled = iface_data.get("enabled", True)
        admin_state = "up" if enabled else "down"

        ipv4_data = iface_data.get("ietf-ip:ipv4", {}).get("address", [])
        if ipv4_data:
            ip = ipv4_data[0].get("ip")
            netmask = ipv4_data[0].get("netmask")
            ipv4_str = str(IPv4Interface(f"{ip}/{netmask}"))
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

    if status_code == 404:
        return {
            "status": "ok",
            "result": "not_found",
            "interface": None,
        }

    if status_code in (401, 403):
        return {
            "status": "error",
            "result": "authentication_failed",
        }

    return {
        "status": "error",
        "result": "backend_failed",
    }


def plan_interface(
    router,
    desired_interface,
    http_get=None,
):
    """Return create/update/no_change plan using RESTCONF status."""
    def _fetch_state(target_router, target_iface_name):
        return get_interface_state(target_router, target_iface_name, http_get=http_get)

    return generic_plan(router, desired_interface, _fetch_state)


def apply_interface(
    router,
    desired_interface,
    http_put=None,
):
    """Apply complete desired interface state using RESTCONF."""
    name = desired_interface["name"]
    number = int(name[len("Loopback"):])
    url = f"https://{router}/restconf/data/Cisco-IOS-XE-native:native/interface/Loopback={number}"

    ipv4 = IPv4Interface(desired_interface["ipv4"])

    payload = {
        "Cisco-IOS-XE-native:Loopback": {
            "name": number,
            "description": desired_interface["description"],
            "ip": {
                "address": {
                    "primary": {
                        "address": str(ipv4.ip),
                        "mask": str(ipv4.network.netmask),
                    }
                }
            },
        }
    }

    if desired_interface.get("admin_state") == "down":
        payload["Cisco-IOS-XE-native:Loopback"]["shutdown"] = [None]

    if http_put is None:
        if not REQUESTS_AVAILABLE:
            raise RuntimeError("requests library is required for RESTCONF")

        def _default_put(target_url, json=None):
            return requests.put(
                target_url,
                json=json,
                auth=(os.getenv("ROUTER_USER", ""), os.getenv("ROUTER_PASS", "")),
                headers={
                    "Accept": "application/yang-data+json",
                    "Content-Type": "application/yang-data+json",
                },
                verify=False,
                timeout=10,
            )
        http_put = _default_put

    try:
        response = http_put(url, json=payload)
    except Exception as e:
        return _handle_request_error(e)

    status_code = getattr(response, "status_code", 500)

    if status_code in (200, 201, 204):
        return {
            "status": "ok",
            "result": "applied",
        }

    if status_code in (401, 403):
        return {
            "status": "error",
            "result": "authentication_failed",
        }

    return {
        "status": "error",
        "result": "backend_failed",
    }
