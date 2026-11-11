"""Simulador de eventos discretos (ver docs/CONTRACT.md, secoes 4 e 6)."""
import heapq
import time

from mps.models import PACK_MIN, WARMUP_MIN, Order
from mps.sim.docks import layout
from mps.strategies import make_strategy

# prioridade de desempate para eventos no mesmo instante (menor primeiro)
P_DONE, P_OUT_END, P_OUT_START, P_ARRIVAL, P_EVENT = 0, 1, 2, 3, 4


class _Group(object):
    """Grupo de docas identicas (mesmos tamanhos e velocidade)."""
    __slots__ = ("name", "sizes", "count", "speed", "qidx", "busy", "down", "free",
                 "busy_area", "max_accept")

    def __init__(self, g):
        self.name = g["name"]
        self.sizes = g["sizes"]
        self.count = g["count"]
        self.speed = g["speed"]
        self.qidx = g["queue"]
        self.busy = 0
        self.down = 0
        self.free = list(range(self.count - 1, -1, -1))  # pilha de slots livres
        self.busy_area = 0.0
        self.max_accept = max(PACK_MIN[x] for x in self.sizes)


class _Queue(object):
    __slots__ = ("name", "sizes", "q", "q_area", "max_q")

    def __init__(self, name, sizes, q):
        self.name = name
        self.sizes = sizes
        self.q = q
        self.q_area = 0.0
        self.max_q = 0


class SimResult(object):
    """Saida bruta de uma simulacao; as metricas sao calculadas em metrics.py."""

    def __init__(self):
        self.records = []        # (order, start, completion) de pedidos medidos
        self.n_arrivals = 0
        self.n_cancelled = 0
        self.n_loans = 0
        self.t_end = 0.0
        self.warmup = WARMUP_MIN
        self.groups = []         # (name, count, busy_area) por grupo de docas
        self.queues = []         # (name, q_area, max_q) por fila
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
    if borrow is not None:
        dock_cfg = dict(dock_cfg, borrow=borrow)
    lay = layout(dock_cfg)
    borrow = lay["borrow"]
    one_way = borrow == "one_way"
    best = borrow == "best_eligible"
    res = SimResult()
    res.warmup = warmup_min

    queues = [_Queue(q["name"], q["sizes"], make_strategy(impl, backend=backend, **params))
              for q in lay["queues"]]
    groups = [_Group(g) for g in lay["groups"]]
    size_to_q = {}
    for qi, q in enumerate(queues):
        for sz in q.sizes:
            size_to_q[sz] = qi
    # ordem de despacho: fila (menor primeiro) e, dentro da fila, doca mais rapida
    # primeiro; em best_eligible, a menos capaz primeiro (ordem do arquivo)
    if best:
        gorder = list(groups)
    else:
        gorder = sorted(groups, key=lambda g: (g.qidx, -g.speed))
    ngr = len(groups)
    res.group_names = [g.name for g in groups]
    res.queue_names = [q.name for q in queues]

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
        gi = None
        for i, g in enumerate(lay["groups"]):
            if g["name"] == ou["class"] or g["alias"] == ou["class"]:
                gi = i
        if gi is None:
            # config sem essa classe: com um unico grupo a falha vale para ele;
            # senao e ignorada (documentado em docs/DOCKS.md)
            if ngr == 1:
                gi = 0
            else:
                continue
        counter += 1
        heap.append((ou["start_min"], P_OUT_START, counter, "os", (gi, int(ou["count"]))))
        counter += 1
        heap.append((ou["end_min"], P_OUT_END, counter, "oe", (gi, int(ou["count"]))))
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
            res.series.append([next_sample] + [len(c.q) for c in queues] +
                              [g.busy for g in groups])
            next_sample += sample_dt

    def integrate(t):
        # integra fila entre last_t e t, apenas dentro da janela [warmup, inf)
        a = last_t if last_t > warmup_min else warmup_min
        if t > a:
            dt = t - a
            for c in queues:
                c.q_area += len(c.q) * dt

    def dispatch():
        for gr in gorder:
            while gr.count - gr.down - gr.busy > 0:
                loan = False
                if best:
                    # menor chave entre os topos das filas dos tamanhos aceitos;
                    # desempate: tamanho maior primeiro (G, M, P)
                    cand = None
                    cand_key = None
                    for sz in ("G", "M", "P"):
                        if sz in gr.sizes and sz in size_to_q:
                            q = queues[size_to_q[sz]].q
                            if len(q):
                                top = q.peek(now, 1)[0]
                                k = q.key(top, now)
                                if cand is None or k < cand_key:
                                    cand, cand_key = sz, k
                    if cand is None:
                        break
                    o = queues[size_to_q[cand]].q.pop(now)
                    loan = PACK_MIN[o.size] < gr.max_accept
                else:
                    own = queues[gr.qidx].q
                    if len(own):
                        o = own.pop(now)
                    elif one_way and gr.qidx > 0:
                        bst = None
                        bst_key = None
                        bst_q = -1
                        for qj in range(gr.qidx):
                            q = queues[qj].q
                            if len(q):
                                top = q.peek(now, 1)[0]
                                k = q.key(top, now)
                                if bst is None or k < bst_key:
                                    bst, bst_key, bst_q = top, k, qj
                        if bst is None:
                            break
                        o = queues[bst_q].q.pop(now)
                        loan = True
                    else:
                        break
                start(o, gr, loan)

    def start(o, cl, loan):
        nonlocal counter
        slot = cl.free.pop()
        cl.busy += 1
        end = now + PACK_MIN[o.size] / cl.speed
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
            if o.size not in size_to_q:
                raise ValueError("nenhuma doca aceita o tamanho %r (pedido %s)" % (o.size, o.order_id))
            ci = size_to_q[o.size]
            queues[ci].q.push(o, now)
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
                groups[payload[0]].down += payload[1]
            elif kind == "oe":
                groups[payload[0]].down -= payload[1]
            else:  # "ev": update/cancel
                ev = payload
                if state.get(ev.order_id) == "q":
                    ci = cls_of[ev.order_id]
                    if ev.kind == "cancel":
                        queues[ci].q.cancel(ev.order_id)
                        state[ev.order_id] = "cancel"
                        if by_id[ev.order_id].arrival_min >= warmup_min:
                            res.n_cancelled += 1
                        if trace:
                            res.cancelled_ids.append(ev.order_id)
                    elif ev.kind == "update":
                        if ev.new_score is not None or ev.new_deadline_min is not None:
                            queues[ci].q.update(ev.order_id, now, ev.new_score,
                                                     ev.new_deadline_min)
        # despacha so depois de aplicar TODOS os eventos do mesmo instante
        nxt = inf
        if ai < n:
            nxt = pool[ai].arrival_min
        if heap and heap[0][0] < nxt:
            nxt = heap[0][0]
        if nxt > now:
            dispatch()
        if now >= warmup_min:
            for c in queues:
                ql = len(c.q)
                if ql > c.max_q:
                    c.max_q = ql

    if sample_dt:
        # amostras restantes ate o fim (estado final: tudo vazio)
        sample_upto(t_end + sample_dt)
    res.t_end = t_end
    res.groups = [(g.name, g.count, g.busy_area) for g in groups]
    res.queues = [(q.name, q.q_area, q.max_q) for q in queues]
    res.ops_total = sum(q.q.ops for q in queues)
    res.cpu_ms = (time.perf_counter() - t_cpu) * 1000.0
    return res
