#!/usr/bin/env python
"""Analise dos resultados da simulacao VelozMart MPS.

Le `results/runs.csv` (e, se existirem, `queue_timeseries.csv`,
`delays_seed0.csv`, `bench_sorting.csv`), gera graficos PNG e um relatorio
`report.md` com tabelas, comparacao entre tecnicas e o veredito do criterio de
decisao EDF x prazo virtual (secao 5.3 da especificacao).

Uso (da raiz do repositorio):
    python analysis/analyze.py --results results --out results/report
"""
import argparse
import json
import math
import os
import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

# valores criticos t (bicaudal 95%) por graus de liberdade
_T975 = {1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571, 6: 2.447, 7: 2.365,
         8: 2.306, 9: 2.262, 10: 2.228, 12: 2.179, 15: 2.131, 20: 2.086,
         25: 2.060, 29: 2.045, 30: 2.042}

STATIC_ORDER = ["fifo", "edf", "composite", "two_queues", "bands_aging", "wspt"]
CORE_SCENARIOS = ["normal_85", "peak_105", "overload_125"]
PALETTE = ["#1b6ca8", "#d95f02", "#7570b3", "#1b9e77", "#e6ab02", "#a6761d",
           "#e7298a", "#666666", "#66a61e", "#b2182b", "#4d4d4d", "#17becf"]
MARKERS = ["o", "s", "^", "D", "v", "P", "X", "*", "h", "<", ">", "p"]


# ---------------------------------------------------------------- utilidades
def tcrit(n):
    df = max(n - 1, 1)
    if df in _T975:
        return _T975[df]
    keys = sorted(_T975)
    for k in keys:
        if k > df:
            return _T975[k]
    return 1.96


def mean_ci(x):
    x = pd.Series(x).dropna()
    n = len(x)
    if n == 0:
        return float("nan"), float("nan")
    m = float(x.mean())
    if n < 2:
        return m, 0.0
    return m, tcrit(n) * float(x.std(ddof=1)) / math.sqrt(n)


def strategy_order(ids):
    ids = list(ids)
    base = [s for s in STATIC_ORDER if s in ids]
    vd = [s for s in ids if s.startswith("vd_")]
    vd.sort(key=lambda s: float(s.split("_a")[1]) if "_a" in s else 0.0)
    rest = [s for s in ids if s not in base and s not in vd]
    return base + vd + sorted(rest)


def style_map(order):
    return {s: (PALETTE[i % len(PALETTE)], MARKERS[i % len(MARKERS)])
            for i, s in enumerate(order)}


def md_table(df, floatfmt="{:.2f}"):
    if df.empty:
        return "_(sem dados)_\n"
    cols = list(df.columns)
    lines = ["| " + " | ".join(str(c) for c in cols) + " |",
             "|" + "|".join("---" for _ in cols) + "|"]
    for _, row in df.iterrows():
        cells = []
        for c in cols:
            v = row[c]
            if isinstance(v, (float, np.floating)):
                cells.append("" if pd.isna(v) else floatfmt.format(v))
            else:
                cells.append(str(v))
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines) + "\n"


def pm(m, h, fmt="{:.2f}"):
    if pd.isna(m):
        return ""
    return (fmt + " ± " + fmt).format(m, 0.0 if pd.isna(h) else h)


class Ctx(object):
    def __init__(self, args):
        self.args = args
        self.out = args.out
        self.plots = os.path.join(args.out, "plots")
        os.makedirs(self.plots, exist_ok=True)
        self.warnings = []
        self.figs = []

    def save(self, fig, name, caption):
        path = os.path.join(self.plots, name)
        fig.savefig(path, dpi=140, bbox_inches="tight")
        plt.close(fig)
        self.figs.append((name, caption))

    def warn(self, msg):
        self.warnings.append(msg)
        print("[aviso] " + msg, file=sys.stderr)


def safe(ctx, fn, *a, **kw):
    try:
        fn(ctx, *a, **kw)
    except Exception as e:  # um grafico com problema nao derruba o resto
        ctx.warn("%s falhou: %r" % (fn.__name__, e))


# ------------------------------------------------------------------- dados
def load(results):
    p = os.path.join(results, "runs.csv")
    if not os.path.exists(p):
        raise SystemExit("runs.csv nao encontrado em %s" % results)
    runs = pd.read_csv(p)
    if "backend" not in runs.columns:
        runs["backend"] = "heap"
    runs["backend"] = runs["backend"].fillna("heap")
    extra = {}
    for name in ("queue_timeseries", "delays_seed0", "bench_sorting"):
        q = os.path.join(results, name + ".csv")
        extra[name] = pd.read_csv(q) if os.path.exists(q) else None
    return runs, extra


def agg(df, metrics, by):
    rows = []
    for key, g in df.groupby(by):
        key = key if isinstance(key, tuple) else (key,)
        row = dict(zip(by, key))
        row["n_seeds"] = g["seed"].nunique()
        for m in metrics:
            if m in g.columns:
                mu, h = mean_ci(g[m])
                row[m] = mu
                row[m + "_ci"] = h
        rows.append(row)
    return pd.DataFrame(rows)


