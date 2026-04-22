from typing import Any, Optional


async def plan_reminder_hook(chat_id: str, deps: Any) -> Optional[str]:
    """Global system-reminder hook: injects the active plan state each turn.

    Skipped when there is no plan or all phases are completed.
    """
    from suzent.plan import read_plan_from_database, PhaseStatus

    plan = read_plan_from_database(chat_id)
    if not plan or not plan.phases:
        return None

    if all(p.status == PhaseStatus.COMPLETED for p in plan.phases):
        return None

    phases_str = "".join(str(p) for p in plan.phases)
    return f"Active plan — {plan.objective}\n{phases_str}"
