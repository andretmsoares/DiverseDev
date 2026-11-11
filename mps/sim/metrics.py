"""Metricas por run (ver docs/CONTRACT.md, secao 6).

Convencoes (ver docs/STRATEGIES.md): percentuais em 0-100; atraso medido contra
o prazo vigente na conclusao (apos eventual update); percentis por interpolacao
linear sobre TODOS os pedidos medidos (incluindo atraso 0).
"""
from mps.models import SIZES


def percentile(sorted_vals, p):
    if not sorted_vals:
        return 0.0
    if len(sorted_vals) == 1:
        return float(sorted_vals[0])
    pos = (len(sorted_vals) - 1) * p / 100.0
    lo = int(pos)
    hi = min(lo + 1, len(sorted_vals) - 1)
    return sorted_vals[lo] + (sorted_vals[hi] - sorted_vals[lo]) * (pos - lo)


def _mean(xs):
    return sum(xs) / len(xs) if xs else 0.0


def column_names(class_names):
    cols = ["n_orders", "n_late", "pct_late", "mean_delay_min", "mean_delay_late_min",
            "p95_delay_min", "p99_delay_min", "max_delay_min", "n_vip", "vip_pct_late",
            "throughput_per_h", "mean_wait_min",
            "delay_mean_P", "delay_mean_M", "delay_mean_G",
            "pct_late_P", "pct_late_M", "pct_late_G"]
    cols += ["util_" + c for c in class_names]
    cols += ["idle_pct", "n_loans"]
    cols += ["max_queue_" + c for c in class_names]
    cols += ["mean_queue_" + c for c in class_names]
    cols += ["ops_total", "ops_per_order", "cpu_ms", "n_cancelled"]
    return cols


def delay_of(order, completion):
    d = completion - order.deadline_min
    return d if d > 0 else 0.0


def compute_metrics(res):
    """Devolve dict com as colunas de metricas de um SimResult."""
    delays = []
    waits = []
    by_size = dict((s, []) for s in SIZES)
    vip_total = vip_late = 0
    for o, st, comp in res.records:
        d = delay_of(o, comp)
        delays.append(d)
        waits.append(st - o.arrival_min)
        by_size[o.size].append(d)
        if o.priority_score >= 70.0:
            vip_total += 1
            if d > 0:
                vip_late += 1
    n = len(delays)
    late = [d for d in delays if d > 0]
    sd = sorted(delays)
    window = res.t_end - res.warmup
    m = {
        "n_orders": n,
        "n_late": len(late),
        "pct_late": 100.0 * len(late) / n if n else 0.0,
        "mean_delay_min": _mean(delays),
        "mean_delay_late_min": _mean(late),
        "p95_delay_min": percentile(sd, 95),
        "p99_delay_min": percentile(sd, 99),
        "max_delay_min": sd[-1] if sd else 0.0,
        "n_vip": vip_total,
        "vip_pct_late": 100.0 * vip_late / vip_total if vip_total else 0.0,
        "throughput_per_h": n / (window / 60.0) if window > 0 else 0.0,
        "mean_wait_min": _mean(waits),
    }
    for s in SIZES:
        ds = by_size[s]
        m["delay_mean_" + s] = _mean(ds)
        m["pct_late_" + s] = 100.0 * sum(1 for d in ds if d > 0) / len(ds) if ds else 0.0
    busy_tot = cap_tot = 0.0
    for name, count, busy_area, q_area, max_q in res.classes:
        cap = count * window if window > 0 else 0.0
        m["util_" + name] = busy_area / cap if cap else 0.0
        m["max_queue_" + name] = max_q
        m["mean_queue_" + name] = q_area / window if window > 0 else 0.0
        busy_tot += busy_area
        cap_tot += cap
    m["idle_pct"] = 100.0 * (1.0 - busy_tot / cap_tot) if cap_tot else 0.0
    m["n_loans"] = res.n_loans
    m["ops_total"] = res.ops_total
    m["ops_per_order"] = res.ops_total / res.n_arrivals if res.n_arrivals else 0.0
    m["cpu_ms"] = res.cpu_ms
    m["n_cancelled"] = res.n_cancelled
    return m
