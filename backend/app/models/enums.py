from enum import Enum


class JobState(str, Enum):
    UPLOADED = "UPLOADED"
    AI_PHASE_A_DONE = "AI_PHASE_A_DONE"
    ROUTED = "ROUTED"
    IN_REVIEW_GATE_1 = "IN_REVIEW_GATE_1"
    APPROVED_GATE_1 = "APPROVED_GATE_1"
    REJECTED_GATE_1 = "REJECTED_GATE_1"
    AI_PHASE_B_DONE = "AI_PHASE_B_DONE"
    IN_REVIEW_GATE_2 = "IN_REVIEW_GATE_2"
    APPROVED_GATE_2 = "APPROVED_GATE_2"
    REJECTED_GATE_2 = "REJECTED_GATE_2"
    DISTRIBUTED = "DISTRIBUTED"
    REPORT_READY = "REPORT_READY"
    REWARD_CREDITED = "REWARD_CREDITED"
    COMPLETED = "COMPLETED"
    HOLD = "HOLD"
    FAILED = "FAILED"


class PriorityQueue(str, Enum):
    P0 = "P0"
    P1 = "P1"
    P2 = "P2"
    HOLD = "HOLD"


class ReviewGate(str, Enum):
    GATE_1 = "GATE_1"
    GATE_2 = "GATE_2"


class ReviewDecisionValue(str, Enum):
    APPROVE = "APPROVE"
    REJECT = "REJECT"

