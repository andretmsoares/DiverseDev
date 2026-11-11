"""Simulador de eventos discretos (ver docs/CONTRACT.md, secoes 4 e 6)."""
import heapq
import time

from mps.models import PACK_MIN, WARMUP_MIN, Order
from mps.strategies import make_strategy

# prioridade de desempate para eventos no mesmo instante (menor primeiro)
P_DONE, P_OUT_END, P_OUT_START, P_ARRIVAL, P_EVENT = 0, 1, 2, 3, 4


class _Class(object):
    __slots__ = ("name", "sizes", "count", "queue", "busy", "down", "free",
                 "busy_area", "max_q", "q_area")

    def __init__(self, name, sizes, count, queue):
        self.name = name
        self.sizes = sizes
        self.count = count
        self.queue = queue
        self.busy = 0
        self.down = 0
        self.free = list(range(count - 1, -1, -1))  # pilha de slots livres
        self.busy_area = 0.0
        self.max_q = 0
        self.q_area = 0.0


class SimResult(object):
    """Saida bruta de uma simulacao; as metricas sao calculadas em metrics.py."""

    def __init__(self):
        self.records = []        # (order, start, completion) de pedidos medidos
        self.n_arrivals = 0
        self.n_cancelled = 0
        self.n_loans = 0
        self.t_end = 0.0
        self.warmup = WARMUP_MIN
        self.classes = []        # (name, count, busy_area, q_area, max_q)
        self.ops_total = 0
        self.cpu_ms = 0.0
        self.series = []         # linhas de queue_timeseries (se pedido)
        self.assignments = []    # (class, slot, start, end, order_id, loan, measured)
        self.completed_ids = []
        self.cancelled_ids = []


def _fresh(o):
    return Order(o.order_id, o.arrival_min, o.dispatch_window_min,
                 o.priority_score, o.size, o.deadline_min, o.seq)


