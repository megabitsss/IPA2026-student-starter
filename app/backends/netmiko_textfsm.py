"""Netmiko + TextFSM backend for Part 3.

The test suite injects callables ``netmiko_get`` and ``netmiko_delete`` that
simulate real Netmiko interactions.  This module normalises their output
or translates raised exceptions into the canonical result format expected by
the dispatcher.
"""

from typing import Any, Dict


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
    # Common abbreviation mappings
    abbrevs = {
        "Lo": "Loopback",
        "Gi": "GigabitEthernet",
        "Fa": "FastEthernet",
        "Te": "TenGigabitEthernet",
        "Eth": "Ethernet",
    }
    for short, full in abbrevs.items():
        if interface_name.startswith(full) and port_name.startswith(short):
            # Compare the numeric suffix
            if interface_name[len(full):] == port_name[len(short):]:
                return True
    return False


def get_interface_state(
    router: str,
    interface_name: str,
    netmiko_get: Any = None,
) -> Dict[str, Any]:
    """Return normalized interface state using Netmiko + TextFSM."""
    try:
        if netmiko_get is None:
            raise RuntimeError("netmiko_get callable not provided")
        ip_info, descriptions = netmiko_get(router, interface_name)
        # Find the matching entry for the requested interface.
        iface_entry = next(
            (i for i in ip_info if i.get("interface") == interface_name), None
        )
        if not iface_entry:
            return {"status": "ok", "result": "not_found", "interface": None}
        # Build IPv4/Prefix string — values may be lists (TextFSM output).
        ip_addr = _extract_scalar(iface_entry.get("ip_address"))
        prefix = _extract_scalar(iface_entry.get("prefix_length"))
        ipv4 = f"{ip_addr}/{prefix}" if ip_addr and prefix is not None else None
        # Find description — port name may be abbreviated (e.g. Lo123).
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
    except PermissionError:
        return {"status": "error", "result": "authentication_failed"}
    except ConnectionError:
        return {"status": "error", "result": "connection_failed"}
    except Exception:
        return {"status": "error", "result": "backend_failed"}


def delete_interface(
    router: str,
    interface_name: str,
    netmiko_delete: Any = None,
) -> Dict[str, Any]:
    """Delete an interface using Netmiko.

    ``netmiko_delete`` returns the ``delete_result`` value directly as a
    string (``"deleted"`` or ``"not_found"``), NOT wrapped in a dict.
    """
    try:
        if netmiko_delete is None:
            raise RuntimeError("netmiko_delete callable not provided")
        delete_res = netmiko_delete(router, interface_name)
        # delete_res is a plain string like "deleted" or "not_found"
        if delete_res == "deleted":
            return {"status": "ok", "result": "deleted"}
        if delete_res == "not_found":
            return {"status": "ok", "result": "not_found", "interface": None}
        return {"status": "error", "result": "backend_failed"}
    except PermissionError:
        return {"status": "error", "result": "authentication_failed"}
    except ConnectionError:
        return {"status": "error", "result": "connection_failed"}
    except Exception:
        return {"status": "error", "result": "backend_failed"}
