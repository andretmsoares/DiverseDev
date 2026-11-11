import csv
import json
import os
import shutil
import tempfile
import unittest

from mps.sim import metrics
from mps.sim.engine import simulate
from mps.sim.loader import load_dock_configs
from mps.sim.runner import run_all
from tests.helpers import gen_events, gen_orders, mk, write_dataset

D = load_dock_configs()
HERE = os.path.dirname(os.path.abspath(__file__))


def run(orders, events, cfg, impl="fifo", params=None, **kw):
    kw.setdefault("warmup_min", 0.0)
    kw.setdefault("trace", True)
    r = simulate(orders, events, cfg, impl, params or {}, **kw)
    return r, metrics.compute_metrics(r)


class Regression(unittest.TestCase):
    def test_old_configs_unchanged(self):
        with open(os.path.join(HERE, "golden_docks.json")) as f:
            golden = json.load(f)
        o = gen_orders(7, 1.2, 300)
        e = gen_events(o, 7, 0.05, 0.05)
        out = [{"class": "pesada", "count": 2, "start_min": 100, "end_min": 160}]
        for key, want in golden.items():
            cfg, impl = key.split("|")
            params = {}
            r = simulate(o, e, D[cfg], impl, params, warmup_min=60, outages=out)
            got = metrics.compute_metrics(r)
            got.pop("cpu_ms")
            self.assertEqual(got, want, key)


class Speed(unittest.TestCase):
    def test_service_time_uses_speed(self):
        cfg = {"borrow": "none", "classes": [{"name": "s", "sizes": ["P", "M", "G"], "count": 1, "speed": 0.5}]}
        r, m = run([mk("A", 0, 100, 50, "G", 0)], [], cfg)
        self.assertEqual(r.assignments[0][3], 8.0)

    def test_fastest_dock_first_and_shared_queue(self):
        cfg = D["generic_speed_15"]
        r, m = run([mk("A", 0, 100, 50, "P", 0)], [], cfg)
        self.assertEqual(r.assignments[0][0], "fast")
        self.assertAlmostEqual(r.assignments[0][3], 0.8)
        # 6 pedidos P simultaneos: 5 rapidas + 1 normal
        r, m = run([mk("A%d" % i, 0, 100, 50, "P", i) for i in range(6)], [], cfg)
        used = sorted(a[0] for a in r.assignments)
        self.assertEqual(used, ["fast"] * 5 + ["normal"])
        self.assertEqual(m["n_loans"], 0)
        self.assertIn("max_queue_generica", m)
        self.assertIn("util_slow", m)


class Nested(unittest.TestCase):
    cfg = D["generic_nested_15"]

    def test_eligibility_and_preference(self):
        # 1 pedido P -> small; 5 P -> 4 small + 1 medium; G sempre em large
        r, m = run([mk("A%d" % i, 0, 100, 50, "P", i) for i in range(5)], [], self.cfg)
        self.assertEqual(sorted(a[0] for a in r.assignments), ["medium"] + ["small"] * 4)
        self.assertEqual(m["n_loans"], 1)   # P na medium = doca que aceita mais que P
        r, m = run([mk("G%d" % i, 0, 500, 50, "G", i) for i in range(10)], [], self.cfg)
        self.assertTrue(all(a[0] == "large" for a in r.assignments))
        self.assertEqual(m["n_loans"], 0)
        self.assertEqual(max(a[3] for a in r.assignments), 8.0)  # 6 docas, 10 G de 4 min

    def test_picks_min_key_among_eligible(self):
        cfg = {"borrow": "best_eligible", "classes": [{"name": "large", "sizes": ["P", "M", "G"], "count": 1}]}
        orders = [mk("P", 0, 50, 50, "P", 0), mk("M", 0, 20, 50, "M", 1), mk("G", 0, 30, 50, "G", 2)]
        r, _ = run(orders, [], cfg, "edf")
        self.assertEqual(r.completed_ids, ["M", "G", "P"])
        # docas medium nunca pegam G, mesmo com G de menor chave
        cfg = {"borrow": "best_eligible", "classes": [
            {"name": "medium", "sizes": ["P", "M"], "count": 1},
            {"name": "large", "sizes": ["P", "M", "G"], "count": 1}]}
        orders = [mk("G1", 0, 1, 50, "G", 0), mk("G2", 0, 2, 50, "G", 1), mk("P", 0, 50, 50, "P", 2)]
        r, _ = run(orders, [], cfg, "edf")
        by = dict((a[4], a[0]) for a in r.assignments)
        self.assertEqual(by["G1"], "large")
        self.assertEqual(by["G2"], "large")
        self.assertEqual(by["P"], "medium")

    def test_unservable_size_is_error(self):
        cfg = {"borrow": "best_eligible", "classes": [{"name": "medium", "sizes": ["P", "M"], "count": 1}]}
        with self.assertRaises(ValueError):
            run([mk("G", 0, 1, 50, "G", 0)], [], cfg, "edf")

    def test_outage_alias(self):
        orders = [mk("G%d" % i, 0, 500, 50, "G", i) for i in range(6)]
        out = [{"class": "pesada", "count": 4, "start_min": 0, "end_min": 100}]
        r, _ = run(orders, [], self.cfg, outages=out)
        self.assertEqual(sorted(a[3] for a in r.assignments), [4.0, 4.0, 8.0, 8.0, 12.0, 12.0])


