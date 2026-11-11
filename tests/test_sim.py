import csv
import json
import os
import shutil
import tempfile
import time
import unittest

from mps.models import OrderEvent
from mps.sim import metrics
from mps.sim.engine import simulate
from mps.sim.loader import load_dock_configs, load_strategies
from mps.sim.runner import parse_seeds, run_all
from tests.helpers import gen_events, gen_orders, mk, write_dataset

ONE = {"borrow": "none", "classes": [{"name": "g", "sizes": ["P", "M", "G"], "count": 1}]}
TWO = {"borrow": "one_way", "classes": [{"name": "small", "sizes": ["P"], "count": 1},
                                        {"name": "big", "sizes": ["M"], "count": 1}]}
DOCKS = load_dock_configs()


def run(orders, events, cfg, impl="fifo", params=None, **kw):
    kw.setdefault("warmup_min", 0.0)
    kw.setdefault("trace", True)
    r = simulate(orders, events, cfg, impl, params or {}, **kw)
    return r, metrics.compute_metrics(r)


class HandComputed(unittest.TestCase):
    def orders(self):
        return [mk("O1", 0, 10, 50, "G", 0), mk("O2", 0, 5, 50, "M", 1), mk("O3", 1, 100, 50, "P", 2)]

    def test_fifo(self):
        r, m = run(self.orders(), [], ONE, "fifo")
        self.assertEqual(m["n_orders"], 3)
        self.assertEqual(m["n_late"], 1)
        self.assertAlmostEqual(m["pct_late"], 100.0 / 3)
        self.assertAlmostEqual(m["mean_delay_min"], 1.0 / 3)
        self.assertAlmostEqual(m["mean_delay_late_min"], 1.0)
        self.assertAlmostEqual(m["max_delay_min"], 1.0)
        self.assertAlmostEqual(m["mean_wait_min"], 3.0)   # 0, 4, 5
        self.assertAlmostEqual(m["throughput_per_h"], 3 / (7 / 60.0))
        self.assertAlmostEqual(m["util_g"], 1.0)
        self.assertAlmostEqual(m["idle_pct"], 0.0)
        self.assertAlmostEqual(m["delay_mean_M"], 1.0)
        self.assertAlmostEqual(m["pct_late_M"], 100.0)
        self.assertAlmostEqual(m["pct_late_G"], 0.0)

    def test_edf_no_delay(self):
        r, m = run(self.orders(), [], ONE, "edf")
        self.assertEqual(m["n_late"], 0)
        self.assertAlmostEqual(m["mean_wait_min"], 7.0 / 3)  # 0, 2, 5

    def test_warmup_excludes_early_arrivals(self):
        r, m = run(self.orders(), [], ONE, "fifo", warmup_min=1.0)
        self.assertEqual(m["n_orders"], 1)      # so O3 (chegada 1)
        self.assertEqual(m["n_late"], 0)
        self.assertAlmostEqual(m["throughput_per_h"], 1 / (6 / 60.0))
        self.assertEqual(len(r.completed_ids), 3)  # warm-up executa

    def test_update_deadline_changes_dispatch(self):
        orders = [mk("A", 0, 100, 50, "G", 0), mk("B", 0.5, 99.5, 50, "P", 1), mk("C", 0.5, 49.5, 50, "P", 2)]
        ev = [OrderEvent("E1", 1.0, "B", "update", None, 10.0)]
        r, m = run(orders, ev, ONE, "edf")
        self.assertEqual(r.completed_ids, ["A", "B", "C"])
        r2, _ = run(orders, [], ONE, "edf")
        self.assertEqual(r2.completed_ids, ["A", "C", "B"])

    def test_cancel(self):
        orders = [mk("A", 0, 100, 50, "G", 0), mk("B", 0, 100, 50, "P", 1)]
        ev = [OrderEvent("E1", 1.0, "B", "cancel"), OrderEvent("E2", 1.0, "A", "cancel")]
        r, m = run(orders, ev, ONE, "fifo")
        self.assertEqual(r.completed_ids, ["A"])   # A ja em embalagem: nao cancela
        self.assertEqual(r.cancelled_ids, ["B"])
        self.assertEqual(m["n_orders"], 1)
        self.assertEqual(m["n_cancelled"], 1)


