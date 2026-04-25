from app.models.enums import PriorityQueue
from app.services import policy_service

_PRIORITY_ORDER = [PriorityQueue.HOLD, PriorityQueue.P2, PriorityQueue.P1, PriorityQueue.P0]


def route_priority(db, impact_score: float, news_context: dict = None) -> PriorityQueue:
    policy = policy_service.get_active_policy(db)

    if impact_score >= policy.threshold_p0:
        priority = PriorityQueue.P0
    elif impact_score >= policy.threshold_p1:
        priority = PriorityQueue.P1
    elif impact_score >= policy.threshold_p2:
        priority = PriorityQueue.P2
    else:
        priority = PriorityQueue.HOLD

    # Breaking/high-velocity news escalates priority one tier
    if news_context and news_context.get("is_trending") and news_context.get("velocity") in ("HIGH", "BREAKING"):
        idx = _PRIORITY_ORDER.index(priority)
        priority = _PRIORITY_ORDER[min(idx + 1, len(_PRIORITY_ORDER) - 1)]

    return priority