# ----------------------------------------------------------------- graficos
def grouped_bars(ctx, summ, scen, metric, fname, ylabel, strategies, logy=False):
    scen = [s for s in scen if s in set(summ["scenario_id"])]
    if not scen:
        return
    sm = style_map(strategies)
    fig, ax = plt.subplots(figsize=(1.6 + 2.6 * len(scen), 4.6))
    width = 0.8 / max(len(strategies), 1)
    for i, st in enumerate(strategies):
        ys, es = [], []
        for sc in scen:
            r = summ[(summ.scenario_id == sc) & (summ.strategy_id == st)]
            ys.append(float(r[metric].iloc[0]) if len(r) else np.nan)
            es.append(float(r[metric + "_ci"].iloc[0]) if len(r) else 0.0)
        xs = np.arange(len(scen)) + (i - (len(strategies) - 1) / 2.0) * width
        ax.bar(xs, ys, width * 0.92, yerr=es, color=sm[st][0], label=st,
               capsize=1.5, edgecolor="white", linewidth=0.4)
    ax.set_xticks(np.arange(len(scen)))
    ax.set_xticklabels(scen)
    ax.set_ylabel(ylabel)
    if logy:
        ax.set_yscale("symlog", linthresh=1.0)
        ax.set_ylim(bottom=0)
    ax.grid(axis="y", alpha=0.3)
    ax.legend(ncol=min(len(strategies), 7), fontsize=8, frameon=False,
              loc="upper center", bbox_to_anchor=(0.5, -0.10))
    ax.set_title(ylabel + " por cenario (media e IC 95% entre sementes)")
    ctx.save(fig, fname, ylabel + " por cenario e estrategia.")


def plot_bars(ctx, summ, core):
    for metric, fname, ylabel, logy in [
            ("pct_late", "01a_pct_atrasados.png", "% de pedidos atrasados", False),
            ("p99_delay_min", "01b_p99_atraso.png", "P99 do atraso (min)", True),
            ("vip_pct_late", "01c_vip_atrasados.png", "% de VIPs atrasados", False),
            ("mean_delay_min", "01d_atraso_medio.png", "Atraso medio (min)", True),
            ("throughput_per_h", "01e_throughput.png", "Pedidos por hora", False)]:
        if metric in summ.columns:
            grouped_bars(ctx, summ, CORE_SCENARIOS + ["black_friday", "dock_outage"],
                         metric, fname, ylabel, core, logy)


def plot_load_curve(ctx, summ, core):
    sw = summ[summ.scenario_id.str.startswith("sweep_")].copy()
    if sw.empty:
        ctx.warn("sem cenarios sweep_*; curva carga x atraso nao gerada")
        return
    sw["load"] = sw.scenario_id.str.replace("sweep_", "").astype(float)
    sm = style_map(core)
    metrics = [("pct_late", "% atrasados"), ("p99_delay_min", "P99 do atraso (min)"),
               ("vip_pct_late", "% VIPs atrasados")]
    fig, axes = plt.subplots(1, 3, figsize=(16, 4.4))
    for ax, (m, lab) in zip(axes, metrics):
        for st in core:
            g = sw[sw.strategy_id == st].sort_values("load")
            if g.empty:
                continue
            ax.errorbar(g["load"], g[m], yerr=g[m + "_ci"], color=sm[st][0],
                        marker=sm[st][1], ms=4, lw=1.4, capsize=1.5, label=st)
        ax.axvline(100, color="k", ls=":", lw=0.8)
        ax.set_xlabel("carga (% da capacidade nominal de 480/h)")
        ax.set_ylabel(lab)
        if m == "p99_delay_min":
            ax.set_yscale("symlog", linthresh=1.0)
            ax.set_ylim(bottom=0)
        ax.grid(alpha=0.3)
    axes[0].legend(fontsize=8, frameon=False)
    fig.suptitle("Curva carga x atraso (varredura 70% a 130%)")
    ctx.save(fig, "02_curva_carga.png", "Atrasos em funcao da carga, uma linha por estrategia.")


def plot_box(ctx, runs, core, dock, scenario="peak_105"):
    d = runs[(runs.scenario_id == scenario) & (runs.dock_config == dock) & (runs.backend == "heap")]
    if d.empty:
        return
    fig, axes = plt.subplots(1, 3, figsize=(16, 4.4))
    for ax, (m, lab) in zip(axes, [("mean_delay_min", "atraso medio (min)"),
                                    ("p99_delay_min", "P99 (min)"),
                                    ("pct_late", "% atrasados")]):
        data = [d[d.strategy_id == s][m].dropna().values for s in core]
        ax.boxplot(data, labels=core, showmeans=True)
        ax.set_ylabel(lab)
        ax.tick_params(axis="x", rotation=60)
        ax.grid(axis="y", alpha=0.3)
    fig.suptitle("Dispersao entre sementes (%s)" % scenario)
    ctx.save(fig, "03_boxplot_%s.png" % scenario, "Distribuicao por semente em " + scenario + ".")