class Docks(unittest.TestCase):
    def test_loan_only_from_smaller(self):
        orders = [mk("A", 0, 100, 50, "P", 0), mk("B", 0, 100, 50, "P", 1)]
        r, m = run(orders, [], TWO, "fifo")
        self.assertEqual(m["n_loans"], 1)
        ends = dict((a[4], (a[0], a[3])) for a in r.assignments)
        self.assertEqual(ends["A"], ("small", 1.0))
        self.assertEqual(ends["B"], ("big", 1.0))   # emprestada, mesmo instante
        # o contrario nunca acontece: classe pequena nao pega M
        orders = [mk("A", 0, 100, 50, "M", 0), mk("B", 0, 100, 50, "M", 1)]
        r, m = run(orders, [], TWO, "fifo")
        self.assertEqual(m["n_loans"], 0)
        ends = dict((a[4], (a[0], a[3])) for a in r.assignments)
        self.assertEqual(ends["B"], ("big", 4.0))

    def test_no_borrow_config(self):
        cfg = dict(TWO, borrow="none")
        r, m = run([mk("A", 0, 100, 50, "P", 0), mk("B", 0, 100, 50, "P", 1)], [], cfg)
        self.assertEqual(m["n_loans"], 0)
        self.assertEqual(max(a[3] for a in r.assignments), 2.0)

    def test_loan_takes_min_key_across_smaller_queues(self):
        cfg = {"borrow": "one_way", "classes": [
            {"name": "s1", "sizes": ["P"], "count": 1}, {"name": "s2", "sizes": ["M"], "count": 1},
            {"name": "s3", "sizes": ["G"], "count": 1}]}
        # s1 e s2 ocupadas; chegam P(dl 90) e M(dl 50): doca G livre empresta o de menor chave (EDF)
        orders = [mk("P0", 0, 500, 50, "P", 0), mk("M0", 0, 500, 50, "M", 1),
                  mk("P1", 0.1, 90, 50, "P", 2), mk("M1", 0.1, 50, 50, "M", 3)]
        r, m = run(orders, [], cfg, "edf")
        by = dict((a[4], a) for a in r.assignments)
        self.assertEqual(by["M1"][0], "s3")
        self.assertTrue(by["M1"][5])

    def test_outage_idle_and_busy(self):
        cfg = {"borrow": "none", "classes": [{"name": "g", "sizes": ["P", "M", "G"], "count": 1}]}
        orders = [mk("A", 0, 100, 50, "P", 0), mk("B", 0.2, 100, 50, "P", 1)]
        out = [{"class": "g", "count": 1, "start_min": 0.5, "end_min": 5.0}]
        r, m = run(orders, [], cfg, "fifo", outages=out)
        by = dict((a[4], a) for a in r.assignments)
        self.assertEqual(by["A"][3], 1.0)            # termina o pedido em curso
        self.assertEqual((by["B"][2], by["B"][3]), (5.0, 6.0))   # so volta no end_min

    def test_outage_reduces_capacity(self):
        cfg = {"borrow": "none", "classes": [{"name": "g", "sizes": ["P"], "count": 2}]}
        orders = [mk("O%d" % i, 0, 100, 50, "P", i) for i in range(4)]
        out = [{"class": "g", "count": 1, "start_min": 0, "end_min": 100}]
        r, _ = run(orders, [], cfg, "fifo", outages=out)
        self.assertEqual(sorted(a[3] for a in r.assignments), [1.0, 2.0, 3.0, 4.0])


class Invariants(unittest.TestCase):
    def check(self, impl, params, backend="heap"):
        orders = gen_orders(3, 1.2, 300)
        events = gen_events(orders, 3, 0.1, 0.1)
        out = [{"class": "pesada", "count": 2, "start_min": 100, "end_min": 200}]
        r, m = run(orders, events, DOCKS["base_15"], impl, params, outages=out,
                   backend=backend, warmup_min=60)
        done = r.completed_ids
        self.assertEqual(len(done), len(set(done)))
        self.assertEqual(set(done) | set(r.cancelled_ids), set(o.order_id for o in orders))
        self.assertFalse(set(done) & set(r.cancelled_ids))
        slots = {}
        for cls, slot, st, en, oid, loan, meas in r.assignments:
            slots.setdefault((cls, slot), []).append((st, en))
        for iv in slots.values():
            iv.sort()
            for (s1, e1), (s2, e2) in zip(iv, iv[1:]):
                self.assertLessEqual(e1, s2 + 1e-12)
        # durante a falha, no maximo 3 das 5 Pesadas atendem
        for t in (101.0, 150.0, 199.0):
            busy = sum(1 for a in r.assignments if a[0] == "pesada" and a[2] <= t < a[3])
            self.assertLessEqual(busy, 3)
        return m

    def test_all_strategies(self):
        for s in load_strategies():
            self.check(s["impl"], s["params"])

    def test_backends(self):
        for b in ("insertion", "selection", "merge", "quick"):
            self.check("edf", {}, b)

    def test_backends_same_metrics(self):
        orders = gen_orders(4, 1.1, 200)
        events = gen_events(orders, 4)
        ref = None
        for b in ("heap", "insertion", "selection", "merge", "quick"):
            _, m = run(orders, events, DOCKS["base_15"], "edf", backend=b, warmup_min=60)
            m = dict((k, v) for k, v in m.items() if k not in ("cpu_ms", "ops_total", "ops_per_order"))
            if ref is None:
                ref = m
            self.assertEqual(m, ref, b)

    def test_determinism(self):
        orders = gen_orders(5, 1.1, 200)
        events = gen_events(orders, 5)
        a = run(orders, events, DOCKS["base_15"], "composite")[1]
        b = run(orders, events, DOCKS["base_15"], "composite")[1]
        a.pop("cpu_ms"), b.pop("cpu_ms")
        self.assertEqual(a, b)

    def test_input_orders_not_mutated(self):
        orders = gen_orders(6, 1.1, 100)
        snap = [(o.deadline_min, o.priority_score) for o in orders]
        run(orders, gen_events(orders, 6, 0.3, 0.0), DOCKS["base_15"], "edf")
        self.assertEqual(snap, [(o.deadline_min, o.priority_score) for o in orders])


