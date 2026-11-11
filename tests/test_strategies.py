import random
import unittest

from mps.strategies import BACKEND_NAMES, STATIC_IMPLS, make_strategy
from tests.helpers import mk

GUIDE = [("A", 30, 90, "P"), ("B", 70, 55, "G"), ("C", 20, 20, "P")]
EXPECTED_FIRST = {"fifo": "A", "edf": "C", "composite": "B", "two_queues": "B",
                  "bands_aging": "C", "wspt": "A"}
ALL = [("fifo", {}), ("edf", {}), ("composite", {}), ("two_queues", {"urgent_limit_min": 60}),
       ("bands_aging", {"band_min": 30, "aging_pts_per_min": 0.2}), ("wspt", {}),
       ("virtual_deadline", {"alpha": 1})]


def guide_orders():
    return [mk(i, 0.0, dl, sc, sz, n) for n, (i, sc, dl, sz) in enumerate(GUIDE)]


class GuideExample(unittest.TestCase):
    def first(self, impl, **p):
        s = make_strategy(impl, **p)
        for o in guide_orders():
            s.push(o, 0.0)
        return s.pop(0.0).order_id

    def test_each_strategy_picks_expected(self):
        for impl, want in EXPECTED_FIRST.items():
            self.assertEqual(self.first(impl), want, impl)
        self.assertEqual(self.first("virtual_deadline", alpha=1), "B")

    def test_full_orders(self):
        want = {"fifo": "ABC", "edf": "CBA", "wspt": "ACB"}
        for impl, seq in want.items():
            s = make_strategy(impl)
            for o in guide_orders():
                s.push(o, 0.0)
            self.assertEqual("".join(x.order_id for x in s.peek(0.0, 3)), seq)

    def test_vd_alpha0_equals_edf_deadline_order(self):
        rng = random.Random(1)
        orders = [mk("X%d" % i, 0, rng.uniform(10, 200), rng.uniform(0, 100), "PMG"[i % 3], i)
                  for i in range(200)]
        vd = make_strategy("virtual_deadline", alpha=0)
        edf = make_strategy("edf")
        for o in orders:
            vd.push(o, 0)
            edf.push(mk(o.order_id, 0, o.dispatch_window_min, o.priority_score, o.size, o.seq), 0)
        a = [vd.pop(0) for _ in orders]
        b = [edf.pop(0) for _ in orders]
        da = [x.deadline_min for x in a]
        self.assertEqual(da, sorted(da))
        self.assertEqual(da, [x.deadline_min for x in b])


class BasicOps(unittest.TestCase):
    def test_push_pop_update_cancel_peek_len(self):
        for impl, p in ALL:
            for backend in (BACKEND_NAMES if impl in STATIC_IMPLS else ("heap",)):
                s = make_strategy(impl, backend=backend, **p)
                self.assertIsNone(s.pop(0.0))
                self.assertEqual(s.peek(0.0, 3), [])
                for o in guide_orders():
                    s.push(o, 0.0)
                self.assertEqual(len(s), 3)
                self.assertIn("A", s)
                self.assertEqual(len(s.peek(0.0, 2)), 2)
                self.assertEqual(len(s.peek(0.0, 10)), 3)
                self.assertEqual(len(s), 3)  # peek nao remove
                self.assertTrue(s.cancel("B"))
                self.assertFalse(s.cancel("B"))
                self.assertNotIn("B", s)
                self.assertFalse(s.update("ZZ", 0.0, new_score=1))
                self.assertTrue(s.update("A", 0.0, new_score=99, new_deadline_min=1.0))
                self.assertEqual(s.pop(0.0).order_id, "A" if impl != "fifo" else "A")
                got = s.pop(0.0)
                self.assertEqual(got.order_id, "C")
                self.assertIsNone(s.pop(0.0))
                self.assertGreater(s.ops, 0, (impl, backend))

    def test_update_changes_order_edf(self):
        s = make_strategy("edf")
        for o in guide_orders():
            s.push(o, 0.0)
        s.update("A", 0.0, new_deadline_min=5.0)
        self.assertEqual(s.pop(0.0).order_id, "A")

    def test_overdue_orders_ok(self):
        for impl, p in ALL:
            s = make_strategy(impl, **p)
            s.push(mk("L", 0, 10, 50, "P", 0), 0)
            s.push(mk("M", 0, 500, 90, "P", 1), 0)
            s.push(mk("N", 0, 10, 0, "G", 2), 0)
            now = 100.0  # L e N ja estao atrasados
            ks = [s.key(o, now) for o in s.peek(now, 3)]
            self.assertEqual(len(ks), 3)
            out = [s.pop(now) for _ in range(3)]
            self.assertEqual(sorted(o.order_id for o in out), ["L", "M", "N"], impl)

    def test_unknown(self):
        with self.assertRaises(ValueError):
            make_strategy("nope")
        with self.assertRaises(ValueError):
            make_strategy("composite", backend="quick")