class Invariants(unittest.TestCase):
    def check(self, cfg_id, impl="edf"):
        orders = gen_orders(3, 1.2, 300)
        events = gen_events(orders, 3, 0.1, 0.1)
        out = [{"class": "pesada", "count": 2, "start_min": 100, "end_min": 200}]
        r, m = run(orders, events, D[cfg_id], impl, outages=out, warmup_min=60)
        done = r.completed_ids
        self.assertEqual(len(done), len(set(done)))
        self.assertEqual(set(done) | set(r.cancelled_ids), set(o.order_id for o in orders))
        slots = {}
        for cls, slot, st, en, oid, loan, meas in r.assignments:
            slots.setdefault((cls, slot), []).append((st, en))
        for iv in slots.values():
            iv.sort()
            for (s1, e1), (s2, e2) in zip(iv, iv[1:]):
                self.assertLessEqual(e1, s2 + 1e-12)
        size = dict((o.order_id, o.size) for o in orders)
        if cfg_id == "generic_nested_15":
            for a in r.assignments:
                if size[a[4]] == "G":
                    self.assertEqual(a[0], "large")
                if size[a[4]] == "M":
                    self.assertIn(a[0], ("medium", "large"))
        return m

    def test_new_models(self):
        for c in ("generic_nested_15", "generic_speed_15"):
            for impl in ("fifo", "edf", "composite", "bands_aging"):
                self.check(c, impl)

    def test_determinism(self):
        a = self.check("generic_nested_15", "two_queues")
        b = self.check("generic_nested_15", "two_queues")
        a.pop("cpu_ms"), b.pop("cpu_ms")
        self.assertEqual(a, b)


class Pipeline(unittest.TestCase):
    def test_columns(self):
        tmp = tempfile.mkdtemp()
        try:
            data, out = os.path.join(tmp, "d"), os.path.join(tmp, "o")
            write_dataset(data, "sc", [0], load=1.0, duration=200)
            run_all(data, out, "all", ["fifo", "edf"],
                    ["base_15", "generic_15", "generic_nested_15", "generic_speed_15"],
                    [0], workers=1, log=lambda *a: None)
            with open(os.path.join(out, "runs.csv")) as f:
                rows = list(csv.DictReader(f))
            self.assertEqual(len(rows), 8)
            h = list(rows[0])
            for c in ("util_express", "util_small", "util_fast", "max_queue_P", "mean_queue_G",
                      "max_queue_generica", "max_queue_express"):
                self.assertIn(c, h)
            with open(os.path.join(out, "queue_timeseries.csv")) as f:
                ts = list(csv.DictReader(f))
            self.assertIn("queue_P", ts[0])
            self.assertIn("busy_slow", ts[0])
            self.assertEqual(set(r["dock_config"] for r in ts),
                             {"base_15", "generic_15", "generic_nested_15", "generic_speed_15"})
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
