"""Ansible backend for Part 3."""

import ipaddress
import json
import os
import subprocess
from pathlib import Path


def apply_interface(
    router,
    desired_interface,
    run_playbook=None,
):
    """Apply complete desired interface state using Ansible."""
    try:
        ipv4_full = desired_interface.get("ipv4")
        if ipv4_full:
            ip_addr, prefix = ipv4_full.split("/")
            netmask = str(ipaddress.IPv4Network(f"0.0.0.0/{prefix}").netmask)
        else:
            ip_addr = None
            netmask = None

        variables = {
            "router": router,
            "interface_name": desired_interface.get("name"),
            "description": desired_interface.get("description"),
            "ipv4_address": ip_addr,
            "netmask": netmask,
            "shutdown": desired_interface.get("admin_state") == "down",
        }

        if run_playbook is None:
            def _default_run_playbook(vars_dict):
                playbook_dir = Path(__file__).resolve().parents[2] / "ansible"
                playbook = playbook_dir / "apply_interface.yml"
                inventory = playbook_dir / "inventory.ini"
                cmd = [
                    "ansible-playbook",
                    "-i", str(inventory),
                    str(playbook),
                    "-e", json.dumps(vars_dict),
                ]
                proc = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=60,
                )
                if proc.returncode != 0:
                    combined_err = f"{proc.stdout}\n{proc.stderr}".lower()
                    if "authentication" in combined_err or "permission denied" in combined_err:
                        raise PermissionError(combined_err)
                    if "unreachable" in combined_err or "connection" in combined_err:
                        raise ConnectionError(combined_err)
                    raise RuntimeError(combined_err)

            run_playbook = _default_run_playbook

        run_playbook(variables)
        return {"status": "ok", "result": "applied"}
    except PermissionError:
        return {"status": "error", "result": "authentication_failed"}
    except ConnectionError:
        return {"status": "error", "result": "connection_failed"}
    except Exception:
        return {"status": "error", "result": "backend_failed"}
