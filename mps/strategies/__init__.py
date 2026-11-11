"""Estrategias de ordenacao e registry (ver docs/CONTRACT.md, secao 5)."""
from mps.strategies.base import Strategy
from mps.strategies.bands_aging import BandsAging
from mps.strategies.composite import Composite
from mps.strategies.static import EDF, FIFO, WSPT, VirtualDeadline
from mps.strategies.two_queues import TwoQueues

REGISTRY = {
    "fifo": FIFO,
    "edf": EDF,
    "composite": Composite,
    "two_queues": TwoQueues,
    "bands_aging": BandsAging,
    "wspt": WSPT,
    "virtual_deadline": VirtualDeadline,
}


def make_strategy(impl, **params):
    try:
        cls = REGISTRY[impl]
    except KeyError:
        raise ValueError("estrategia desconhecida: %r (validas: %s)" % (impl, sorted(REGISTRY)))
    return cls(**params)


__all__ = ["Strategy", "REGISTRY", "make_strategy"]