def plot_cdf(ctx, delays, core, dock, scenario="peak_105"):
    if delays is None:
        return
    d = delays[(delays.scenario_id == scenario) & (delays.dock_config == dock)]
    if "backend" in d.columns:
        d = d[d.backend.fillna("heap") == "heap"]
    if d.empty:
        return
    sm = style_map(core)
    fig, ax = plt.subplots(figsize=(8, 5))
    for st in core:
        v = np.sort(d[d.strategy_id == st]["delay_min"].values)
        if len(v) == 0:
            continue
        y = np.arange(1, len(v) + 1) / float(len(v))
        ax.plot(v, y, color=sm[st][0], label=st, lw=1.5)
    ax.set_xscale("symlog", linthresh=1.0)
    ax.set_xlabel("atraso (min, escala symlog)")
    ax.set_ylabel("fracao acumulada de pedidos")
    ax.set_ylim(0.5, 1.001)
    ax.grid(alpha=0.3)
    ax.legend(fontsize=8, frameon=False)
    ax.set_title("CDF do atraso - cauda (%s, semente 0)" % scenario)
    ctx.save(fig, "04_cdf_atraso.png", "CDF do atraso na cauda; curvas mais a esquerda sao melhores.")


def plot_queue(ctx, qts, dock, scenario="peak_105", strategies=("fifo", "edf", "vd_a1")):
    if qts is None:
        return
    d = qts[(qts.scenario_id == scenario) & (qts.dock_config == dock)]
    qcols = [c for c in d.columns if c.startswith("queue_")]
    if d.empty or not qcols:
        return
    sm = style_map(list(strategies))
    fig, axes = plt.subplots(1, len(qcols), figsize=(5.2 * len(qcols), 4), sharex=True)
    axes = np.atleast_1d(axes)
    for ax, c in zip(axes, qcols):
        for st in strategies:
            g = d[d.strategy_id == st].sort_values("time_min")
            if len(g):
                ax.plot(g["time_min"] / 60.0, g[c], color=sm[st][0], label=st, lw=1.3)
        ax.set_title(c.replace("queue_", "fila "))
        ax.set_xlabel("hora do dia operacional")
        ax.grid(alpha=0.3)
    axes[0].set_ylabel("pedidos na fila")
    axes[0].legend(fontsize=8, frameon=False)
    ctx.save(fig, "05_filas_%s.png" % scenario, "Tamanho das filas por classe de doca ao longo do dia.")


def plot_util(ctx, summ, runs, dock, strategy="edf"):
    ucols = [c for c in runs.columns if c.startswith("util_")]
    d = runs[(runs.dock_config == dock) & (runs.strategy_id == strategy) & (runs.backend == "heap")]
    if d.empty or not ucols:
        return
    m = d.groupby("scenario_id")[ucols].mean()
    order = [s for s in CORE_SCENARIOS + ["black_friday", "promo_g_burst", "mix_shift_33",
                                           "dock_outage", "regional_mix"] if s in m.index]
    order += [s for s in sorted(m.index) if s not in order]
    m = m.loc[order]
    fig, ax = plt.subplots(figsize=(1.5 + 1.6 * len(ucols), 0.5 + 0.38 * len(order)))
    im = ax.imshow(m.values, aspect="auto", cmap="viridis", vmin=0, vmax=max(1.0, float(np.nanmax(m.values))))
    ax.set_xticks(range(len(ucols)))
    ax.set_xticklabels([c.replace("util_", "") for c in ucols])
    ax.set_yticks(range(len(order)))
    ax.set_yticklabels(order)
    for i in range(m.shape[0]):
        for j in range(m.shape[1]):
            v = m.values[i, j]
            ax.text(j, i, "{:.0%}".format(v), ha="center", va="center",
                    color="white" if v < 0.7 else "black", fontsize=8)
    fig.colorbar(im, ax=ax, fraction=0.04)
    ax.set_title("Utilizacao das docas (%s, %s)" % (strategy, dock))
    ctx.save(fig, "06_utilizacao_docas.png", "Utilizacao media por classe de doca e cenario.")


def plot_pareto(ctx, summ, core):
    sc = [s for s in ("peak_105", "overload_125", "black_friday") if s in set(summ.scenario_id)]
    if not sc:
        return
    sm = style_map(core)
    fig, axes = plt.subplots(1, len(sc), figsize=(5.6 * len(sc), 4.6))
    axes = np.atleast_1d(axes)
    for ax, s in zip(axes, sc):
        for st in core:
            r = summ[(summ.scenario_id == s) & (summ.strategy_id == st)]
            if r.empty:
                continue
            r = r.iloc[0]
            ax.errorbar(r["p99_delay_min"], r["vip_pct_late"], xerr=r["p99_delay_min_ci"],
                        yerr=r["vip_pct_late_ci"], fmt=sm[st][1], color=sm[st][0],
                        ms=7, capsize=2, label=st)
        ax.set_xscale("symlog", linthresh=1.0)
        ax.set_xlabel("P99 do atraso (min)  [menor e melhor]")
        ax.set_ylabel("% VIPs atrasados  [menor e melhor]")
        ax.set_title(s)
        ax.grid(alpha=0.3)
    axes[0].legend(fontsize=8, frameon=False)
    ctx.save(fig, "07_pareto_vip_cauda.png", "Compromisso entre protecao de VIP e cauda do atraso.")