def simulate(orders, events, dock_cfg, impl, params=None, outages=(),
             warmup_min=WARMUP_MIN, borrow=None, backend="heap", sample_dt=None, trace=False):
    """Roda uma simulacao.

    orders: lista de Order ordenada por chegada (nao e modificada).
    events: lista de OrderEvent.
    dock_cfg: dict com 'classes' e 'borrow' (entrada de configs/docks.json).
    sample_dt: se dado, coleta serie temporal (fila/ocupacao por classe).
    trace: guarda atribuicoes doca/pedido (testes de invariantes).
    """
    t_cpu = time.perf_counter()
    params = params or {}
    borrow = dock_cfg.get("borrow", "none") if borrow is None else borrow
    one_way = borrow == "one_way"
    res = SimResult()
    res.warmup = warmup_min

    classes = []
    size_to_class = {}
    for ci, c in enumerate(dock_cfg["classes"]):
        cl = _Class(c["name"], tuple(c["sizes"]), int(c["count"]), make_strategy(impl, backend=backend, **params))
        classes.append(cl)
        for s in c["sizes"]:
            size_to_class[s] = ci
    ncls = len(classes)

    pool = [_fresh(o) for o in orders]
    by_id = dict((o.order_id, o) for o in pool)
    state = {}  # order_id -> 'q' | 'run' | 'done' | 'cancel'
    cls_of = {}

    heap = []
    counter = 0
    for ev in events:
        counter += 1
        heap.append((ev.time_min, P_EVENT, counter, "ev", ev))
    for ou in outages:
        ci = None
        for i, cl in enumerate(classes):
            if cl.name == ou["class"]:
                ci = i
        if ci is None:
            raise ValueError("outage em classe desconhecida: %r" % (ou["class"],))
        counter += 1
        heap.append((ou["start_min"], P_OUT_START, counter, "os", (ci, int(ou["count"]))))
        counter += 1
        heap.append((ou["end_min"], P_OUT_END, counter, "oe", (ci, int(ou["count"]))))
    heapq.heapify(heap)

    n = len(pool)
    ai = 0
    now = 0.0
    last_t = 0.0
    t_end = 0.0
    next_sample = 0.0
    inf = float("inf")
    records = res.records

    def sample_upto(t):
        nonlocal next_sample
        while next_sample < t:
            res.series.append([next_sample] + [len(c.queue) for c in classes] +
                              [c.busy for c in classes])
            next_sample += sample_dt

    def integrate(t):
        # integra fila entre last_t e t, apenas dentro da janela [warmup, inf)
        a = last_t if last_t > warmup_min else warmup_min
        if t > a:
            dt = t - a
            for c in classes:
                c.q_area += len(c.queue) * dt

    def dispatch():
        for ci in range(ncls):
            cl = classes[ci]
            while cl.count - cl.down - cl.busy > 0:
                loan = False
                if len(cl.queue):
                    o = cl.queue.pop(now)
                elif one_way and ci > 0:
                    best = None
                    best_key = None
                    best_cj = -1
                    for cj in range(ci):
                        q = classes[cj].queue
                        if len(q):
                            top = q.peek(now, 1)[0]
                            k = q.key(top, now)
                            if best is None or k < best_key:
                                best, best_key, best_cj = top, k, cj
                    if best is None:
                        break
                    o = classes[best_cj].queue.pop(now)
                    loan = True
                else:
                    break
                start(o, cl, loan)

    def start(o, cl, loan):
        nonlocal counter
        slot = cl.free.pop()
        cl.busy += 1
        end = now + PACK_MIN[o.size]
        state[o.order_id] = "run"
        if loan:
            res.n_loans += 1
        counter += 1
        heapq.heappush(heap, (end, P_DONE, counter, "done", (cl, slot, o, now, loan)))

    while True:
        # proximo evento: chegada ou heap
        if ai < n and (not heap or (pool[ai].arrival_min, P_ARRIVAL) < (heap[0][0], heap[0][1])):
            t = pool[ai].arrival_min
            kind = "arr"
        elif heap:
            t = heap[0][0]
            kind = None
        else:
            break
        if sample_dt:
            sample_upto(t)
        integrate(t)
        now = t
        last_t = t
        if kind == "arr":
            o = pool[ai]
            ai += 1
            res.n_arrivals += 1
            ci = size_to_class[o.size]
            classes[ci].queue.push(o, now)
            state[o.order_id] = "q"
            cls_of[o.order_id] = ci
        else:
            _, _, _, kind, payload = heapq.heappop(heap)
            if kind == "done":
                cl, slot, o, st, loan = payload
                cl.busy -= 1
                cl.free.append(slot)
                state[o.order_id] = "done"
                a = st if st > warmup_min else warmup_min
                if now > a:
                    cl.busy_area += now - a
                if now > t_end:
                    t_end = now
                measured = o.arrival_min >= warmup_min
                if measured:
                    records.append((o, st, now))
                if trace:
                    res.assignments.append((cl.name, slot, st, now, o.order_id, loan, measured))
                    res.completed_ids.append(o.order_id)
            elif kind == "os":
                classes[payload[0]].down += payload[1]
            elif kind == "oe":
                classes[payload[0]].down -= payload[1]
            else:  # "ev": update/cancel
                ev = payload
                if state.get(ev.order_id) == "q":
                    ci = cls_of[ev.order_id]
                    if ev.kind == "cancel":
                        classes[ci].queue.cancel(ev.order_id)
                        state[ev.order_id] = "cancel"
                        if by_id[ev.order_id].arrival_min >= warmup_min:
                            res.n_cancelled += 1
                        if trace:
                            res.cancelled_ids.append(ev.order_id)
                    elif ev.kind == "update":
                        if ev.new_score is not None or ev.new_deadline_min is not None:
                            classes[ci].queue.update(ev.order_id, now, ev.new_score,
                                                     ev.new_deadline_min)
        dispatch()
        if now >= warmup_min:
            for c in classes:
                ql = len(c.queue)
                if ql > c.max_q:
                    c.max_q = ql

    if sample_dt:
        # amostras restantes ate o fim (estado final: tudo vazio)
        sample_upto(t_end + sample_dt)
    res.t_end = t_end
    res.classes = [(c.name, c.count, c.busy_area, c.q_area, c.max_q) for c in classes]
    res.ops_total = sum(c.queue.ops for c in classes)
    res.cpu_ms = (time.perf_counter() - t_cpu) * 1000.0
    res.class_names = [c.name for c in classes]
    return res
