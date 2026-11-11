"""Composite: maior score / max(deadline - now, 1). Chave dependente do tempo.

Implementacao: heap do heapq (C) com reavaliacao periodica. As chaves sao
recalculadas (heapify O(n)) quando o relogio avanca `refresh_min` desde a
ultima reconstrucao (padrao 1 min; 0 = exato a cada instante novo). Entre
reconstrucoes, pedidos novos entram com a chave do instante de chegada.
Cancel/update usam remocao preguicosa. `ops` e estimado analiticamente
(heapify ~ 2n, push/pop ~ log2 n), pois o heapq e implementado em C.
"""
import heapq

from mps.strategies.base import Strategy
from mps.strategies.static import OpsMixin


class Composite(OpsMixin, Strategy):
    name = "composite"

    def __init__(self, refresh_min=1.0, **params):
        params["refresh_min"] = refresh_min
        Strategy.__init__(self, **params)
        self.refresh_min = float(refresh_min)
        self._heap = []      # entradas [-ratio, seq, serial, order, alive]
        self._live = {}      # order_id -> entrada viva
        self._t0 = 0.0
        self._serial = 0

    @staticmethod
    def _ratio(o, now):
        d = o.deadline_min - now
        return o.priority_score / (d if d > 1.0 else 1.0)

    def key(self, order, now):
        return (-self._ratio(order, now), order.seq)

    def _entry(self, o, now):
        self._serial += 1
        return [-self._ratio(o, now), o.seq, self._serial, o, True]

    def _sync(self, now):
        if now != self._t0 and now - self._t0 >= self.refresh_min:
            ents = []
            for e in self._live.values():
                e[0] = -self._ratio(e[3], now)
                ents.append(e)
            heapq.heapify(ents)
            self._heap = ents
            self._t0 = now
            self.ops += 2 * len(ents)

    def _log(self):
        return max(1, len(self._live).bit_length())

    def push(self, order, now):
        if not self._live:
            self._heap = []
            self._t0 = now
        else:
            self._sync(now)
        e = self._entry(order, now)
        self._live[order.order_id] = e
        heapq.heappush(self._heap, e)
        self.ops += self._log()

    def _clean(self):
        h = self._heap
        while h and not h[0][4]:
            heapq.heappop(h)
            self.ops += self._log()

    def pop(self, now):
        if not self._live:
            return None
        self._sync(now)
        self._clean()
        e = heapq.heappop(self._heap)
        self.ops += self._log()
        del self._live[e[3].order_id]
        e[4] = False
        return e[3]

    def peek(self, now, k=1):
        if not self._live:
            return []
        self._sync(now)
        self._clean()
        h = self._heap
        if k == 1:
            return [h[0][3]]
        aux = [(h[0], 0)]
        out = []
        n = len(h)
        while aux and len(out) < k:
            e, i = heapq.heappop(aux)
            if e[4]:
                out.append(e[3])
            for c in (2 * i + 1, 2 * i + 2):
                if c < n:
                    heapq.heappush(aux, (h[c], c))
            self.ops += 2
        return out

    def update(self, order_id, now, new_score=None, new_deadline_min=None):
        old = self._live.get(order_id)
        if old is None:
            return False
        o = old[3]
        old[4] = False
        if new_score is not None:
            o.priority_score = new_score
        if new_deadline_min is not None:
            o.deadline_min = new_deadline_min
        e = self._entry(o, now)
        self._live[order_id] = e
        heapq.heappush(self._heap, e)
        self.ops += self._log()
        return True

    def cancel(self, order_id):
        e = self._live.pop(order_id, None)
        if e is None:
            return False
        e[4] = False
        return True

    def __len__(self):
        return len(self._live)

    def __contains__(self, order_id):
        return order_id in self._live