def plot_alpha(ctx, summ):
    vd = summ[summ.strategy_id.str.startswith("vd_")].copy()
    if vd.empty:
        return
    vd["alpha"] = vd.strategy_id.str.split("_a").str[1].astype(float)
    sc = [s for s in ("normal_85", "peak_105", "overload_125", "black_friday") if s in set(vd.scenario_id)]
    metrics = [("pct_late", "% atrasados"), ("p99_delay_min", "P99 (min)"), ("vip_pct_late", "% VIPs atrasados")]
    fig, axes = plt.subplots(1, 3, figsize=(16, 4.4))
    for ax, (m, lab) in zip(axes, metrics):
        for i, s in enumerate(sc):
            g = vd[vd.scenario_id == s].sort_values("alpha")
            ax.errorbar(g["alpha"], g[m], yerr=g[m + "_ci"], color=PALETTE[i], marker=MARKERS[i],
                        ms=4, capsize=1.5, label=s)
            e = summ[(summ.scenario_id == s) & (summ.strategy_id == "edf")]
            if len(e):
                ax.axhline(float(e[m].iloc[0]), color=PALETTE[i], ls=":", lw=0.9)
        ax.set_xlabel("alpha (min por ponto de score); alpha=0 ~ EDF; pontilhado = EDF")
        ax.set_ylabel(lab)
        if m == "p99_delay_min":
            ax.set_yscale("symlog", linthresh=1.0)
            ax.set_ylim(bottom=0)
        ax.grid(alpha=0.3)
    axes[0].legend(fontsize=8, frameon=False)
    fig.suptitle("Custo e ganho do bonus de score (prazo virtual)")
    ctx.save(fig, "08_curva_alpha.png", "Efeito de alpha nos atrasos; linhas pontilhadas sao o EDF.")


def plot_docks(ctx, summ_all):
    docks = sorted(summ_all.dock_config.unique())
    if len(docks) < 2:
        return
    strat = [s for s in ("fifo", "edf", "vd_a1") if s in set(summ_all.strategy_id)]
    sc = [s for s in ("normal_85", "peak_105", "overload_125", "mix_shift_33", "dock_outage")
          if s in set(summ_all.scenario_id)]
    fig, axes = plt.subplots(1, 2, figsize=(14, 4.6))
    for ax, (m, lab) in zip(axes, [("pct_late", "% atrasados"), ("p99_delay_min", "P99 (min)")]):
        labels, vals, errs, cols = [], [], [], []
        width = 0.8 / max(len(docks), 1)
        for j, dk in enumerate(docks):
            ys = []
            es = []
            for s in sc:
                r = summ_all[(summ_all.scenario_id == s) & (summ_all.dock_config == dk) & (summ_all.strategy_id == (strat[1] if len(strat) > 1 else strat[0]))]
                ys.append(float(r[m].iloc[0]) if len(r) else np.nan)
                es.append(float(r[m + "_ci"].iloc[0]) if len(r) else 0.0)
            xs = np.arange(len(sc)) + (j - (len(docks) - 1) / 2.0) * width
            ax.bar(xs, ys, width * 0.92, yerr=es, color=PALETTE[j], label=dk, capsize=1.5)
        ax.set_xticks(np.arange(len(sc)))
        ax.set_xticklabels(sc, rotation=20)
        ax.set_ylabel(lab)
        if m == "p99_delay_min":
            ax.set_yscale("symlog", linthresh=1.0)
            ax.set_ylim(bottom=0)
        ax.grid(axis="y", alpha=0.3)
    axes[0].legend(fontsize=8, frameon=False)
    fig.suptitle("Configuracao de docas (estrategia %s)" % (strat[1] if len(strat) > 1 else strat[0]))
    ctx.save(fig, "09_comparacao_docas.png", "Docas genericas x especializadas, com e sem emprestimo.")


def plot_by_class(ctx, summ, core, scenario="peak_105"):
    cols = [c for c in ("pct_late_P", "pct_late_M", "pct_late_G") if c in summ.columns]
    d = summ[summ.scenario_id == scenario]
    if d.empty or not cols:
        return
    fig, ax = plt.subplots(figsize=(10, 4.4))
    sm = style_map(core)
    width = 0.8 / len(core)
    for i, st in enumerate(core):
        r = d[d.strategy_id == st]
        if r.empty:
            continue
        ys = [float(r[c].iloc[0]) for c in cols]
        es = [float(r[c + "_ci"].iloc[0]) for c in cols]
        xs = np.arange(len(cols)) + (i - (len(core) - 1) / 2.0) * width
        ax.bar(xs, ys, width * 0.92, yerr=es, color=sm[st][0], label=st, capsize=1.5)
    ax.set_xticks(range(len(cols)))
    ax.set_xticklabels(["P (Express)", "M (Padrao)", "G (Pesada)"][:len(cols)])
    ax.set_ylabel("% atrasados")
    ax.grid(axis="y", alpha=0.3)
    ax.legend(ncol=4, fontsize=8, frameon=False)
    ax.set_title("Atrasos por tamanho de pedido (%s)" % scenario)
    ctx.save(fig, "10_atraso_por_classe.png", "Quem paga o atraso: P, M ou G.")