class Sanity(unittest.TestCase):
    def pct(self, load):
        orders = gen_orders(0, load, 600)
        events = gen_events(orders, 0)
        res = {}
        for impl in ("fifo", "edf", "composite", "two_queues", "bands_aging", "wspt"):
            res[impl] = run(orders, events, DOCKS["base_15"], impl, warmup_min=60, trace=False)[1]["pct_late"]
        return res

    def test_low_load_nearly_no_delays(self):
        for impl, p in self.pct(0.6).items():
            self.assertLess(p, 1.0, impl)

    def test_overload_fifo_worse_than_edf(self):
        p = self.pct(1.25)
        self.assertGreater(p["fifo"], p["edf"] + 2.0)

    def test_performance_smoke(self):
        orders = gen_orders(0, 1.25, 960)   # ~9 mil pedidos
        events = gen_events(orders, 0)
        for s in load_strategies():
            t = time.time()
            run(orders, events, DOCKS["base_15"], s["impl"], s["params"], trace=False, warmup_min=60)
            self.assertLess(time.time() - t, 20.0, s["id"])


class EndToEnd(unittest.TestCase):
    def test_cli_pipeline(self):
        tmp = tempfile.mkdtemp()
        try:
            data = os.path.join(tmp, "data")
            out = os.path.join(tmp, "results")
            write_dataset(data, "sc_a", [0, 1], load=1.0, duration=200)
            write_dataset(data, "sc_out", [0], load=0.8, duration=200,
                          manifest={"outages": [{"class": "pesada", "count": 2,
                                                 "start_min": 80, "end_min": 140}]})
            run_all(data, out, "all", ["fifo", "edf", "vd_a1"], ["base_15", "generic_15"],
                    [0, 1], workers=2, backends=["heap", "merge"], log=lambda *a: None)
            with open(os.path.join(out, "runs.csv")) as f:
                rows = list(csv.DictReader(f))
            header = list(rows[0].keys())
            self.assertEqual(header[:7], ["scenario_id", "dock_config", "strategy_id", "backend",
                                          "impl", "alpha", "seed"])
            for col in ("util_express", "util_generica", "max_queue_pesada", "mean_queue_padrao",
                        "ops_per_order", "cpu_ms", "n_cancelled", "p99_delay_min", "pct_late_G"):
                self.assertIn(col, header)
            # (sc_a: 2 seeds + sc_out: 1 seed) x 2 docas x (3 heap + 3 merge)
            self.assertEqual(len(rows), 3 * 2 * 6)
            for name in ("queue_timeseries.csv", "delays_seed0.csv", "runs.meta.json"):
                self.assertTrue(os.path.exists(os.path.join(out, name)), name)
            with open(os.path.join(out, "queue_timeseries.csv")) as f:
                ts = list(csv.DictReader(f))
            self.assertEqual(set(r["seed"] for r in ts), {"0"})
            self.assertEqual(float(ts[1]["time_min"]) - float(ts[0]["time_min"]), 5.0)
            with open(os.path.join(out, "runs.meta.json")) as f:
                self.assertIn("command", json.load(f))
            # heap e merge => mesmas metricas
            by = {}
            for r in rows:
                by.setdefault((r["scenario_id"], r["dock_config"], r["strategy_id"], r["seed"]), {})[r["backend"]] = r
            for k, d in by.items():
                self.assertEqual(d["heap"]["pct_late"], d["merge"]["pct_late"], k)
                self.assertEqual(d["heap"]["n_orders"], d["merge"]["n_orders"], k)
            # determinismo entre execucoes e entre n. de workers
            out2 = os.path.join(tmp, "r2")
            run_all(data, out2, "all", ["fifo", "edf", "vd_a1"], ["base_15", "generic_15"],
                    [0, 1], workers=1, backends=["heap", "merge"], log=lambda *a: None)
            with open(os.path.join(out2, "runs.csv")) as f:
                rows2 = list(csv.DictReader(f))
            strip = lambda rs: [dict((k, v) for k, v in r.items() if k not in ("cpu_ms",)) for r in rs]
            self.assertEqual(strip(rows), strip(rows2))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_parse_seeds(self):
        self.assertEqual(parse_seeds("0-3"), [0, 1, 2, 3])
        self.assertEqual(parse_seeds("0,5,9"), [0, 5, 9])


if __name__ == "__main__":
    unittest.main()
