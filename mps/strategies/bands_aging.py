"""Faixas de prazo com envelhecimento.

faixa = floor(max(deadline - now, 0) / band_min); dentro da faixa, maior
score + aging*(now - arrival), depois menor pack_min, depois seq.

Observacao: aging*now e comum a todos os pedidos, logo a ordem DENTRO da faixa
e estatica (score - aging*arrival). So a pertinencia a faixa muda com o tempo;
um heap de instantes de mudanca de faixa (deadline - b*band_min) move cada
pedido exatamente quando cruza a fronteira. Exato e O(log n) por operacao.
"""
import heapq
import math

from mps.strategies._heap import IndexedHeap
from mps.strategies.base import Strategy
from mps.strategies.static import OpsMixin


class BandsAging(OpsMixin, Strategy):
    name = "bands_aging"

    def __init__(self, band_min=30.0, aging_pts_per_min=0.2, **params):
        params["band_min"] = band_min
        params["aging_pts_per_min"] = aging_pts_per_min
        Strategy.__init__(self, **params)
        self.band_min = float(band_min)
        self.aging = float(aging_pts_per_min)
        self._bands = {}   # faixa -> IndexedHeap
        self._of = {}      # order_id -> faixa
        self._mig = []     # (instante, serial, order_id)
        self._ver = {}
        self._serial = 0

    def _band(self, o, now):
        d = o.deadline_min - now
        return int(math.floor(d / self.band_min)) if d > 0 else 0

    def key(self, order, now):
        return (self._band(order, now),
                -(order.priority_score + self.aging * (now - order.arrival_min)),
                order.pack_min, order.seq)

    def _inkey(self, o):
        return (-(o.priority_score - self.aging * o.arrival_min), o.pack_min, o.seq)

    def _place(self, o, now):
        b = self._band(o, now)
        h = self._bands.get(b)
        if h is None:
            h = self._bands[b] = IndexedHeap(self._cnt)
        h.push(self._inkey(o), o)
        self._of[o.order_id] = b
        self._serial += 1
        self._ver[o.order_id] = self._serial
        if b >= 1:
            t = o.deadline_min - b * self.band_min
            if t < now:
                t = now
            heapq.heappush(self._mig, (t, self._serial, o.order_id))
            self._cnt[0] += 1

    def _take(self, oid):
        b = self._of.pop(oid, None)
        if b is None:
            return None
        self._ver.pop(oid, None)
        h = self._bands[b]
        o = h.remove(oid)
        if not len(h):
            del self._bands[b]
        return o

    def _sync(self, now):
        mig = self._mig
        while mig and mig[0][0] < now:
            _, ser, oid = heapq.heappop(mig)
            self._cnt[0] += 1
            if self._ver.get(oid) != ser:
                continue
            o = self._take(oid)
            self._place(o, now)

    def push(self, order, now):
        self._sync(now)
        self._place(order, now)

    def pop(self, now):
        self._sync(now)
        if not self._bands:
            return None
        b = min(self._bands)
        h = self._bands[b]
        o = h.pop()
        del self._of[o.order_id]
        self._ver.pop(o.order_id, None)
        if not len(h):
            del self._bands[b]
        return o

    def peek(self, now, k=1):
        self._sync(now)
        out = []
        for b in sorted(self._bands):
            if len(out) >= k:
                break
            out.extend(self._bands[b].peek(k - len(out)))
        return out

    def update(self, order_id, now, new_score=None, new_deadline_min=None):
        self._sync(now)
        o = self._take(order_id)
        if o is None:
            return False
        if new_score is not None:
            o.priority_score = new_score
        if new_deadline_min is not None:
            o.deadline_min = new_deadline_min
        self._place(o, now)
        return True

    def cancel(self, order_id):
        return self._take(order_id) is not None

    def __len__(self):
        return len(self._of)

    def __contains__(self, order_id):
        return order_id in self._of