def plot_cost(ctx, summ, core):
    d = summ[(summ.scenario_id == "peak_105")]
    if d.empty:
        d = summ[summ.scenario_id == sorted(summ.scenario_id.unique())[0]]
    d = d[d.strategy_id.isin(core)].set_index("strategy_id").reindex(core).dropna(subset=["ops_per_order"])
    if d.empty:
        return
    fig, axes = plt.subplots(1, 2, figsize=(13, 4.2))
    for ax, (m, lab) in zip(axes, [("ops_per_order", "operacoes (comparacoes/trocas) por pedido"),
                                    ("cpu_ms", "tempo de CPU por run (ms)")]):
        ax.bar(range(len(d)), d[m], yerr=d[m + "_ci"], color="#1b6ca8", capsize=2)
        ax.set_xticks(range(len(d)))
        ax.set_xticklabels(d.index, rotation=60)
        ax.set_ylabel(lab)
        ax.set_yscale("log")
        ax.grid(axis="y", alpha=0.3)
    fig.suptitle("Custo das estrategias (backend heap)")
    ctx.save(fig, "11_custo_estrategias.png", "Custo computacional por estrategia.")


def plot_backends(ctx, runs, bench):
    b = runs[runs.backend != "heap"]
    if b.empty and bench is None:
        return
    allb = runs[runs.strategy_id.isin(["edf", "vd_a1"]) & runs.scenario_id.isin(CORE_SCENARIOS)]
    if allb.backend.nunique() > 1:
        s = agg(allb, ["ops_per_order", "cpu_ms"], ["scenario_id", "strategy_id", "backend"])
        fig, axes = plt.subplots(1, 2, figsize=(14, 4.4))
        backs = [x for x in ["heap", "insertion", "selection", "merge", "quick"] if x in set(s.backend)]
        for ax, (m, lab) in zip(axes, [("ops_per_order", "operacoes por pedido"), ("cpu_ms", "CPU por run (ms)")]):
            width = 0.8 / len(backs)
            labels = [(sc, st) for sc in CORE_SCENARIOS for st in ("edf", "vd_a1")
                      if len(s[(s.scenario_id == sc) & (s.strategy_id == st)])]
            for j, bk in enumerate(backs):
                ys = []
                for sc, st in labels:
                    r = s[(s.scenario_id == sc) & (s.strategy_id == st) & (s.backend == bk)]
                    ys.append(float(r[m].iloc[0]) if len(r) else np.nan)
                xs = np.arange(len(labels)) + (j - (len(backs) - 1) / 2.0) * width
                ax.bar(xs, ys, width * 0.92, color=PALETTE[j], label=bk)
            ax.set_xticks(range(len(labels)))
            ax.set_xticklabels(["%s\n%s" % l for l in labels], fontsize=8)
            ax.set_ylabel(lab)
            ax.set_yscale("log")
            ax.grid(axis="y", alpha=0.3)
        axes[0].legend(fontsize=8, frameon=False)
        fig.suptitle("Algoritmos de ordenacao como backend da fila (simulacao completa)")
        ctx.save(fig, "12a_backends_simulacao.png", "Custo de manter a fila com cada algoritmo de ordenacao.")
    if bench is not None and len(bench):
        ops = sorted(bench["op"].unique())
        fig, axes = plt.subplots(1, len(ops), figsize=(5.4 * len(ops), 4.2), sharey=False)
        axes = np.atleast_1d(axes)
        for ax, op in zip(axes, ops):
            for j, alg in enumerate(sorted(bench.algorithm.unique())):
                g = bench[(bench.algorithm == alg) & (bench.op == op)].sort_values("n")
                ax.plot(g["n"], g["ms_per_op"], marker=MARKERS[j], color=PALETTE[j], label=alg)
            ax.set_xscale("log")
            ax.set_yscale("log")
            ax.set_xlabel("n (pedidos na fila)")
            ax.set_ylabel("ms por operacao")
            ax.set_title(op)
            ax.grid(alpha=0.3, which="both")
        axes[0].legend(fontsize=8, frameon=False)
        fig.suptitle("Benchmark de ordenacao: custo por operacao x tamanho da fila")
        ctx.save(fig, "12b_benchmark_ordenacao.png", "Crescimento do custo por operacao com n.")


# --------------------------------------------------------- criterio de decisao
def paired_delta(runs, scen, dock, a, b, metric):
    """media e IC de (a - b) pareando por semente (mesmos pedidos)."""
    d = runs[(runs.scenario_id == scen) & (runs.dock_config == dock) & (runs.backend == "heap")]
    pa = d[d.strategy_id == a].set_index("seed")[metric]
    pb = d[d.strategy_id == b].set_index("seed")[metric]
    diff = (pa - pb).dropna()
    if diff.empty:
        return float("nan"), float("nan"), 0
    m, h = mean_ci(diff)
    return m, h, len(diff)


