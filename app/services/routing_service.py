from app.models.enums import PriorityQueue
from app.services import policy_service


def route_priority(db, impact_score: float) -> PriorityQueue:
    policy = policy_service.get_active_policy(db)
    if impact_score >= policy.threshold_p0:
        return PriorityQueue.P0
    if impact_score >= policy.threshold_p1:
        return PriorityQueue.P1
    if impact_score >= policy.threshold_p2:
        return PriorityQueue.P2
    return PriorityQueue.HOLD
