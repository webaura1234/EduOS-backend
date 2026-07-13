"""Optional module update adapters during promotion execution — skipped when unavailable."""

MODULES = ["Transport", "Hostel", "Library", "ID Card"]


def run_module_updates(*, branch_id, session_id, student_actions: list[dict], user=None) -> list[dict]:
    """Return skipped module rows for the execution report."""
    return [{"module": name, "status": "skipped"} for name in MODULES]