def decision(ctx, runs, summ, dock, finalists):
    args = ctx.args
    a_list = [s for s in finalists if s != "edf" and s in set(runs.strategy_id)]
    scen_all = [s for s in args.decisive.split(",") if s in set(runs.scenario_id)]
    if "edf" not in set(runs.strategy_id) or not a_list or not scen_all:
        return None, "_Criterio nao avaliado: faltam EDF, prazo virtual ou cenarios decisivos._\n"
    guard = [s for s in args.guard.split(",") if s in set(runs.scenario_id)]
    rows = []
    verdict = {}
    for st in a_list:
        ok_all = True
        for sc in scen_all + guard:
            decisive = sc in scen_all
            vip_e = float(summ[(summ.scenario_id == sc) & (summ.dock_config == dock) & (summ.strategy_id == "edf")]["vip_pct_late"].iloc[0])
            vip_s = float(summ[(summ.scenario_id == sc) & (summ.dock_config == dock) & (summ.strategy_id == st)]["vip_pct_late"].iloc[0])
            p99_e = float(summ[(summ.scenario_id == sc) & (summ.dock_config == dock) & (summ.strategy_id == "edf")]["p99_delay_min"].iloc[0])
            d_late, h_late, n = paired_delta(runs, sc, dock, st, "edf", "pct_late")
            d_p99, h_p99, _ = paired_delta(runs, sc, dock, st, "edf", "p99_delay_min")
            late_eff = 0.0 if (abs(d_late) <= h_late) else d_late  # IC contem 0 => empate
            p99_rel = (0.0 if abs(d_p99) <= h_p99 else d_p99) / max(p99_e, 1.0)
            vip_red = (vip_e - vip_s) / vip_e if vip_e > 0 else float("nan")
            has_room = vip_e >= args.min_vip_base
            c_vip = bool(has_room and vip_red >= args.vip_reduction)
            c_late = late_eff <= args.max_pp
            c_p99 = p99_rel <= args.max_p99_rel
            if decisive:
                passed = c_vip and c_late and c_p99
                ok_all = ok_all and passed
            else:
                passed = c_late and c_p99  # guarda: nao pode regredir em carga normal
                ok_all = ok_all and passed
            rows.append({"estrategia": st, "cenario": sc, "papel": "decisivo" if decisive else "guarda",
                         "VIP EDF %": vip_e, "VIP estrat. %": vip_s,
                         "reducao VIP": vip_red * 100 if not pd.isna(vip_red) else float("nan"),
                         "delta % atrasados (pp)": d_late, "IC": h_late,
                         "delta P99 (%)": p99_rel * 100, "passa": "sim" if passed else "nao"})
        verdict[st] = ok_all
    tab = pd.DataFrame(rows)
    winners = [s for s, v in verdict.items() if v]
    if winners:
        best = winners[0]
        res = "**Prazo virtual (%s)** atende ao criterio em todos os cenarios decisivos e nao regride nos de guarda." % best
    else:
        res = "**EDF**: nenhum prazo virtual testado atende ao criterio (ou os resultados empatam, e o empate vai para o EDF pela simplicidade)."
    txt = ("Criterio (secao 5.3): o prazo virtual so substitui o EDF se, em **todos** os cenarios decisivos (%s), "
           "reduzir os VIPs atrasados em pelo menos %.0f%% (partindo de pelo menos %.1f%% de VIP atrasado no EDF) "
           "sem piorar a %% de atrasados em mais de %.1f pp nem o P99 em mais de %.0f%%; diferencas dentro do IC 95%% "
           "pareado por semente contam como empate; nos cenarios de guarda (%s) nao pode regredir.\n\n"
           % (", ".join(scen_all), args.vip_reduction * 100, args.min_vip_base, args.max_pp,
              args.max_p99_rel * 100, ", ".join(guard) or "nenhum"))
    txt += md_table(tab, "{:.2f}") + "\n**Veredito:** " + res + "\n"
    return (winners[0] if winners else "edf"), txt


# ------------------------------------------------------------------ relatorio
def table_by_scenario(summ, scen, strategies, dock):
    d = summ[(summ.scenario_id == scen) & (summ.dock_config == dock)]
    rows = []
    for st in strategies:
        r = d[d.strategy_id == st]
        if r.empty:
            continue
        r = r.iloc[0]
        rows.append({"estrategia": st,
                     "% atrasados": pm(r["pct_late"], r["pct_late_ci"]),
                     "% VIP atrasados": pm(r["vip_pct_late"], r["vip_pct_late_ci"]),
                     "atraso medio (min)": pm(r["mean_delay_min"], r["mean_delay_min_ci"]),
                     "P95 (min)": pm(r["p95_delay_min"], r["p95_delay_min_ci"], "{:.1f}") if "p95_delay_min" in r else "",
                     "P99 (min)": pm(r["p99_delay_min"], r["p99_delay_min_ci"], "{:.1f}"),
                     "pior (min)": pm(r["max_delay_min"], r["max_delay_min_ci"], "{:.1f}") if "max_delay_min" in r else "",
                     "pedidos/h": pm(r["throughput_per_h"], r["throughput_per_h_ci"], "{:.1f}")})
    return pd.DataFrame(rows)


