"""Estrategias de chave estatica: FIFO, EDF, WSPT e prazo virtual.

Heap com mapa id -> posicao: push/pop/update/cancel em O(log n), peek(k) em
O(k log k).
"""
from mps.strategies._heap import IndexedHeap
from mps.strategies.backends import BACKENDS
from mps.strategies.base import Strategy


class OpsMixin(object):
    """`ops` guardado numa lista compartilhada com os heaps internos."""

    @property
    def ops(self):
        return self._cnt[0]

    @ops.setter
    def ops(self, value):
        try:
            self._cnt[0] = value
        except AttributeError:
            self._cnt = [value]


class StaticHeapStrategy(OpsMixin, Strategy):
    name = "static"

    def __init__(self, backend="heap", **params):
        Strategy.__init__(self, **params)
        self.backend = backend
        if backend == "heap":
            self._heap = IndexedHeap(self._cnt)
        elif backend in BACKENDS:
            self._heap = BACKENDS[backend](self._cnt)
        else:
            raise ValueError("backend desconhecido: %r" % (backend,))

    def _keyfn(self, order):
        raise NotImplementedError

    def key(self, order, now):
        return self._keyfn(order)

    def push(self, order, now):
        self._heap.push(self._keyfn(order), order)

    def pop(self, now):
        return self._heap.pop()

    def peek(self, now, k=1):
        return self._heap.peek(k)

    def update(self, order_id, now, new_score=None, new_deadline_min=None):
        order = self._heap.get(order_id)
        if order is None:
            return False
        if new_score is not None:
            order.priority_score = new_score
        if new_deadline_min is not None:
            order.deadline_min = new_deadline_min
        self._heap.change_key(order_id, self._keyfn(order))
        return True

    def cancel(self, order_id):
        return self._heap.remove(order_id) is not None

    def __len__(self):
        return len(self._heap)

    def __contains__(self, order_id):
        return order_id in self._heap


class FIFO(StaticHeapStrategy):
    name = "fifo"

    def _keyfn(self, o):
        return (o.seq,)


class EDF(StaticHeapStrategy):
    name = "edf"

    def _keyfn(self, o):
        return (o.deadline_min, -o.priority_score, o.seq)


class WSPT(StaticHeapStrategy):
    name = "wspt"

    def _keyfn(self, o):
        return (-(o.priority_score / o.pack_min), o.seq)


class VirtualDeadline(StaticHeapStrategy):
    """Prazo virtual: deadline - alpha*score (alpha em minutos por ponto)."""
    name = "virtual_deadline"

    def __init__(self, alpha=1.0, **params):
        params["alpha"] = alpha
        StaticHeapStrategy.__init__(self, **params)
        self.alpha = float(alpha)

    def _keyfn(self, o):
        return (o.deadline_min - self.alpha * o.priority_score, o.pack_min, o.seq)
