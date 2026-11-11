"""Compara o custo de manter a fila com Insertion/Selection/Merge/Quick/Heap.

Para cada (algoritmo, n): monta uma fila de n pedidos (chave EDF aleatoria) e mede,
em ciclos [push, push, update, cancel, pop] que mantem o tamanho constante, o tempo
medio (ms) e as `ops` (comparacoes+movimentos) por operacao. Nos backends de
reordenacao (merge/quick) o custo da reordenacao cai no pop seguinte.

Saida: results/bench_sorting.csv com algorithm,n,op,ms_per_op,ops_per_op.
Combinacoes cuja projecao quadratica excede o orcamento sao puladas (linha com
valores vazios), tipico de quick (pivo fixo, pior caso em fila ordenada) com n grande.

Uso: python scripts/bench_sorting.py [--out results/bench_sorting.csv]
         [--sizes 1000,10000,50000] [--budget-s 20] [--seed 0]
"""
import argparse
import csv
import os
import random
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mps.models import Order  # noqa: E402
from mps.strategies import make_strategy  # noqa: E402

ALGOS = ["insertion", "selection", "merge", "quick", "heap"]
OPS = ["push", "update", "cancel", "pop"]


def build(backend, n, rng):
    s = make_strategy("edf", backend=backend)
    orders = [Order("B%d" % i, 0.0, rng.uniform(1, 1e6), 50.0, "P", deadline_min=rng.uniform(1, 1e6), seq=i)
              for i in range(n)]
    if backend == "heap":
        for o in orders:
            s.push(o, 0.0)
    else:  # montagem direta (setup, nao medido): evita n^2 para insertion
        q = s._heap
        pairs = [(s.key(o, 0.0), o) for o in orders]
        if backend != "selection":
            pairs.sort(key=lambda e: e[0])   # so no setup
        q.a = pairs
        q.ids = dict((o.order_id, o) for o in orders)
    s.ops = 0
    return s, orders


def measure(backend, n, budget_s, rng):
    s, orders = build(backend, n, rng)
    live = [o.order_id for o in orders]
    nxt = n
    tot_t = dict((op, 0.0) for op in OPS)
    tot_o = dict((op, 0) for op in OPS)
    cnt = dict((op, 0) for op in OPS)

    def timed(op, fn):
        o0 = s.ops
        t = time.perf_counter()
        r = fn()
        tot_t[op] += time.perf_counter() - t
        tot_o[op] += s.ops - o0
        cnt[op] += 1
        return r

    start = time.perf_counter()
    cycles = 0
    while cycles < 200 and (cycles == 0 or time.perf_counter() - start < budget_s):
        for _ in range(2):
            nxt += 1
            o = Order("B%d" % nxt, 0.0, 1.0, 50.0, "P", deadline_min=rng.uniform(1, 1e6), seq=nxt)
            timed("push", lambda: s.push(o, 0.0))
            live.append(o.order_id)
        oid = live[rng.randrange(len(live))]
        timed("update", lambda: s.update(oid, 0.0, new_deadline_min=rng.uniform(1, 1e6)))
        j = rng.randrange(len(live))
        live[j], live[-1] = live[-1], live[j]
        timed("cancel", lambda: s.cancel(live.pop()))
        got = timed("pop", lambda: s.pop(0.0))
        live.remove(got.order_id)
        cycles += 1
    return [(op, 1000.0 * tot_t[op] / cnt[op], tot_o[op] / float(cnt[op])) for op in OPS]


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="results/bench_sorting.csv")
    ap.add_argument("--sizes", default="1000,10000,50000")
    ap.add_argument("--budget-s", type=float, default=20.0)
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args(argv)
    sizes = [int(x) for x in args.sizes.split(",")]
    rng = random.Random(args.seed)
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    rows = []
    for algo in ALGOS:
        prev = None   # (n, pior ms/op)
        for n in sizes:
            if prev is not None:
                proj = prev[1] * (float(n) / prev[0]) ** 2   # ms, projecao quadratica
                if proj > 5 * args.budget_s * 1000.0:
                    print("%s n=%d: pulado (projecao %.0f s)" % (algo, n, proj / 1000.0))
                    rows.extend([algo, n, op, "", ""] for op in OPS)
                    continue
            res = measure(algo, n, args.budget_s, rng)
            prev = (n, max(r[1] for r in res))
            for op, ms, ops in res:
                rows.append([algo, n, op, "%.6f" % ms, "%.2f" % ops])
                print("%-9s n=%-6d %-7s %12.5f ms/op %14.1f ops/op" % (algo, n, op, ms, ops))
    with open(args.out, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["algorithm", "n", "op", "ms_per_op", "ops_per_op"])
        w.writerows(rows)
    print("escrito", args.out)


if __name__ == "__main__":
    main()