def findings(summ, dock, strategies):
    out = []
    for sc in CORE_SCENARIOS:
        d = summ[(summ.scenario_id == sc) & (summ.dock_config == dock)].set_index("strategy_id")
        if d.empty:
            continue
        have = [s for s in strategies if s in d.index]
        if "fifo" in d.index and "edf" in d.index:
            f, e = d.loc["fifo"], d.loc["edf"]
            out.append("- **%s:** EDF reduz os atrasados de %.1f%% (FIFO) para %.1f%% e o P99 de %.1f para %.1f min."
                       % (sc, f["pct_late"], e["pct_late"], f["p99_delay_min"], e["p99_delay_min"]))
        if have:
            b = min(have, key=lambda s: d.loc[s, "pct_late"])
            w = min(have, key=lambda s: d.loc[s, "p99_delay_min"])
            v = min(have, key=lambda s: d.loc[s, "vip_pct_late"])
            out.append("  - menor %% de atrasados: **%s** (%.1f%%); menor P99: **%s** (%.1f min); menos VIPs atrasados: **%s** (%.1f%%)."
                       % (b, d.loc[b, "pct_late"], w, d.loc[w, "p99_delay_min"], v, d.loc[v, "vip_pct_late"]))
    return "\n".join(out) + ("\n" if out else "")


def consistency(runs):
    """backends diferentes com a mesma chave devem dar as mesmas metricas de atraso."""
    nb = runs[runs.backend != "heap"]
    if nb.empty:
        return "_Sem execucoes com backends alem do heap._\n"
    keys = ["scenario_id", "dock_config", "strategy_id", "seed"]
    h = runs[runs.backend == "heap"].set_index(keys)
    bad = 0
    tot = 0
    for bk, g in nb.groupby("backend"):
        g = g.set_index(keys)
        j = g[["pct_late", "mean_delay_min"]].join(h[["pct_late", "mean_delay_min"]], rsuffix="_heap", how="inner")
        tot += len(j)
        bad += int(((j.pct_late - j.pct_late_heap).abs() > 1e-9).sum())
    return ("Comparadas %d execucoes de backends alternativos com o heap: %d divergem em %% de atrasados "
            "(esperado: 0, pois a chave e a mesma).\n" % (tot, bad))


def write_report(ctx, runs, extra, summ, summ_all, dock, order, core, verdict_txt, winner):
    a = ctx.args
    L = []
    L.append("# VelozMart MPS - relatorio de analise\n")
    L.append("Gerado a partir de `%s`. %d execucoes; %d cenarios; %d estrategias; sementes por cenario: %s.\n" % (
        os.path.join(a.results, "runs.csv"), len(runs), runs.scenario_id.nunique(),
        runs.strategy_id.nunique(), ", ".join(sorted(set(str(int(x)) for x in summ_all.n_seeds.unique())))))
    L.append("Configuracao de docas principal: `%s`. IC = 95%% (t de Student) entre sementes; "
             "comparacoes entre estrategias usam as mesmas sementes (mesmos pedidos).\n" % dock)
    L.append("## 1. Resposta rapida\n")
    L.append("**Algoritmo recomendado pelo criterio: %s.**\n" % ("EDF" if winner == "edf" else "prazo virtual (%s)" % winner))
    L.append(findings(summ, dock, core))
    L.append("## 2. Pergunta III: metricas contra a ordenacao simples por tempo (FIFO)\n")
    for sc in CORE_SCENARIOS + ["black_friday", "dock_outage"]:
        t = table_by_scenario(summ, sc, order, dock)
        if len(t):
            L.append("### %s\n" % sc)
            L.append(md_table(t))
    L.append("## 3. Criterio de decisao: EDF x prazo virtual\n")
    L.append(verdict_txt)
    L.append("## 4. Graficos\n")
    for name, cap in ctx.figs:
        L.append("![%s](plots/%s)\n\n_%s_\n" % (name, name, cap))
    L.append("## 5. Docas e custo\n")
    docks = sorted(summ_all.dock_config.unique())
    if len(docks) > 1:
        L.append("Configuracoes de docas encontradas: %s. Ver grafico 09.\n" % ", ".join(docks))
        sub = summ_all[(summ_all.scenario_id == "peak_105") & (summ_all.strategy_id == "edf")]
        if len(sub):
            t = sub[["dock_config", "pct_late", "p99_delay_min", "throughput_per_h"]].copy()
            if "n_loans" in sub.columns:
                t["emprestimos"] = sub["n_loans"]
            L.append("EDF em `peak_105`:\n")
            L.append(md_table(t))
    L.append("### Algoritmos de ordenacao (backends)\n")
    L.append(consistency(runs))
    bk = runs[runs.backend != "heap"]
    if len(bk):
        s = agg(runs[runs.strategy_id.isin(["edf", "vd_a1"]) & runs.scenario_id.isin(CORE_SCENARIOS)],
                ["ops_per_order", "cpu_ms"], ["scenario_id", "strategy_id", "backend"])
        s = s[s.strategy_id == "edf"][["scenario_id", "backend", "ops_per_order", "cpu_ms"]]
        L.append("EDF, operacoes por pedido e CPU por run:\n")
        L.append(md_table(s, "{:.1f}"))
    L.append("## 6. Limitacoes\n")
    L.append("- Dados sinteticos: o score e gerado a partir de SLA, distancia, valor e reputacao, o que favorece "
             "estrategias que usam o score.\n"
             "- A embalagem e deterministica (P=1, M=2, G=4 min); nao ha variabilidade de transporte nem de mao de obra.\n"
             "- Parametros dos concorrentes (faixa 30 min, aging 0,2, limite 60 min) nao foram calibrados com o mesmo rigor do alpha.\n"
             "- Os limites do criterio (%.0f%% de reducao de VIP, %.1f pp, %.0f%% de P99) sao sugestoes do grupo.\n"
             % (a.vip_reduction * 100, a.max_pp, a.max_p99_rel * 100))
    if ctx.warnings:
        L.append("## Avisos da analise\n")
        L.extend("- " + w for w in ctx.warnings)
        L.append("")
    path = os.path.join(ctx.out, "report.md")
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(L))
    return path


