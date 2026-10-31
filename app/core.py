import yaml

ALLOWED_ROUTERS = {
    "10.0.29.101",
    "10.0.29.102",
    "10.0.29.103",
    "10.0.29.104",
    "10.0.29.105",
}

CAPABILITY_MATRIX = {
    "restconf": {"status", "plan", "apply"},
    "netconf": {"status", "plan", "apply"},
    "ansible": {"apply"},
    "netmiko-textfsm": {"status", "delete"},
}

#data จะรับมาเป็น dict (json)
def validate_request(data):
    """
    Validate one IPA2026 desired-state request.

    Return a response dictionary according to
    specs/response-spec-v1.md.
    """
    if not isinstance(data, dict):
        return {"status": "error", "result": "invalid_yaml"}

    # 1. version: it must be the YAML integer 1.
    if "version" not in data:
        return {"status": "error", "result": "invalid_version"}
    version = data["version"]
    if isinstance(version, bool) or not isinstance(version, int) or version != 1:
        return {"status": "error", "result": "invalid_version"}

    # 2. router: missing_router, then invalid_router
    if "router" not in data or data["router"] is None or data["router"] == "":
        return {"status": "error", "result": "missing_router"}
    if str(data["router"]) not in ALLOWED_ROUTERS:
        return {"status": "error", "result": "invalid_router"}

    # 3. method: missing_method, then invalid_method
    if "method" not in data or data["method"] is None or data["method"] == "":
        return {"status": "error", "result": "missing_method"}
    method = data["method"]
    if method not in CAPABILITY_MATRIX:
        return {"status": "error", "result": "invalid_method"}

    # 4. action: missing_action, then invalid_action
    if "action" not in data or data["action"] is None or data["action"] == "":
        return {"status": "error", "result": "missing_action"}
    action = data["action"]
    if action not in CAPABILITY_MATRIX[method]:
        return {"status": "error", "result": "invalid_action"}

    # 5. desired, desired.interface, desired.interface.name
    if "desired" not in data or not isinstance(data["desired"], dict):
        return {"status": "error", "result": "missing_desired"}

    desired = data["desired"]
    if "interface" not in desired or not isinstance(desired["interface"], dict):
        return {"status": "error", "result": "missing_interface"}

    interface = desired["interface"]
    if "name" not in interface or interface["name"] is None or interface["name"] == "":
        return {"status": "error", "result": "missing_interface_name"}

    # 6. For plan and apply only: missing_ipv4, missing_description, missing_admin_state, then invalid_admin_state
    if action in ("plan", "apply"):
        if "ipv4" not in interface or interface["ipv4"] is None or interface["ipv4"] == "":
            return {"status": "error", "result": "missing_ipv4"}
        if "description" not in interface or interface["description"] is None or interface["description"] == "":
            return {"status": "error", "result": "missing_description"}
        if "admin_state" not in interface or interface["admin_state"] is None or interface["admin_state"] == "":
            return {"status": "error", "result": "missing_admin_state"}
        if interface["admin_state"] not in ("up", "down"):
            return {"status": "error", "result": "invalid_admin_state"}

    return {"status": "ok", "result": "accepted"}


def process_request_file(path):
    """
    Read a YAML request file, validate it,
    and return a response dictionary.
    """
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
    except Exception:
        return {"status": "error", "result": "invalid_yaml"}

    if not isinstance(data, dict):
        return {"status": "error", "result": "invalid_yaml"}

    return validate_request(data)
