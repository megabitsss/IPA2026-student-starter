MANAGED_FIELDS = ("ipv4", "description", "admin_state")


def build_plan(desired_interface, current_interface):
    """
    Compare desired interface state with normalized current state
    and return a plan according to specs/plan-spec-v1.md.
    """
    # 1. กรณี Interface ยังไม่มีบน Router -> สร้างใหม่ (create)
    if current_interface is None:
        changes = {
            field: {"to": desired_interface[field]}
            for field in MANAGED_FIELDS
            if field in desired_interface
        }
        return {
            "status": "ok",
            "result": "planned",
            "operation": "create",
            "changes": changes,
        }

    # 2. กรณี Interface มีอยู่แล้ว -> ตรวจหาฟิลด์ที่ต่างกัน
    changes = {}
    for field in MANAGED_FIELDS:
        desired_val = desired_interface.get(field)
        current_val = current_interface.get(field)
        if desired_val != current_val:
            changes[field] = {
                "from": current_val,
                "to": desired_val,
            }

    # 3. ถ้าไม่มีฟิลด์ไหนต่างกันเลย -> ไม่ต้องทำอะไร (no_change)
    if not changes:
        return {
            "status": "ok",
            "result": "planned",
            "operation": "no_change",
            "changes": {},
        }

    # 4. ถ้ามีฟิลด์ต่างกัน -> อัปเดตเฉพาะฟิลด์นั้น (update)
    return {
        "status": "ok",
        "result": "planned",
        "operation": "update",
        "changes": changes,
    }