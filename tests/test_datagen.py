import csv
import json
import os
import shutil
import tempfile
import unittest

from mps.datagen import cli
from mps.datagen import config as C
from mps.datagen import generator as G

CFG = C.load_config()
ORDER_HEADER = ["order_id", "arrival_min", "dispatch_window_min", "deadline_min",
                "priority_score", "size_category"]
EVENT_HEADER = ["event_id", "time_min", "order_id", "kind", "new_score", "new_deadline_min"]


def load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def read_csv(path):
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f)), None


class Gen(object):
    cache = {}

    @classmethod
    def get(cls, sid, seed=0):
        key = (sid, seed)
        if key not in cls.cache:
            sc = C.resolve_scenario(CFG, sid)
            o = G.generate_orders(sc, seed)
            e = G.generate_events(sc, o, seed)
            cls.cache[key] = (sc, o, e)
        return cls.cache[key]


class TestCatalog(unittest.TestCase):
    def test_all_contract_scenarios_present(self):
        ids = set(C.scenario_ids(CFG))
        base = {"normal_85", "peak_105", "overload_125", "black_friday", "promo_g_burst",
                "mix_shift_33", "dock_outage", "regional_mix"}
        sweeps = set("sweep_%d" % p for p in range(70, 135, 5))
        self.assertEqual(len(sweeps), 13)
        self.assertTrue((base | sweeps) <= ids)
        for sid in ids:
            sc = C.resolve_scenario(CFG, sid)
            self.assertEqual(sc["dock_config"], "base_15")
            self.assertAlmostEqual(sum(sc["size_mix"].values()), 1.0, places=6)

    def test_seed_sets_disjoint(self):
        self.assertFalse(set(C.EVAL_SEEDS) & set(C.CALIB_SEEDS))
        self.assertEqual(list(C.EVAL_SEEDS), list(range(0, 30)))
        self.assertEqual(list(C.CALIB_SEEDS), list(range(1000, 1010)))
        self.assertEqual(C.parse_seeds("0-2,9"), [0, 1, 2, 9])

    def test_cli_rejects_mixed_seeds(self):
        with self.assertRaises(SystemExit):
            cli.main(["--seeds", "0,1000", "--out", tempfile.gettempdir()])
        with self.assertRaises(SystemExit):
            cli.main(["--calibration", "--seeds", "0"])


SCENARIOS_FAST = ["normal_85", "peak_105", "black_friday", "mix_shift_33", "regional_mix", "promo_g_burst"]


