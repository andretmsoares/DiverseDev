"""Orquestracao: tarefas (cenario, doca, seed) em paralelo e escrita dos CSVs."""
import csv
import datetime
import json
import multiprocessing
import os
import platform
import subprocess
import sys

from mps.sim import loader, metrics
from mps.sim.docks import names as dock_names
from mps.sim.engine import simulate
from mps.strategies import BACKEND_NAMES, STATIC_IMPLS

SAMPLE_DT = 5.0

IDENT_COLS = ["scenario_id", "dock_config", "strategy_id", "backend", "impl", "alpha", "seed"]


def parse_seeds(text):
    seeds = []
    for part in text.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            a, b = part.split("-", 1)
            seeds.extend(range(int(a), int(b) + 1))
        else:
            seeds.append(int(part))
    return seeds


def run_task(task):
    """Worker (nivel de modulo, requisito do Windows): uma seed de um cenario com
    todas as estrategias. Devolve (runs, series, delays) como listas de dicts."""
    scen_dir = os.path.join(task["data"], task["scenario"])
    seed_dir = os.path.join(scen_dir, "seed_%d" % task["seed"])
    orders = loader.load_orders(os.path.join(seed_dir, "orders.csv"))
    events = loader.load_events(os.path.join(seed_dir, "events.csv"))
    runs, series, delays = [], [], []
    for backend, st in task["strategies"]:
        collect = task["seed"] == 0 and backend == "heap"
        res = simulate(orders, events, task["dock_cfg"], st["impl"], st.get("params") or {},
                       outages=task["outages"], warmup_min=task["warmup"],
                       sample_dt=SAMPLE_DT if collect else None, backend=backend)
        row = {"scenario_id": task["scenario"], "dock_config": task["dock_id"],
               "strategy_id": st["id"], "backend": backend, "impl": st["impl"],
               "alpha": (st.get("params") or {}).get("alpha", ""), "seed": task["seed"]}
        row.update(metrics.compute_metrics(res))
        runs.append(row)
        if collect:
            qn, gn = res.queue_names, res.group_names
            for srow in res.series:
                d = {"scenario_id": task["scenario"], "dock_config": task["dock_id"],
                     "strategy_id": st["id"], "seed": task["seed"], "time_min": srow[0]}
                for i, nm in enumerate(qn):
                    d["queue_" + nm] = srow[1 + i]
                for i, nm in enumerate(gn):
                    d["busy_" + nm] = srow[1 + len(qn) + i]
                series.append(d)
            for o, s, comp in res.records:
                delays.append({"scenario_id": task["scenario"], "dock_config": task["dock_id"],
                               "strategy_id": st["id"], "order_id": o.order_id,
                               "size_category": o.size, "is_vip": int(o.is_vip),
                               "delay_min": metrics.delay_of(o, comp),
                               "wait_min": s - o.arrival_min})
    return runs, series, delays


def _git_commit():
    try:
        out = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=loader.ROOT,
                                      stderr=subprocess.DEVNULL)
        return out.decode().strip()
    except Exception:
        return None


def _write_csv(path, cols, rows):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols, restval="", extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow(r)


