"""Backends de fila por ordenacao (CONTRACT 5b): insertion, selection, merge, quick.

Algoritmos escritos aqui (sem sorted()/list.sort). Todos expoem a mesma
interface do IndexedHeap (push, pop, remove, change_key, peek, get) e contam
`ops` (comparacoes + movimentos) na lista compartilhada `cnt`.
Elementos guardados como tuplas (chave, pedido); so a chave e comparada.
"""


class _ListQueue(object):
    name = "list"

    def __init__(self, cnt):
        self.cnt = cnt
        self.a = []          # lista de (chave, pedido)
        self.ids = {}        # order_id -> pedido (pertinencia O(1))

    def __len__(self):
        return len(self.a)

    def __contains__(self, oid):
        return oid in self.ids

    def get(self, oid):
        return self.ids.get(oid)

    def _find(self, oid):
        a = self.a
        for i in range(len(a)):
            self.cnt[0] += 1
            if a[i][1].order_id == oid:
                return i
        return -1

    def change_key(self, oid, new_key):
        o = self.remove(oid)
        self.push(new_key, o)


class InsertionQueue(_ListQueue):
    """Lista sempre ordenada; push = insertion sort de um elemento (O(n)); pop O(1)
    (retirada da frente)."""
    name = "insertion"

    def push(self, key, order):
        a = self.a
        a.append(None)
        i = len(a) - 1
        cnt = self.cnt
        while i > 0:
            cnt[0] += 1
            if key < a[i - 1][0]:
                a[i] = a[i - 1]
                cnt[0] += 1
                i -= 1
            else:
                break
        a[i] = (key, order)
        self.ids[order.order_id] = order

    def pop(self):
        if not self.a:
            return None
        self.cnt[0] += 1
        o = self.a.pop(0)[1]
        del self.ids[o.order_id]
        return o

    def remove(self, oid):
        i = self._find(oid)
        if i < 0:
            return None
        o = self.a.pop(i)[1]
        self.cnt[0] += len(self.a) - i  # deslocamento
        del self.ids[oid]
        return o

    def peek(self, k):
        return [e[1] for e in self.a[:k]]


class SelectionQueue(_ListQueue):
    """Lista sem ordem; pop = uma passada de selection sort (varre o minimo, O(n))."""
    name = "selection"

    def push(self, key, order):
        self.a.append((key, order))
        self.ids[order.order_id] = order
        self.cnt[0] += 1

    def _argmin(self, skip=()):
        a = self.a
        best = -1
        for i in range(len(a)):
            if i in skip:
                continue
            if best < 0:
                best = i
                continue
            self.cnt[0] += 1
            if a[i][0] < a[best][0]:
                best = i
        return best

    def _del_at(self, i):
        a = self.a
        o = a[i][1]
        last = a.pop()
        if i < len(a):
            a[i] = last
            self.cnt[0] += 1
        del self.ids[o.order_id]
        return o

    def pop(self):
        if not self.a:
            return None
        return self._del_at(self._argmin())

    def remove(self, oid):
        i = self._find(oid)
        if i < 0:
            return None
        return self._del_at(i)

    def peek(self, k):
        out = []
        skip = set()
        for _ in range(min(k, len(self.a))):
            i = self._argmin(skip)
            skip.add(i)
            out.append(self.a[i][1])
        return out


class _ResortQueue(_ListQueue):
    """Mantem a lista ordenada; qualquer mudanca de chaves marca `dirty` e a lista
    inteira e reordenada pelo algoritmo proprio antes do proximo pop/peek."""

    def __init__(self, cnt):
        _ListQueue.__init__(self, cnt)
        self.dirty = False

    def _sort(self):
        raise NotImplementedError

    def _ready(self):
        if self.dirty:
            self._sort()
            self.dirty = False

    def push(self, key, order):
        self.a.append((key, order))
        self.ids[order.order_id] = order
        self.dirty = True
        self.cnt[0] += 1

    def pop(self):
        if not self.a:
            return None
        self._ready()
        self.cnt[0] += 1
        o = self.a.pop(0)[1]
        del self.ids[o.order_id]
        return o

    def remove(self, oid):
        i = self._find(oid)
        if i < 0:
            return None
        o = self.a.pop(i)[1]   # remover nao desordena
        self.cnt[0] += len(self.a) - i
        del self.ids[oid]
        return o

    def peek(self, k):
        self._ready()
        return [e[1] for e in self.a[:k]]


class MergeQueue(_ResortQueue):
    """Merge sort proprio, iterativo (bottom-up), estavel, O(n log n)."""
    name = "merge"

    def _sort(self):
        a = self.a
        n = len(a)
        cnt = self.cnt
        src, dst = a, [None] * n
        width = 1
        while width < n:
            i = 0
            while i < n:
                mid = min(i + width, n)
                hi = min(i + 2 * width, n)
                l, r, k = i, mid, i
                while l < mid and r < hi:
                    cnt[0] += 1
                    if src[r][0] < src[l][0]:
                        dst[k] = src[r]
                        r += 1
                    else:
                        dst[k] = src[l]
                        l += 1
                    k += 1
                cnt[0] += (mid - l) + (hi - r)
                while l < mid:
                    dst[k] = src[l]
                    l += 1
                    k += 1
                while r < hi:
                    dst[k] = src[r]
                    r += 1
                    k += 1
                i += 2 * width
            src, dst = dst, src
            width *= 2
        if src is not a:
            a[:] = src


class QuickQueue(_ResortQueue):
    """Quick sort proprio com pivo fixo (primeiro elemento do intervalo) e pilha
    explicita (sem recursao). Em fila quase ordenada degenera para O(n^2)."""
    name = "quick"

    def _sort(self):
        a = self.a
        cnt = self.cnt
        stack = [(0, len(a) - 1)]
        while stack:
            lo, hi = stack.pop()
            if lo >= hi:
                continue
            pivot = a[lo][0]
            i = lo
            for j in range(lo + 1, hi + 1):
                cnt[0] += 1
                if a[j][0] < pivot:
                    i += 1
                    a[i], a[j] = a[j], a[i]
                    cnt[0] += 1
            a[lo], a[i] = a[i], a[lo]
            cnt[0] += 1
            stack.append((lo, i - 1))
            stack.append((i + 1, hi))


BACKENDS = {
    "insertion": InsertionQueue,
    "selection": SelectionQueue,
    "merge": MergeQueue,
    "quick": QuickQueue,
}
