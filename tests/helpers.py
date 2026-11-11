"""Gerador MINIMO de dados so para testes (nao e o mps.datagen)."""
import csv
import json
import os
import random

from mps.models import PACK_MIN, Order, OrderEvent

# 15 docas base_15: capacidade nominal 480/h no mix 50/35/15
CAP_PER_H = 480.0


def gen_orders(seed, load=0.9, duration=480.0, mix=(0.5, 0.35, 0.15), cap=CAP_PER_H):
    """Chegadas Poisson homogeneas; janelas uniformes 30-240; score uniforme."""
    rng = random.Random(seed)
    rate = cap * load / 60.0
    t = 0.0
    out = []
    while True:
        t += rng.expovariate(rate)
        if t >= duration:
            break
        size = rng.choices(["P", "M", "G"], weights=mix)[0]
        win = rng.uniform(30, 240)
        score = rng.uniform(0, 100)
        out.append(Order("O%06d" % (len(out) + 1), t, win, score, size, seq=len(out)))
    return out


def gen_events(orders, seed, p_update=0.03, p_cancel=0.02):
    rng = random.Random(seed + 7919)
    evs = []
    for o in orders:
        r = rng.random()
        if r < p_cancel:
            evs.append(OrderEvent("E%06d" % (len(evs) + 1), o.arrival_min + rng.uniform(0, o.dispatch_window_min),
                                  o.order_id, "cancel"))
        elif r < p_cancel + p_update:
            evs.append(OrderEvent("E%06d" % (len(evs) + 1), o.arrival_min + rng.uniform(0, o.dispatch_window_min),
                                  o.order_id, "update", rng.uniform(0, 100), None))
    evs.sort(key=lambda e: e.time_min)
    return evs


def write_dataset(root, scenario, seeds, load=0.9, duration=480.0, manifest=None, **kw):
    sdir = os.path.join(root, scenario)
    os.makedirs(sdir, exist_ok=True)
    man = {"scenario_id": scenario, "warmup_min": 60, "dock_config": "base_15"}
    man.update(manifest or {})
    with open(os.path.join(sdir, "manifest.json"), "w") as f:
        json.dump(man, f)
    for seed in seeds:
        d = os.path.join(sdir, "seed_%d" % seed)
        os.makedirs(d, exist_ok=True)
        orders = gen_orders(seed, load, duration, **kw)
        with open(os.path.join(d, "orders.csv"), "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["order_id", "arrival_min", "dispatch_window_min", "deadline_min",
                        "priority_score", "size_category"])
            for o in orders:
                w.writerow([o.order_id, o.arrival_min, o.dispatch_window_min, o.deadline_min,
                            o.priority_score, o.size])
        with open(os.path.join(d, "events.csv"), "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["event_id", "time_min", "order_id", "kind", "new_score", "new_deadline_min"])
            for e in gen_events(orders, seed):
                w.writerow([e.event_id, e.time_min, e.order_id, e.kind,
                            "" if e.new_score is None else e.new_score, ""])


def mk(oid, arrival, window, score, size, seq):
    return Order(oid, arrival, window, score, size, seq=seq)
