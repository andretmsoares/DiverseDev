"""Heap binario com mapa order_id -> posicao (update/cancel em O(log n))."""
import heapq


class IndexedHeap(object):
    """Min-heap de (chave, pedido). `cnt` e uma lista de 1 elemento compartilhada
    com a estrategia: cada comparacao e cada movimento de elemento soma 1."""

    __slots__ = ("keys", "items", "pos", "cnt")

    def __init__(self, cnt):
        self.keys = []
        self.items = []
        self.pos = {}
        self.cnt = cnt

    def __len__(self):
        return len(self.keys)

    def __contains__(self, oid):
        return oid in self.pos

    def get(self, oid):
        i = self.pos.get(oid)
        return None if i is None else self.items[i]

    def _up(self, i):
        keys, items, pos, cnt = self.keys, self.items, self.pos, self.cnt
        key, item = keys[i], items[i]
        while i > 0:
            p = (i - 1) >> 1
            cnt[0] += 1
            if key < keys[p]:
                keys[i] = keys[p]
                it = items[p]
                items[i] = it
                pos[it.order_id] = i
                cnt[0] += 1
                i = p
            else:
                break
        keys[i] = key
        items[i] = item
        pos[item.order_id] = i

    def _down(self, i):
        keys, items, pos, cnt = self.keys, self.items, self.pos, self.cnt
        n = len(keys)
        key, item = keys[i], items[i]
        while True:
            c = 2 * i + 1
            if c >= n:
                break
            if c + 1 < n:
                cnt[0] += 1
                if keys[c + 1] < keys[c]:
                    c += 1
            cnt[0] += 1
            if keys[c] < key:
                keys[i] = keys[c]
                it = items[c]
                items[i] = it
                pos[it.order_id] = i
                cnt[0] += 1
                i = c
            else:
                break
        keys[i] = key
        items[i] = item
        pos[item.order_id] = i

    def push(self, key, order):
        self.keys.append(key)
        self.items.append(order)
        self.pos[order.order_id] = len(self.keys) - 1
        self._up(len(self.keys) - 1)

    def top(self):
        return self.items[0] if self.items else None

    def pop(self):
        if not self.keys:
            return None
        top = self.items[0]
        self._remove_at(0)
        return top

    def _remove_at(self, i):
        keys, items = self.keys, self.items
        del self.pos[items[i].order_id]
        last_k = keys.pop()
        last_i = items.pop()
        if i == len(keys):
            return
        keys[i] = last_k
        items[i] = last_i
        self.pos[last_i.order_id] = i
        self._up(i)
        self._down(self.pos[last_i.order_id])

    def remove(self, oid):
        i = self.pos.get(oid)
        if i is None:
            return None
        order = self.items[i]
        self._remove_at(i)
        return order

    def change_key(self, oid, new_key):
        i = self.pos[oid]
        self.keys[i] = new_key
        self._up(i)
        self._down(self.pos[oid])

    def peek(self, k):
        """k menores em ordem, via heap auxiliar de indices: O(k log k)."""
        n = len(self.keys)
        if n == 0 or k <= 0:
            return []
        if k == 1:
            return [self.items[0]]
        aux = [(self.keys[0], 0)]
        out = []
        while aux and len(out) < k:
            _, i = heapq.heappop(aux)
            self.cnt[0] += 1
            out.append(self.items[i])
            for c in (2 * i + 1, 2 * i + 2):
                if c < n:
                    heapq.heappush(aux, (self.keys[c], c))
                    self.cnt[0] += 1
        return out
