"""Modelos de dados compartilhados (ver docs/CONTRACT.md)."""
from dataclasses import dataclass
from typing import Optional

PACK_MIN = {"P": 1.0, "M": 2.0, "G": 4.0}
VIP_THRESHOLD = 70.0
SIZES = ("P", "M", "G")
DAY_MIN = 960.0
WARMUP_MIN = 60.0


@dataclass
class Order:
    order_id: str
    arrival_min: float
    dispatch_window_min: float
    priority_score: float
    size: str
    deadline_min: float = None  # arrival + window (absoluto)
    seq: int = 0  # ordem de chegada (0, 1, 2...)

    def __post_init__(self):
        if self.deadline_min is None:
            self.deadline_min = self.arrival_min + self.dispatch_window_min

    @property
    def pack_min(self) -> float:
        return PACK_MIN[self.size]

    @property
    def is_vip(self) -> bool:
        return self.priority_score >= VIP_THRESHOLD


@dataclass
class OrderEvent:
    event_id: str
    time_min: float
    order_id: str
    kind: str  # "update" | "cancel"
    new_score: Optional[float] = None
    new_deadline_min: Optional[float] = None
