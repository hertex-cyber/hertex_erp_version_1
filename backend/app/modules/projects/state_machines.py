from app.core.exceptions import ConflictError

PROJECT_TRANSITIONS = {
    "draft": {"submit": "approval_pending"},
    "approval_pending": {"approve": "approved", "reject": "rejected"},
    "approved": {"activate": "active"},
    "active": {"hold": "on_hold", "complete": "completed", "cancel": "cancelled"},
    "on_hold": {"resume": "active", "cancel": "cancelled"},
    "completed": {"reopen": "active"},
    "rejected": {},
    "cancelled": {},
}

WORK_ITEM_TRANSITIONS = {
    "backlog": {"refine": "todo", "cancel": "cancelled"},
    "todo": {"start": "in_progress", "cancel": "cancelled"},
    "in_progress": {"block": "blocked", "submit_review": "in_review", "cancel": "cancelled"},
    "blocked": {"unblock": "in_progress", "cancel": "cancelled"},
    "in_review": {"approve": "done", "request_change": "in_progress", "cancel": "cancelled"},
    "done": {"accept": "accepted", "reopen": "in_progress", "cancel": "cancelled"},
    "accepted": {"close": "closed", "reopen": "in_progress"},
    "closed": {"reopen": "in_progress"},
    "cancelled": {"reopen": "in_progress"},
}

SPRINT_TRANSITIONS = {
    "planned": {"start": "active", "cancel": "cancelled"},
    "active": {"complete": "completed", "cancel": "cancelled"},
    "completed": {},
    "cancelled": {},
}

MILESTONE_TRANSITIONS = {
    "planned": {"reach": "reached", "cancel": "cancelled"},
    "reached": {"accept": "accepted"},
    "accepted": {"bill": "billed"},
    "billed": {"paid": "paid"},
    "paid": {},
    "cancelled": {},
}

TIME_ENTRY_TRANSITIONS = {
    "draft": {"submit": "submitted"},
    "submitted": {"approve": "approved", "reject": "rejected"},
    "rejected": {"resubmit": "submitted"},
    "approved": {"invoice": "invoiced", "revert": "draft"},
    "invoiced": {"paid": "paid"},
    "paid": {},
}

TIMESHEET_TRANSITIONS = {
    "draft": {"submit": "submitted"},
    "submitted": {"approve": "approved", "reject": "rejected"},
    "rejected": {"resubmit": "submitted"},
    "approved": {},
}

BILLING_RUN_TRANSITIONS = {
    "draft": {"generate": "review"},
    "review": {"approve": "approved"},
    "approved": {"post": "invoiced"},
    "invoiced": {"fail": "failed"},
    "failed": {"retry": "review"},
}

DEPENDENCY_TRANSITIONS = {
    "proposed": {"confirm": "active", "cancel": "cancelled"},
    "active": {"resolve": "resolved", "cancel": "cancelled"},
    "resolved": {},
    "cancelled": {},
}

RISK_TRANSITIONS = {
    "identified": {"assess": "analysing", "cancel": "cancelled"},
    "analysing": {"mitigate": "mitigated", "escalate": "escalated", "close": "closed"},
    "mitigated": {"close": "closed", "reopen": "analysing"},
    "escalated": {"mitigate": "mitigated", "close": "closed"},
    "closed": {"reopen": "analysing"},
    "cancelled": {},
}

ISSUE_TRANSITIONS = {
    "open": {"triage": "triaged", "cancel": "cancelled"},
    "triaged": {"start": "in_progress", "cancel": "cancelled"},
    "in_progress": {"resolve": "resolved", "cancel": "cancelled"},
    "resolved": {"close": "closed", "reopen": "in_progress"},
    "closed": {"reopen": "in_progress"},
    "cancelled": {},
}

CHANGE_REQUEST_TRANSITIONS = {
    "draft": {"submit": "submitted"},
    "submitted": {"approve": "approved", "reject": "rejected"},
    "approved": {"apply": "applied"},
    "rejected": {},
    "applied": {},
}

BOOKING_TRANSITIONS = {
    "requested": {"approve": "confirmed", "cancel": "cancelled"},
    "confirmed": {"fulfill": "fulfilled", "cancel": "cancelled"},
    "fulfilled": {},
    "cancelled": {},
}

AI_ACTION_TRANSITIONS = {
    "proposed": {"review": "approved", "reject": "rejected"},
    "approved": {"execute": "executed", "reject": "rejected"},
    "executed": {"reverse": "reversed"},
    "failed": {"retry": "proposed"},
    "rejected": {},
    "reversed": {},
}

STATUS_UPDATE_TRANSITIONS = {
    "draft": {"submit": "submitted", "publish": "published"},
    "submitted": {"approve": "approved", "reject": "rejected"},
    "rejected": {"submit": "submitted"},
    "approved": {"publish": "published"},
    "published": {},
}

STATE_MACHINES = {
    "project": PROJECT_TRANSITIONS,
    "work_item": WORK_ITEM_TRANSITIONS,
    "sprint": SPRINT_TRANSITIONS,
    "milestone": MILESTONE_TRANSITIONS,
    "time_entry": TIME_ENTRY_TRANSITIONS,
    "timesheet": TIMESHEET_TRANSITIONS,
    "billing_run": BILLING_RUN_TRANSITIONS,
    "dependency": DEPENDENCY_TRANSITIONS,
    "risk": RISK_TRANSITIONS,
    "issue": ISSUE_TRANSITIONS,
    "change_request": CHANGE_REQUEST_TRANSITIONS,
    "booking": BOOKING_TRANSITIONS,
    "ai_action": AI_ACTION_TRANSITIONS,
    "status_update": STATUS_UPDATE_TRANSITIONS,
}


def next_status(kind: str, current: str, event: str) -> str:
    machine = STATE_MACHINES.get(kind)
    if machine is None:
        raise ConflictError(f"Unknown state machine: {kind}")
    targets = machine.get(current)
    if targets is None or event not in targets:
        raise ConflictError(f"Illegal {kind} transition: {current} --{event}--> ?")
    return targets[event]
