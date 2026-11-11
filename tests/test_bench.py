import csv
import importlib.util
import os
import shutil
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class BenchSmoke(unittest.TestCase):
    def test_bench_runs_small(self):
        spec = importlib.util.spec_from_file_location("bench_sorting", os.path.join(ROOT, "scripts", "bench_sorting.py"))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        tmp = tempfile.mkdtemp()
        try:
            out = os.path.join(tmp, "b.csv")
            mod.main(["--out", out, "--sizes", "100,300", "--budget-s", "0.05"])
            with open(out) as f:
                rows = list(csv.DictReader(f))
            self.assertEqual(rows[0].keys().__len__(), 5)
            self.assertEqual(len(rows), 5 * 2 * 4)
            self.assertEqual(set(r["algorithm"] for r in rows),
                             {"insertion", "selection", "merge", "quick", "heap"})
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
