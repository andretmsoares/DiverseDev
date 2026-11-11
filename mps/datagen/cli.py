"""CLI: python -m mps.datagen --scenarios all --seeds 0-29 --out data/synthetic [--calibration]."""
import argparse
import json
import os
import sys

from mps.datagen import config as cfgmod
from mps.datagen import generator as gen

ORDER_COLS = ["order_id", "arrival_min", "dispatch_window_min", "deadline_min", "priority_score",
              "size_category", "region", "distance_km", "sla_min", "value_brl", "seller_reputation"]
EVENT_COLS = ["event_id", "time_min", "order_id", "kind", "new_score", "new_deadline_min"]


def _fmt(v):
    if v is None:
        return ""
    if isinstance(v, float):
        return repr(v)
    return str(v)


def write_seed(sc, seed, out_dir):
    """Gera e grava orders.csv e events.csv de uma seed; devolve o resumo estatistico."""
    orders = gen.generate_orders(sc, seed)
    events = gen.generate_events(sc, orders, seed)
    d = os.path.join(out_dir, sc["scenario_id"], "seed_%d" % seed)
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "orders.csv"), "w", encoding="utf-8", newline="") as f:
        f.write(",".join(ORDER_COLS) + "\n")
        for o in orders:
            f.write(",".join(_fmt(o[c]) for c in ORDER_COLS) + "\n")
    with open(os.path.join(d, "events.csv"), "w", encoding="utf-8", newline="") as f:
        f.write(",".join(EVENT_COLS) + "\n")
        for e in events:
            f.write(",".join(_fmt(x) for x in e) + "\n")
    return gen.summarize(sc, orders, events)


def build_manifest(sc, seeds, stats, previous=None):
    """Manifest do cenario; mescla seeds/estatisticas de execucoes anteriores."""
    all_stats = {}
    if previous:
        all_stats.update(previous.get("seed_stats", {}))
    for s in seeds:
        all_stats[str(s)] = stats[s]
    all_seeds = sorted(int(k) for k in all_stats)
    exp_mix = gen.expected_size_mix(sc)
    names, per = gen.rate_curves(sc)
    dur = int(sc["duration_min"])
    tot = [sum(per[n][k] for n in names) * 60.0 for k in range(dur)]
    return {
        "scenario_id": sc["scenario_id"],
        "description": sc["description"],
        "seeds": all_seeds,
        "duration_min": sc["duration_min"],
        "base_rate_per_h": sc["base_rate_per_h"],
        "load_pct": sc["load_pct"],
        "nominal_capacity_per_h": 480,
        "size_mix": sc["size_mix"],
        "expected_size_mix": dict((k, round(v, 4)) for k, v in exp_mix.items()),
        "mix_windows": sc["mix_windows"],
        "rate_profile": "%s (media 1; rate_knots=%s; regioes=%s)" % (
            sc["profile"], json.dumps(sc["rate_knots"]),
            ",".join("%s:%.2f" % (n, sc["regions"][n]["share"]) for n in sorted(sc["regions"]))),
        "rate_per_h_min_max": [round(min(tot), 1), round(max(tot), 1)],
        "dock_config": sc["dock_config"],
        "outages": sc["outages"],
        "warmup_min": sc["warmup_min"],
        "update_prob": sc["update_prob"],
        "cancel_prob": sc["cancel_prob"],
        "notes": sc.get("notes", ""),
        "seed_stats": dict((str(k), all_stats[str(k)]) for k in all_seeds),
    }


def write_manifest(sc, seeds, stats, out_dir):
    path = os.path.join(out_dir, sc["scenario_id"], "manifest.json")
    prev = None
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            prev = json.load(f)
    man = build_manifest(sc, seeds, stats, prev)
    with open(path, "w", encoding="utf-8", newline="") as f:
        json.dump(man, f, indent=2, sort_keys=False)
        f.write("\n")
    return man


def main(argv=None):
    p = argparse.ArgumentParser(prog="python -m mps.datagen", description="Gera dados sinteticos da VelozMart MPS")
    p.add_argument("--scenarios", default="all", help="'all' ou lista separada por virgula")
    p.add_argument("--seeds", default=None, help="ex.: 0-29 ou 0,5,9 (padrao 0-29)")
    p.add_argument("--out", default="data/synthetic")
    p.add_argument("--calibration", action="store_true", help="usa as seeds de calibracao 1000-1009")
    p.add_argument("--config", default=None, help="caminho alternativo de scenarios.json")
    a = p.parse_args(argv)

    cfg = cfgmod.load_config(a.config)
    if a.calibration:
        if a.seeds is not None:
            p.error("--calibration ja define as seeds (1000-1009); nao combine com --seeds")
        seeds = list(cfgmod.CALIB_SEEDS)
    else:
        seeds = cfgmod.parse_seeds(a.seeds if a.seeds is not None else "0-29")
    ev, cal = set(cfgmod.EVAL_SEEDS), set(cfgmod.CALIB_SEEDS)
    if any(s in ev for s in seeds) and any(s in cal for s in seeds):
        p.error("nao misture seeds de avaliacao (0-29) e de calibracao (1000-1009)")

    ids = cfgmod.scenario_ids(cfg) if a.scenarios == "all" else [x.strip() for x in a.scenarios.split(",") if x.strip()]
    for sid in ids:
        if sid not in cfg["scenarios"]:
            p.error("cenario desconhecido: %s" % sid)

    for sid in ids:
        sc = cfgmod.resolve_scenario(cfg, sid)
        stats = {}
        for s in seeds:
            stats[s] = write_seed(sc, s, a.out)
        man = write_manifest(sc, seeds, stats, a.out)
        last = stats[seeds[-1]]
        print("%-14s seeds=%d  n=%d  %.1f/h  VIP=%.1f%%" % (
            sid, len(seeds), last["n_orders"], last["mean_rate_per_h"], last["pct_vip"]))
        sys.stdout.flush()
    return 0
