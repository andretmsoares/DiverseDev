#!/usr/bin/env python
"""Junta as saidas de varias execucoes de `mps.sim` (cada uma em uma pasta) em um unico `results/`.

Uso: python scripts/merge_results.py --out results part_a part_b ...
Concatena runs.csv, queue_timeseries.csv e delays_seed0.csv (uniao das colunas) e
guarda as metas em runs.meta.json (lista).
"""
import argparse
import csv
import json
import os


def read_rows(path):
    with open(path, newline="", encoding="utf-8") as f:
        r = csv.DictReader(f)
        return list(r.fieldnames or []), list(r)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="results")
    ap.add_argument("parts", nargs="+")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    for name in ("runs.csv", "queue_timeseries.csv", "delays_seed0.csv"):
        cols, rows = [], []
        for p in a.parts:
            path = os.path.join(p, name)
            if not os.path.exists(path):
                continue
            c, r = read_rows(path)
            cols += [x for x in c if x not in cols]
            rows += r
        if not rows:
            continue
        with open(os.path.join(a.out, name), "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=cols, restval="")
            w.writeheader()
            w.writerows(rows)
        print("%s: %d linhas" % (name, len(rows)))
    metas = []
    for p in a.parts:
        m = os.path.join(p, "runs.meta.json")
        if os.path.exists(m):
            with open(m, encoding="utf-8") as f:
                metas.append(json.load(f))
    with open(os.path.join(a.out, "runs.meta.json"), "w", encoding="utf-8") as f:
        json.dump(metas, f, indent=2)


if __name__ == "__main__":
    main()