def run_random_ops(strategy, seed, n_ops=400):
    """Opera aleatoriamente; devolve a sequencia de ids despachados e checa contra
    a referencia de forca bruta (min de key(o, now) entre os vivos)."""
    rng = random.Random(seed)
    live = {}
    now = 0.0
    seq = 0
    out = []
    for _ in range(n_ops):
        now += rng.uniform(0, 3)
        r = rng.random()
        if r < 0.5 or not live:
            seq += 1
            o = mk("O%d" % seq, now, rng.uniform(5, 150), rng.choice([rng.uniform(0, 100), 50.0]),
                   rng.choice("PMG"), seq)
            strategy.push(o, now)
            live[o.order_id] = o
        elif r < 0.75:
            oid = rng.choice(sorted(live))
            sc = rng.uniform(0, 100)
            dl = live[oid].deadline_min + rng.uniform(-30, 30)
            strategy.update(oid, now, new_score=sc, new_deadline_min=dl)
        elif r < 0.85:
            oid = rng.choice(sorted(live))
            assert strategy.cancel(oid)
            del live[oid]
        else:
            want = min(live.values(), key=lambda o: strategy.key(o, now))
            top = strategy.peek(now, 1)[0]
            assert top.order_id == want.order_id, (top.order_id, want.order_id)
            got = strategy.pop(now)
            assert got.order_id == want.order_id
            del live[got.order_id]
            out.append(got.order_id)
        assert len(strategy) == len(live)
    return out


class Reference(unittest.TestCase):
    def test_match_bruteforce(self):
        cases = ALL[:2] + ALL[3:]  # composite abaixo, com refresh_min=0
        for impl, p in cases:
            for backend in (BACKEND_NAMES if impl in STATIC_IMPLS else ("heap",)):
                for seed in range(3):
                    run_random_ops(make_strategy(impl, backend=backend, **p), seed)
        for seed in range(3):
            run_random_ops(make_strategy("composite", refresh_min=0), seed)

    def test_backends_same_dispatch_order(self):
        for impl, p in ALL:
            if impl not in STATIC_IMPLS:
                continue
            ref = run_random_ops(make_strategy(impl, **p), 11, 600)
            for b in BACKEND_NAMES:
                self.assertEqual(run_random_ops(make_strategy(impl, backend=b, **p), 11, 600),
                                 ref, (impl, b))

    def test_composite_default_refresh_is_close_to_exact(self):
        # com refresh de 1 min o topo nao pode divergir muito: so checa integridade
        s = make_strategy("composite")
        rng = random.Random(3)
        for i in range(300):
            s.push(mk("O%d" % i, i * 0.1, rng.uniform(20, 200), rng.uniform(0, 100), "P", i), i * 0.1)
        ids = set()
        now = 40.0
        while len(s):
            ids.add(s.pop(now).order_id)
            now += 0.1
        self.assertEqual(len(ids), 300)


class Properties(unittest.TestCase):
    def test_virtual_deadline_bounded_overtaking(self):
        for alpha in (0.5, 1.0, 3.0):
            rng = random.Random(5)
            s = make_strategy("virtual_deadline", alpha=alpha)
            live = {}
            now = 0.0
            for i in range(1500):
                now += rng.uniform(0, 1)
                o = mk("O%d" % i, now, rng.uniform(30, 240), rng.uniform(0, 100), "P", i)
                s.push(o, now)
                live[o.order_id] = o
                if rng.random() < 0.6:
                    y = s.pop(now)
                    del live[y.order_id]
                    # y ultrapassou todos os que continuam na fila
                    for x in live.values():
                        self.assertLess(y.deadline_min, x.deadline_min + 100 * alpha + 1e-9)
                        self.assertLessEqual(y.deadline_min - alpha * y.priority_score,
                                             x.deadline_min - alpha * x.priority_score + 1e-9)

    def test_ops_counter_grows_with_n(self):
        small = make_strategy("edf")
        big = make_strategy("edf")
        rng = random.Random(0)
        for i in range(100):
            small.push(mk("A%d" % i, 0, rng.uniform(1, 100), 10, "P", i), 0)
        for i in range(5000):
            big.push(mk("A%d" % i, 0, rng.uniform(1, 100), 10, "P", i), 0)
        self.assertGreater(big.ops, small.ops)

    def test_backend_cost_ordering(self):
        # lista ordenada (insertion) custa mais por push que heap em fila grande
        rng = random.Random(2)
        h = make_strategy("edf")
        ins = make_strategy("edf", backend="insertion")
        for i in range(2000):
            dl = rng.uniform(1, 1000)
            h.push(mk("A%d" % i, 0, dl, 10, "P", i), 0)
            ins.push(mk("A%d" % i, 0, dl, 10, "P", i), 0)
        self.assertGreater(ins.ops, 10 * h.ops)

    def test_quick_no_recursion_on_sorted_input(self):
        s = make_strategy("fifo", backend="quick")
        for i in range(3000):  # pivo fixo + entrada ordenada: pior caso, sem estourar a pilha
            s.push(mk("A%d" % i, 0, 100, 10, "P", i), 0)
            if i == 2999:
                self.assertEqual(s.pop(0).order_id, "A0")


if __name__ == "__main__":
    unittest.main()
