"""Duas filas: urgentes (maior score primeiro) e normais (FIFO).

Urgente se deadline - now <= urgent_limit_min. A migracao normal -> urgente e
EXATA: um heap de instantes de migracao (deadline - limite) com invalidacao
por versao dispara a migracao assim que o relogio alcanca o instante.
Tudo O(log n) por operacao.
"""
import heapq

from mps.strategies._heap import IndexedHeap
from mps.strategies.base import Strategy
from mps.strategies.static import OpsMixin


class TwoQueues(OpsMixin, Strategy):
    name = "two_queues"

    def __init__(self, urgent_limit_min=60.0, **params):
        params["urgent_limit_min"] = urgent_limit_min
        Strategy.__init__(self, **params)
        self.limit = float(urgent_limit_min)
        self._urgent = IndexedHeap(self._cnt)
        self._normal = IndexedHeap(self._cnt)
        self._mig = []   # (instante, serial, order_id)
        self._ver = {}   # order_id -> serial valido (so pedidos normais)
        self._serial = 0

    def key(self, order, now):
        if order.deadline_min - now <= self.limit:
            return (0, -order.priority_score, order.seq)
        return (1, order.seq, 0)

    def _place(self, o, now):
        if o.deadline_min - now <= self.limit:
            self._urgent.push((-o.priority_score, o.seq), o)
        else:
            self._normal.push((o.seq,), o)
            self._serial += 1
            self._ver[o.order_id] = self._serial
            heapq.heappush(self._mig, (o.deadline_min - self.limit, self._serial, o.order_id))
            self._cnt[0] += 1

    def _sync(self, now):
        mig = self._mig
        while mig and mig[0][0] <= now:
            _, ser, oid = heapq.heappop(mig)
            self._cnt[0] += 1
            if self._ver.get(oid) != ser:
                continue
            del self._ver[oid]
            o = self._normal.remove(oid)
            self._urgent.push((-o.priority_score, o.seq), o)

    def push(self, order, now):
        self._sync(now)
        self._place(order, now)

    def pop(self, now):
        self._sync(now)
        if len(self._urgent):
            return self._urgent.pop()
        o = self._normal.pop()
        if o is not None:
            self._ver.pop(o.order_id, None)
        return o

    def peek(self, now, k=1):
        self._sync(now)
        out = self._urgent.peek(k)
        if len(out) < k:
            out = out + self._normal.peek(k - len(out))
        return out

    def _detach(self, order_id):
        o = self._urgent.remove(order_id)
        if o is None:
            o = self._normal.remove(order_id)
            if o is not None:
                self._ver.pop(order_id, None)
        return o

    def update(self, order_id, now, new_score=None, new_deadline_min=None):
        self._sync(now)
        o = self._detach(order_id)
        if o is None:
            return False
        if new_score is not None:
            o.priority_score = new_score
        if new_deadline_min is not None:
            o.deadline_min = new_deadline_min
        self._place(o, now)
        return True

    def cancel(self, order_id):
        return self._detach(order_id) is not None

    def __len__(self):
        return len(self._urgent) + len(self._normal)

    def __contains__(self, order_id):
        return order_id in self._urgent or order_id in self._normal