def run_all(data, out, scenarios, strategy_ids, dock_ids, seeds, workers=1,
            calibration=False, backends=("heap",), argv=None, log=print):
    docks = loader.load_dock_configs()
    all_strats = loader.load_strategies()
    by_id = dict((s["id"], s) for s in all_strats)
    if strategy_ids == "all":
        strats = all_strats
    else:
        strats = []
        for sid in strategy_ids:
            if sid not in by_id:
                raise SystemExit("estrategia desconhecida: %s" % sid)
            strats.append(by_id[sid])
    cfg = loader.load_strategy_config()
    bs_ids = cfg.get("backend_strategies", ["edf", "vd_a1"])
    pairs = []  # (backend, estrategia)
    for b in backends:
        if b not in BACKEND_NAMES:
            raise SystemExit("backend desconhecido: %s" % b)
        if b == "heap":
            pairs.extend((b, s) for s in strats)
        else:
            for s in strats:
                if s["impl"] in STATIC_IMPLS and (strategy_ids != "all" or s["id"] in bs_ids):
                    pairs.append((b, s))
    if scenarios == "all":
        scenarios = sorted(d for d in os.listdir(data)
                           if os.path.isdir(os.path.join(data, d)) and
                           os.path.exists(os.path.join(data, d, "manifest.json")))
    for d in dock_ids:
        if d not in docks:
            raise SystemExit("config de docas desconhecida: %s" % d)

    tasks = []
    for sc in scenarios:
        man = loader.load_manifest(os.path.join(data, sc))
        for d in dock_ids:
            for seed in seeds:
                if not os.path.exists(os.path.join(data, sc, "seed_%d" % seed, "orders.csv")):
                    log("aviso: sem dados para %s seed %d (ignorado)" % (sc, seed))
                    continue
                tasks.append({"data": data, "scenario": sc, "dock_id": d, "seed": seed,
                              "dock_cfg": docks[d], "strategies": pairs,
                              "outages": man.get("outages") or [],
                              "warmup": loader.scenario_warmup(man)})
    log("%d tarefas x %d estrategias" % (len(tasks), len(pairs)))
    if workers > 1 and len(tasks) > 1:
        pool = multiprocessing.Pool(workers)
        try:
            results = pool.map(run_task, tasks, chunksize=1)
        finally:
            pool.close()
            pool.join()
    else:
        results = [run_task(t) for t in tasks]

    order_idx = dict((s["id"], i) for i, s in enumerate(strats))
    bidx = dict((b, i) for i, b in enumerate(backends))
    runs = [r for res in results for r in res[0]]
    series = [r for res in results for r in res[1]]
    delays = [r for res in results for r in res[2]]
    sort_key = lambda r: (r["scenario_id"], r["dock_config"], order_idx[r["strategy_id"]],
                          bidx[r["backend"]], r.get("seed", 0))
    runs.sort(key=sort_key)
    series.sort(key=lambda r: (r["scenario_id"], r["dock_config"], order_idx[r["strategy_id"]],
                               r["time_min"]))
    delays.sort(key=lambda r: (r["scenario_id"], r["dock_config"], order_idx[r["strategy_id"]]))

    gnames, qnames = [], []
    for d in dock_ids:
        gn, qn = dock_names(docks[d])
        gnames.extend(x for x in gn if x not in gnames)
        qnames.extend(x for x in qn if x not in qnames)
    os.makedirs(out, exist_ok=True)
    prefix = "calibration_" if calibration else ""
    _write_csv(os.path.join(out, prefix + "runs.csv"),
               IDENT_COLS + metrics.column_names(gnames, qnames), runs)
    _write_csv(os.path.join(out, prefix + "queue_timeseries.csv"),
               ["scenario_id", "dock_config", "strategy_id", "seed", "time_min"] +
               ["queue_" + n for n in qnames] + ["busy_" + n for n in gnames], series)
    _write_csv(os.path.join(out, prefix + "delays_seed0.csv"),
               ["scenario_id", "dock_config", "strategy_id", "order_id", "size_category",
                "is_vip", "delay_min", "wait_min"], delays)
    meta = {"python": sys.version, "platform": platform.platform(),
            "datetime": datetime.datetime.now().isoformat(),
            "command": " ".join(argv if argv is not None else sys.argv),
            "git_commit": _git_commit(), "scenarios": scenarios,
            "strategies": [s["id"] for s in strats], "backends": list(backends), "dock_configs": dock_ids,
            "seeds": seeds, "calibration": calibration, "n_runs": len(runs),
            "workers": workers}
    with open(os.path.join(out, prefix + "runs.meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2)
    log("escrito: %s (%d linhas)" % (os.path.join(out, prefix + "runs.csv"), len(runs)))
    return runs