# ---------------------------------------------------------------------- main
def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--results", default="results")
    ap.add_argument("--out", default=None, help="padrao: <results>/report")
    ap.add_argument("--dock", default="base_15", help="configuracao de docas principal")
    ap.add_argument("--strategies-config", default="configs/strategies.json")
    ap.add_argument("--decisive", default="peak_105,overload_125,black_friday")
    ap.add_argument("--guard", default="normal_85")
    ap.add_argument("--vip-reduction", type=float, default=0.5)
    ap.add_argument("--min-vip-base", type=float, default=1.0,
                    help="% minima de VIP atrasado no EDF para haver o que melhorar")
    ap.add_argument("--max-pp", type=float, default=1.0)
    ap.add_argument("--max-p99-rel", type=float, default=0.2)
    args = ap.parse_args(argv)
    args.out = args.out or os.path.join(args.results, "report")
    ctx = Ctx(args)

    runs, extra = load(args.results)
    finalists = ["edf", "vd_a1", "vd_a2", "vd_a3"]
    if os.path.exists(args.strategies_config):
        try:
            with open(args.strategies_config, encoding="utf-8") as f:
                finalists = json.load(f).get("finalists", finalists)
        except Exception as e:
            ctx.warn("nao li %s: %r" % (args.strategies_config, e))

    dock = args.dock if args.dock in set(runs.dock_config) else sorted(runs.dock_config.unique())[0]
    if dock != args.dock:
        ctx.warn("dock %s ausente; usando %s" % (args.dock, dock))

    metrics = ["pct_late", "mean_delay_min", "p95_delay_min", "p99_delay_min", "max_delay_min",
               "vip_pct_late", "throughput_per_h", "mean_wait_min", "pct_late_P", "pct_late_M", "pct_late_G",
               "idle_pct", "n_loans", "ops_per_order", "cpu_ms"] + [c for c in runs.columns if c.startswith("util_")]
    heap = runs[runs.backend == "heap"]
    summ_all = agg(heap, metrics, ["scenario_id", "dock_config", "strategy_id"])
    summ_all.to_csv(os.path.join(ctx.out, "summary.csv"), index=False)
    summ = summ_all[summ_all.dock_config == dock]

    order = strategy_order(summ.strategy_id.unique())
    core = [s for s in order if not s.startswith("vd_") or s in finalists]
    if "fifo" in order and "fifo" not in core:
        core.insert(0, "fifo")

    safe(ctx, plot_bars, summ, core)
    safe(ctx, plot_load_curve, summ, core)
    safe(ctx, plot_box, heap, core, dock)
    safe(ctx, plot_cdf, extra["delays_seed0"], core, dock)
    safe(ctx, plot_queue, extra["queue_timeseries"], dock)
    safe(ctx, plot_util, summ, heap, dock)
    safe(ctx, plot_pareto, summ, core)
    safe(ctx, plot_alpha, summ)
    safe(ctx, plot_docks, summ_all)
    safe(ctx, plot_by_class, summ, core)
    safe(ctx, plot_cost, summ, core)
    safe(ctx, plot_backends, runs, extra["bench_sorting"])

    winner, verdict_txt = "edf", ""
    try:
        w, verdict_txt = decision(ctx, heap, summ, dock, finalists)
        winner = w or "edf"
    except Exception as e:
        ctx.warn("decision falhou: %r" % (e,))
        verdict_txt = "_Criterio nao avaliado (ver avisos)._\n"
    path = write_report(ctx, runs, extra, summ, summ_all, dock, order, core, verdict_txt, winner)
    print("Relatorio: %s\nGraficos: %s (%d)" % (path, ctx.plots, len(ctx.figs)))


if __name__ == "__main__":
    main()
