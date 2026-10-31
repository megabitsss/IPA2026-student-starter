def apply_interface(
    router,
    desired_interface,
    run_playbook=None,
):
    """Apply complete desired interface state using Ansible."""
    import ipaddress
    try:
        if run_playbook is None:
            raise RuntimeError("run_playbook callable not provided")
        # Extract variables from desired_interface
        ipv4_full = desired_interface.get("ipv4")
        if ipv4_full:
            ip_addr, prefix = ipv4_full.split("/")
            # Calculate netmask from prefix
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
        # Run the Ansible playbook (test injects a fake runner)
        run_playbook(variables)
        return {"status": "ok", "result": "applied"}
    except PermissionError:
        return {"status": "error", "result": "authentication_failed"}
    except ConnectionError:
        return {"status": "error", "result": "connection_failed"}
    except Exception:
        return {"status": "error", "result": "backend_failed"}