class TestOrders(unittest.TestCase):
    def test_invariants(self):
        for sid in SCENARIOS_FAST:
            sc, orders, _ = Gen.get(sid)
            self.assertGreater(len(orders), 1000)
            prev = -1.0
            ids = set()
            for o in orders:
                self.assertGreaterEqual(o["arrival_min"], prev)
                prev = o["arrival_min"]
                self.assertLess(o["arrival_min"], sc["duration_min"])
                self.assertGreaterEqual(o["dispatch_window_min"], 30.0)
                self.assertLessEqual(o["dispatch_window_min"], 240.0)
                self.assertAlmostEqual(o["deadline_min"], o["arrival_min"] + o["dispatch_window_min"], delta=0.002)
                self.assertTrue(0.0 <= o["priority_score"] <= 100.0)
                self.assertIn(o["size_category"], ("P", "M", "G"))
                ids.add(o["order_id"])
            self.assertEqual(len(ids), len(orders))
            self.assertEqual(orders[0]["order_id"], "O000001")

    def test_vip_fraction(self):
        for sid in SCENARIOS_FAST + ["overload_125", "sweep_70"]:
            _, orders, _ = Gen.get(sid)
            f = sum(1 for o in orders if o["priority_score"] >= 70.0) / float(len(orders))
            self.assertTrue(0.15 <= f <= 0.30, "%s VIP=%.3f" % (sid, f))

    def test_size_mix_matches_manifest(self):
        for sid in SCENARIOS_FAST:
            sc, orders, _ = Gen.get(sid)
            exp = G.expected_size_mix(sc)
            for s in "PMG":
                obs = sum(1 for o in orders if o["size_category"] == s) / float(len(orders))
                self.assertAlmostEqual(obs, exp[s], delta=0.03, msg="%s %s" % (sid, s))

    def test_special_mixes(self):
        sc, _, _ = Gen.get("black_friday")
        self.assertGreater(G.expected_size_mix(sc)["G"], 0.17)
        _, orders, _ = Gen.get("promo_g_burst")
        win = [o for o in orders if 360 <= o["arrival_min"] < 480]
        g = sum(1 for o in win if o["size_category"] == "G") / float(len(win))
        self.assertAlmostEqual(g, 0.40, delta=0.07)
        _, orders, _ = Gen.get("mix_shift_33")
        g = sum(1 for o in orders if o["size_category"] == "G") / float(len(orders))
        self.assertAlmostEqual(g, 0.33, delta=0.03)

    def test_mean_rate_near_target(self):
        for sid in ["normal_85", "peak_105", "overload_125", "black_friday", "regional_mix", "sweep_70"]:
            sc, orders, _ = Gen.get(sid)
            rate = len(orders) / (sc["duration_min"] / 60.0)
            self.assertAlmostEqual(rate / sc["base_rate_per_h"], 1.0, delta=0.05, msg=sid)
        sc, orders, _ = Gen.get("peak_105")
        self.assertEqual(sc["base_rate_per_h"], 504.0)

    def test_daily_profile_has_valleys_and_peaks(self):
        sc, _, _ = Gen.get("normal_85")
        names, per = G.rate_curves(sc)
        hourly = [sum(per[n][k] for n in names) * 60 for k in range(0, 960, 60)]
        self.assertGreater(max(hourly) / min(hourly), 1.8)

    def test_black_friday_plateau(self):
        sc, _, _ = Gen.get("black_friday")
        names, per = G.rate_curves(sc)
        plateau = [sum(per[n][k] for n in names) * 60 for k in range(360, 600)]
        avg = sum(plateau) / len(plateau) / 480.0
        self.assertTrue(1.3 <= avg <= 1.5, avg)

    def test_regional_mix(self):
        sc, orders, _ = Gen.get("regional_mix")
        cnt = {}
        for o in orders:
            cnt[o["region"]] = cnt.get(o["region"], 0) + 1
        self.assertEqual(set(cnt), set(["BR", "MX", "AR", "CO", "CL"]))
        self.assertAlmostEqual(cnt["BR"] / float(len(orders)), 0.45, delta=0.04)
        mean_w = {}
        for r in cnt:
            ws = [o["dispatch_window_min"] for o in orders if o["region"] == r]
            mean_w[r] = sum(ws) / len(ws)
        self.assertLess(mean_w["AR"], mean_w["MX"])  # AR tem SLA mais apertado

    def test_tight_sla_gives_shorter_windows(self):
        _, orders, _ = Gen.get("regional_mix")
        by = {}
        for o in orders:
            by.setdefault(o["sla_min"], []).append(o["dispatch_window_min"])
        keys = sorted(by)
        means = [sum(by[k]) / len(by[k]) for k in keys]
        self.assertEqual(means, sorted(means))

    def test_value_correlates_with_size(self):
        _, orders, _ = Gen.get("normal_85")
        med = {}
        for s in "PMG":
            v = sorted(o["value_brl"] for o in orders if o["size_category"] == s)
            med[s] = v[len(v) // 2]
        self.assertLess(med["P"], med["M"])
        self.assertLess(med["M"], med["G"])

    def test_score_from_components(self):
        _, orders, _ = Gen.get("normal_85")
        for o in orders[:200]:
            s = G.compute_score(o["dispatch_window_min"], o["distance_km"], o["value_brl"], o["seller_reputation"])
            self.assertAlmostEqual(s, o["priority_score"], delta=0.5)


class TestEvents(unittest.TestCase):
    def test_event_rates_and_ranges(self):
        sc, orders, events = Gen.get("normal_85")
        by = dict((o["order_id"], o) for o in orders)
        n = float(len(orders))
        ups = [e for e in events if e[3] == "update"]
        cas = [e for e in events if e[3] == "cancel"]
        self.assertAlmostEqual(len(ups) / n, 0.03, delta=0.01)
        self.assertAlmostEqual(len(cas) / n, 0.02, delta=0.008)
        prev = -1.0
        for eid, t, oid, kind, ns, nd in events:
            o = by[oid]
            self.assertGreaterEqual(t, prev)
            prev = t
            self.assertTrue(o["arrival_min"] <= t <= o["deadline_min"])
            if kind == "update":
                self.assertTrue(ns is not None or nd is not None)
                if nd is not None:
                    self.assertGreater(nd, t)
                if ns is not None:
                    self.assertTrue(0 <= ns <= 100)
        self.assertEqual(len(set(e[0] for e in events)), len(events))

    def test_black_friday_more_updates(self):
        _, o1, e1 = Gen.get("black_friday")
        _, o2, e2 = Gen.get("normal_85")
        r1 = sum(1 for e in e1 if e[3] == "update") / float(len(o1))
        r2 = sum(1 for e in e2 if e[3] == "update") / float(len(o2))
        self.assertGreater(r1, r2 * 1.4)


class TestFilesAndDeterminism(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _run(self, sub, seeds="0,1"):
        out = os.path.join(self.tmp, sub)
        cli.main(["--scenarios", "normal_85,dock_outage", "--seeds", seeds, "--out", out])
        return out

    def test_files_format_and_determinism(self):
        a = self._run("a")
        b = self._run("b")
        for sid in ("normal_85", "dock_outage"):
            for seed in (0, 1):
                for name in ("orders.csv", "events.csv"):
                    pa = os.path.join(a, sid, "seed_%d" % seed, name)
                    pb = os.path.join(b, sid, "seed_%d" % seed, name)
                    with open(pa, "rb") as fa, open(pb, "rb") as fb:
                        self.assertEqual(fa.read(), fb.read())
            with open(os.path.join(a, sid, "manifest.json"), "rb") as fa, \
                    open(os.path.join(b, sid, "manifest.json"), "rb") as fb:
                self.assertEqual(fa.read(), fb.read())
        rows, _ = read_csv(os.path.join(a, "normal_85", "seed_0", "orders.csv"))
        with open(os.path.join(a, "normal_85", "seed_0", "orders.csv")) as f:
            self.assertEqual(f.readline().strip().split(",")[:6], ORDER_HEADER)
        with open(os.path.join(a, "normal_85", "seed_0", "events.csv")) as f:
            self.assertEqual(f.readline().strip().split(","), EVENT_HEADER)
        self.assertGreater(len(rows), 1000)
        r = rows[5]
        self.assertAlmostEqual(float(r["deadline_min"]), float(r["arrival_min"]) + float(r["dispatch_window_min"]), delta=0.002)
        man = load_json(os.path.join(a, "dock_outage", "manifest.json"))
        for k in ("scenario_id", "description", "seeds", "duration_min", "base_rate_per_h", "size_mix",
                  "rate_profile", "dock_config", "outages", "warmup_min", "notes", "seed_stats"):
            self.assertIn(k, man)
        self.assertEqual(man["seeds"], [0, 1])
        self.assertEqual(man["outages"][0]["class"], "pesada")
        st = man["seed_stats"]["0"]
        for k in ("n_orders", "mean_rate_per_h", "pct_vip", "size_mix"):
            self.assertIn(k, st)

    def test_different_seeds_differ_and_manifest_merges(self):
        out = self._run("c", "0")
        cli.main(["--scenarios", "normal_85", "--seeds", "5", "--out", out])
        man = load_json(os.path.join(out, "normal_85", "manifest.json"))
        self.assertEqual(man["seeds"], [0, 5])
        _, o0, _ = Gen.get("normal_85", 0)
        _, o1, _ = Gen.get("normal_85", 1)
        self.assertNotEqual([o["arrival_min"] for o in o0[:20]], [o["arrival_min"] for o in o1[:20]])

    def test_calibration_flag(self):
        out = os.path.join(self.tmp, "cal")
        cli.main(["--scenarios", "sweep_70", "--calibration", "--out", out])
        man = load_json(os.path.join(out, "sweep_70", "manifest.json"))
        self.assertEqual(man["seeds"], list(range(1000, 1010)))


if __name__ == "__main__":
    unittest.main()
