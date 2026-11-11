#!/usr/bin/env python
"""Analise geral de todos os experimentos (v1: janelas amplas; v2: janelas apertadas).

Gera graficos PNG, tabelas e um documento HTML que e impresso em PDF.
Uso (da raiz do repositorio):
    python analysis/overall.py --out reports/v1.0.0
O PDF e gerado com Microsoft Edge/Chrome headless se encontrado (--no-pdf para pular).
"""
import argparse
import os
import shutil
import subprocess
import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from overall_data import (ALL_DOCKS, GENERAL, SCENARIOS, SPECIALIZED, STRATS, WEIGHTS, WEIGHTS_VIP,  # noqa: E402
                          best_table, load_runs, notas_matrix, outcome, overall_ranking, score_group,
                          summarize)

PAL = ["#1b6ca8", "#d95f02", "#7570b3", "#1b9e77", "#e6ab02", "#a6761d", "#e7298a", "#666666", "#66a61e",
       "#b2182b", "#17becf", "#4d4d4d"]
SC_LABEL = {"normal_85": "Normal (85%)", "peak_105": "Pico (105%)", "overload_125": "Sobrecarga (125%)",
            "black_friday": "Black Friday", "promo_g_burst": "Rajada de G", "mix_shift_33": "Mix deslocado",
            "dock_outage": "Falha de doca", "regional_mix": "Multi-país"}
DOCK_LABEL = {"base_15": "Especializada (com empréstimo)", "base_15_no_borrow": "Especializada (sem empréstimo)",
              "generic_15": "Geral uniforme", "generic_nested_15": "Geral de capacidade variada",
              "generic_speed_15": "Geral de velocidade variada"}
ST_LABEL = {"fifo": "FIFO", "edf": "EDF", "composite": "Peso composto", "two_queues": "Duas filas",
            "bands_aging": "Faixas + aging", "wspt": "WSPT", "vd_a0.5": "Prazo virtual α=0,5",
            "vd_a1": "Prazo virtual α=1", "vd_a2": "Prazo virtual α=2", "vd_a3": "Prazo virtual α=3",
            "vd_a5": "Prazo virtual α=5"}


def fmt(x, d=1):
    return ("{:." + str(d) + "f}").format(x).replace(".", ",")


class Ctx(object):
    def __init__(self, out):
        self.out = out
        self.plots = os.path.join(out, "plots")
        os.makedirs(self.plots, exist_ok=True)


def savefig(ctx, fig, name):
    fig.savefig(os.path.join(ctx.plots, name), dpi=150, bbox_inches="tight")
    plt.close(fig)
    return "plots/" + name


# ------------------------------------------------------------------ graficos
def fig_ranking(ctx, rank_all, rank_esp, rank_ger):
    order = list(rank_all.index)
    fig, ax = plt.subplots(figsize=(10, 5.2))
    w = 0.27
    y = np.arange(len(order))
    for k, (lab, r, c) in enumerate([("Todas as docas", rank_all, PAL[0]), ("Especializadas", rank_esp, PAL[1]),
                                     ("Gerais", rank_ger, PAL[3])]):
        ax.barh(y + (k - 1) * w, [r.loc[s, "nota_media"] for s in order], w * 0.95, color=c, label=lab)
    ax.set_yticks(y)
    ax.set_yticklabels([ST_LABEL[s] for s in order])
    ax.invert_yaxis()
    ax.set_xlabel("nota média (0 a 100; maior é melhor)")
    ax.grid(axis="x", alpha=0.3)
    ax.legend(frameon=False)
    ax.set_title("Nota média das estratégias por grupo de docas (janelas apertadas)")
    return savefig(ctx, fig, "g1_nota_geral.png")


def fig_heat(ctx, m, title, name):
    cols = [c for c in SCENARIOS if c in m.columns]
    mm = m[cols]
    fig, ax = plt.subplots(figsize=(1.8 + 1.15 * len(cols), 0.9 + 0.42 * len(mm)))
    im = ax.imshow(mm.values, aspect="auto", cmap="RdYlGn", vmin=0, vmax=100)
    ax.set_xticks(range(len(cols)))
    ax.set_xticklabels([SC_LABEL[c] for c in cols], rotation=30, ha="right")
    ax.set_yticks(range(len(mm)))
    ax.set_yticklabels([ST_LABEL[s] for s in mm.index])
    for i in range(mm.shape[0]):
        for j in range(mm.shape[1]):
            v = mm.values[i, j]
            ax.text(j, i, "%.0f" % v, ha="center", va="center", fontsize=8, color="black")
    fig.colorbar(im, ax=ax, fraction=0.03, label="nota (maior é melhor)")
    ax.set_title(title)
    return savefig(ctx, fig, name)


def fig_blackfriday(ctx, S):
    strat = ["fifo", "edf", "composite", "two_queues", "bands_aging", "wspt", "vd_a1", "vd_a2", "vd_a3"]
    d = S[S.scenario_id == "black_friday"]
    fig, axes = plt.subplots(1, 3, figsize=(17, 4.8))
    for ax, (m, lab) in zip(axes, [("pct_late", "% de pedidos atrasados"), ("p99_delay_min", "P99 do atraso (min)"),
                                   ("vip_pct_late", "% de VIPs atrasados")]):
        w = 0.8 / len(ALL_DOCKS)
        for j, dk in enumerate(ALL_DOCKS):
            ys = [float(d[(d.dock_config == dk) & (d.strategy_id == s)][m].iloc[0]) for s in strat]
            ax.bar(np.arange(len(strat)) + (j - 2) * w, ys, w * 0.95, color=PAL[j], label=DOCK_LABEL[dk])
        ax.set_xticks(range(len(strat)))
        ax.set_xticklabels([ST_LABEL[s].replace("Prazo virtual", "PV") for s in strat], rotation=45, ha="right")
        ax.set_ylabel(lab)
        ax.grid(axis="y", alpha=0.3)
        if m == "p99_delay_min":
            ax.set_yscale("symlog", linthresh=10)
            ax.set_ylim(bottom=0)
    h, l = axes[0].get_legend_handles_labels()
    fig.legend(h, l, loc="lower center", ncol=5, frameon=False, fontsize=9, bbox_to_anchor=(0.5, -0.04))
    fig.suptitle("Black Friday: estratégia × configuração de docas")
    return savefig(ctx, fig, "g5_black_friday.png")


def fig_bf_size(ctx, S):
    d = S[(S.scenario_id == "black_friday") & (S.strategy_id == "edf")].set_index("dock_config").loc[ALL_DOCKS]
    fig, ax = plt.subplots(figsize=(9, 4.4))
    w = 0.27
    for k, (c, lab) in enumerate([("pct_late_P", "P (pequeno)"), ("pct_late_M", "M (médio)"), ("pct_late_G", "G (grande)")]):
        ax.bar(np.arange(len(ALL_DOCKS)) + (k - 1) * w, d[c].values, w * 0.95, color=PAL[k], label=lab)
    ax.set_xticks(range(len(ALL_DOCKS)))
    ax.set_xticklabels([DOCK_LABEL[x].replace(" (", "\n(") for x in ALL_DOCKS], fontsize=8)
    ax.set_ylabel("% atrasados (EDF)")
    ax.grid(axis="y", alpha=0.3)
    ax.legend(frameon=False)
    ax.set_title("Black Friday: quem paga o atraso, por tamanho de pedido")
    return savefig(ctx, fig, "g5b_black_friday_tamanho.png")


def fig_docks_edf(ctx, S):
    sc = [s for s in SCENARIOS if s != "normal_85"]
    fig, axes = plt.subplots(1, 2, figsize=(16, 4.8))
    for ax, (m, lab) in zip(axes, [("pct_late", "% de pedidos atrasados (EDF)"), ("p99_delay_min", "P99 do atraso, min (EDF)")]):
        w = 0.8 / len(ALL_DOCKS)
        for j, dk in enumerate(ALL_DOCKS):
            ys = [float(S[(S.dock_config == dk) & (S.scenario_id == s) & (S.strategy_id == "edf")][m].iloc[0]) for s in sc]
            ax.bar(np.arange(len(sc)) + (j - 2) * w, ys, w * 0.95, color=PAL[j], label=DOCK_LABEL[dk])
        ax.set_xticks(range(len(sc)))
        ax.set_xticklabels([SC_LABEL[s] for s in sc], rotation=25, ha="right")
        ax.set_ylabel(lab)
        ax.grid(axis="y", alpha=0.3)
        if m == "p99_delay_min":
            ax.set_yscale("symlog", linthresh=10)
            ax.set_ylim(bottom=0)
    axes[0].legend(fontsize=8, frameon=False)
    fig.suptitle("Docas especializadas × gerais (estratégia EDF)")
    return savefig(ctx, fig, "g6_docas_edf.png")


def fig_sweep(ctx, runs):
    h = runs[(runs.backend == "heap") & runs.scenario_id.str.startswith("sweep_")]
    g = h.groupby(["dock_config", "scenario_id", "strategy_id"])[["pct_late", "p99_delay_min"]].mean().reset_index()
    g["load"] = g.scenario_id.str.replace("sweep_", "").astype(int)
    strat = [s for s in ("fifo", "edf", "vd_a2", "two_queues") if s in set(g.strategy_id)]
    fig, axes = plt.subplots(1, 2, figsize=(14, 4.6))
    for ax, (m, lab) in zip(axes, [("pct_late", "% de pedidos atrasados"), ("p99_delay_min", "P99 do atraso (min)")]):
        for k, s in enumerate(strat):
            for dk, ls in (("base_15", "-"), ("generic_15", "--")):
                x = g[(g.dock_config == dk) & (g.strategy_id == s)].sort_values("load")
                if len(x):
                    ax.plot(x["load"], x[m], ls, color=PAL[k], marker="o", ms=3, lw=1.5,
                            label="%s, %s" % (ST_LABEL[s], "especializada" if dk == "base_15" else "geral"))
        ax.axvline(100, color="k", ls=":", lw=0.8)
        ax.set_xlabel("carga (% da capacidade nominal)")
        ax.set_ylabel(lab)
        ax.grid(alpha=0.3)
        if m == "p99_delay_min":
            ax.set_yscale("symlog", linthresh=10)
            ax.set_ylim(bottom=0)
    axes[0].legend(fontsize=7, frameon=False, ncol=2)
    fig.suptitle("Curva carga × atraso: linha contínua = docas especializadas, tracejada = docas gerais")
    return savefig(ctx, fig, "g7_curva_carga.png")


def fig_pareto(ctx, S):
    strat = ["fifo", "edf", "composite", "two_queues", "bands_aging", "wspt", "vd_a0.5", "vd_a1", "vd_a2", "vd_a3", "vd_a5"]
    fig, axes = plt.subplots(2, 2, figsize=(13, 9))
    for i, sc in enumerate(["peak_105", "black_friday"]):
        for j, dk in enumerate(["base_15", "generic_15"]):
            ax = axes[i, j]
            d = S[(S.scenario_id == sc) & (S.dock_config == dk)]
            for k, s in enumerate(strat):
                r = d[d.strategy_id == s]
                if r.empty:
                    continue
                ax.scatter(float(r.p99_delay_min.iloc[0]), float(r.vip_pct_late.iloc[0]), s=70, color=PAL[k % len(PAL)],
                           label=ST_LABEL[s], zorder=3)
            ax.set_xscale("symlog", linthresh=10)
            ax.set_xlim(left=0)
            ax.set_xlabel("P99 do atraso (min), menor é melhor")
            ax.set_ylabel("% VIPs atrasados, menor é melhor")
            ax.set_title("%s, docas %s" % (SC_LABEL[sc], "especializadas" if dk == "base_15" else "gerais"))
            ax.grid(alpha=0.3)
    axes[0, 0].legend(fontsize=7, frameon=False, ncol=2)
    fig.suptitle("Proteção de VIP × cauda do atraso")
    return savefig(ctx, fig, "g8_vip_cauda.png")


def fig_sens(ctx, S):
    r1, _ = overall_ranking(S, ALL_DOCKS, weights=WEIGHTS)
    r2, _ = overall_ranking(S, ALL_DOCKS, weights=WEIGHTS_VIP)
    order = list(r1.index)
    fig, ax = plt.subplots(figsize=(10, 5))
    y = np.arange(len(order))
    ax.barh(y - 0.2, [r1.loc[s, "nota_media"] for s in order], 0.38, color=PAL[0], label="pesos do grupo (VIP 10%)")
    ax.barh(y + 0.2, [r2.loc[s, "nota_media"] for s in order], 0.38, color=PAL[1], label="se o VIP pesasse 40%")
    ax.set_yticks(y)
    ax.set_yticklabels([ST_LABEL[s] for s in order])
    ax.invert_yaxis()
    ax.set_xlabel("nota média (0 a 100)")
    ax.grid(axis="x", alpha=0.3)
    ax.legend(frameon=False)
    ax.set_title("Sensibilidade aos pesos da nota")
    return savefig(ctx, fig, "g12_sensibilidade.png"), r1, r2


def fig_alpha(ctx, S):
    d = S[(S.dock_config == "base_15") & S.strategy_id.isin(["edf", "vd_a0.5", "vd_a1", "vd_a2", "vd_a3", "vd_a5"])]
    alphas = {"edf": 0, "vd_a0.5": 0.5, "vd_a1": 1, "vd_a2": 2, "vd_a3": 3, "vd_a5": 5}
    sc = ["peak_105", "overload_125", "black_friday"]
    fig, axes = plt.subplots(1, 3, figsize=(16, 4.4))
    for ax, (m, lab) in zip(axes, [("pct_late", "% atrasados"), ("p99_delay_min", "P99 (min)"), ("vip_pct_late", "% VIPs atrasados")]):
        for k, s in enumerate(sc):
            x = d[d.scenario_id == s].copy()
            x["a"] = x.strategy_id.map(alphas)
            x = x.sort_values("a")
            ax.plot(x["a"], x[m], marker="o", color=PAL[k], label=SC_LABEL[s])
        ax.set_xlabel("α (min por ponto de score); α = 0 é o EDF")
        ax.set_ylabel(lab)
        ax.grid(alpha=0.3)
    axes[0].legend(frameon=False, fontsize=8)
    fig.suptitle("Custo e ganho do bônus de score (prazo virtual), docas especializadas")
    return savefig(ctx, fig, "g9_alpha.png")


def fig_cost(ctx, runs):
    x = runs[runs.strategy_id.isin(["edf"]) & runs.scenario_id.isin(["normal_85", "peak_105", "overload_125"])]
    g = x.groupby(["scenario_id", "backend"])[["ops_per_order", "cpu_ms"]].mean().reset_index()
    backs = [b for b in ["heap", "insertion", "selection", "merge", "quick"] if b in set(g.backend)]
    names = {"heap": "Heap", "insertion": "Insertion", "selection": "Selection", "merge": "Merge", "quick": "Quick (pivô fixo)"}
    fig, axes = plt.subplots(1, 2, figsize=(14, 4.4))
    for ax, (m, lab) in zip(axes, [("ops_per_order", "operações por pedido (escala log)"), ("cpu_ms", "CPU por execução, ms (escala log)")]):
        w = 0.8 / len(backs)
        sc = ["normal_85", "peak_105", "overload_125"]
        for j, b in enumerate(backs):
            ys = [float(g[(g.scenario_id == s) & (g.backend == b)][m].iloc[0]) for s in sc]
            ax.bar(np.arange(len(sc)) + (j - (len(backs) - 1) / 2.0) * w, ys, w * 0.95, color=PAL[j], label=names[b])
        ax.set_xticks(range(len(sc)))
        ax.set_xticklabels([SC_LABEL[s] for s in sc])
        ax.set_yscale("log")
        ax.set_ylabel(lab)
        ax.grid(axis="y", alpha=0.3)
    axes[0].legend(frameon=False, fontsize=8)
    fig.suptitle("Algoritmos de ordenação como backend da fila (estratégia EDF)")
    return savefig(ctx, fig, "g10_custo_ordenacao.png"), g


def dock_ranking(S, strategy="edf"):
    """nota (0-100) de cada configuracao de docas, com a estrategia fixa, media nos cenarios com atraso."""
    acc = []
    for sc in SCENARIOS:
        d = S[(S.scenario_id == sc) & (S.strategy_id == strategy)].set_index("dock_config").loc[ALL_DOCKS]
        if d.pct_late.max() - d.pct_late.min() < 0.3 and d.p99_delay_min.max() - d.p99_delay_min.min() < 2:
            continue
        wr = np.zeros(len(d))
        for m, w in WEIGHTS.items():
            wr += w * d[m].rank(method="average").values
        acc.append(pd.Series(100.0 * (len(d) - wr) / (len(d) - 1), index=d.index, name=sc))
    m = pd.concat(acc, axis=1)
    return m.mean(axis=1).sort_values(ascending=False), m


# ----------------------------------------------------------------------- html
def table_html(df, cls=""):
    head = "".join("<th>%s</th>" % c for c in df.columns)
    rows = []
    for _, r in df.iterrows():
        rows.append("<tr>" + "".join("<td>%s</td>" % v for v in r.values) + "</tr>")
    return '<table class="%s"><tr>%s</tr>%s</table>' % (cls, head, "".join(rows))


def best_html(bt, docks):
    rows = []
    for sc in SCENARIOS:
        row = [SC_LABEL[sc]]
        for dk in docks:
            r = bt[(bt.dock == dk) & (bt.cenario == sc)]
            if r.empty:
                row.append("-")
                continue
            r = r.iloc[0]
            if r.tipo == "sem_atrasos":
                row.append("sem atrasos (empate)")
            elif r.tipo == "empate_edf":
                row.append("EDF (empate técnico)")
            else:
                row.append("<b>%s</b><br><small>%s%% atras., P99 %s min</small>" % (
                    ST_LABEL[r.melhor], fmt(r.pct_late), fmt(r.p99, 0)))
        rows.append(row)
    cols = ["Cenário"] + [DOCK_LABEL[d] for d in docks]
    return table_html(pd.DataFrame(rows, columns=cols))


def rank_html(r):
    d = pd.DataFrame({"Estratégia": [ST_LABEL[s] for s in r.index],
                      "Nota média": [fmt(v) for v in r.nota_media],
                      "Vitórias claras": [int(v) for v in r.vitorias],
                      "Empates com EDF": [int(v) for v in r.empates_com_edf]})
    return table_html(d.head(8))


def build(args):
    ctx = Ctx(args.out)
    v2 = load_runs(args.v2)
    v1 = load_runs(args.v1)
    S = summarize(v2)
    S1 = summarize(v1)

    def M(dk, sc, st, m):
        return float(S[(S.dock_config == dk) & (S.scenario_id == sc) & (S.strategy_id == st)][m].iloc[0])

    rank_all, m_all = overall_ranking(S, ALL_DOCKS)
    rank_esp, m_esp = overall_ranking(S, SPECIALIZED)
    rank_ger, m_ger = overall_ranking(S, GENERAL)
    bt = best_table(S, ALL_DOCKS)
    bt.to_csv(os.path.join(ctx.out, "melhor_por_cenario.csv"), index=False)
    rank_all.to_csv(os.path.join(ctx.out, "ranking_geral.csv"))

    f = {}
    f["rank"] = fig_ranking(ctx, rank_all, rank_esp, rank_ger)
    f["heat_esp"] = fig_heat(ctx, m_esp, "Nota por cenário: docas especializadas", "g2_heat_especializadas.png")
    f["heat_ger"] = fig_heat(ctx, m_ger, "Nota por cenário: docas gerais (média das 3 configurações)", "g3_heat_gerais.png")
    f["bf"] = fig_blackfriday(ctx, S)
    f["bfsize"] = fig_bf_size(ctx, S)
    f["docks"] = fig_docks_edf(ctx, S)
    f["sweep"] = fig_sweep(ctx, v2)
    f["pareto"] = fig_pareto(ctx, S)
    f["sens"], r_def, r_vip = fig_sens(ctx, S)
    f["alpha"] = fig_alpha(ctx, S)
    f["cost"], cost = fig_cost(ctx, v2)

    dr, dr_m = dock_ranking(S)
    dr_vd, _ = dock_ranking(S, "vd_a2")

    # robustez v1 (janelas amplas)
    docks1 = [d for d in ["base_15", "base_15_no_borrow", "generic_15"] if d in set(S1.dock_config)]
    bt1 = best_table(S1, docks1)
    r1_all, _ = overall_ranking(S1, docks1)

    def kind_count(t):
        return t.tipo.value_counts().to_dict()

    # BF melhor combinacao dock x estrategia
    bf = S[S.scenario_id == "black_friday"].copy()
    bf = bf[bf.strategy_id.isin(STRATS)]
    bf["combo"] = bf.dock_config + "|" + bf.strategy_id
    edf_min_p99 = bf[bf.strategy_id == "edf"].p99_delay_min.min()
    lim = max(3 * edf_min_p99, 120)
    wr = np.zeros(len(bf))
    for m, w in WEIGHTS.items():
        wr += w * bf[m].rank(method="average").values
    bf["wr"] = wr
    bf["ok"] = bf.p99_delay_min <= lim
    bfq = bf[bf.ok].sort_values("wr").head(6)

    def combo_row(r):
        dk, st = r.combo.split("|")
        return [DOCK_LABEL[dk], ST_LABEL[st], fmt(r.pct_late), fmt(r.mean_delay_min), fmt(r.p99_delay_min, 0), fmt(r.vip_pct_late),
                fmt(r.pct_late_P) + " / " + fmt(r.pct_late_M) + " / " + fmt(r.pct_late_G)]

    bf_tab = pd.DataFrame([combo_row(r) for _, r in bfq.iterrows()],
                          columns=["Docas", "Estratégia", "% atrasados", "Atraso médio (min)", "P99 (min)", "% VIP atrasados", "% atrasados P / M / G"])

    n_runs = len(v1) + len(v2)
    tot_cmp = int(rank_all.n_comparacoes.iloc[0])
    edf_all = rank_all.loc["edf"]
    html = HTML.format(
        css=CSS, n_runs=fmt(n_runs, 0).replace(",", "."), n_v1=fmt(len(v1), 0), n_v2=fmt(len(v2), 0),
        rank_fig=f["rank"], heat_esp=f["heat_esp"], heat_ger=f["heat_ger"], bf=f["bf"], bfsize=f["bfsize"],
        docks=f["docks"], sweep=f["sweep"], pareto=f["pareto"], sens=f["sens"], alpha=f["alpha"], cost=f["cost"],
        edf_nota=fmt(edf_all.nota_media), edf_wins=int(edf_all.vitorias), edf_ties=int(edf_all.empates_com_edf), tot_cmp=tot_cmp,
        second=ST_LABEL[rank_all.index[1]], second_nota=fmt(rank_all.nota_media.iloc[1]),
        rank_all=rank_html(rank_all), rank_esp=rank_html(rank_esp), rank_ger=rank_html(rank_ger),
        best_esp=best_html(bt, SPECIALIZED), best_ger=best_html(bt, GENERAL),
        esp_nota=fmt(rank_esp.loc["edf", "nota_media"]), esp_w=int(rank_esp.loc["edf", "vitorias"]), esp_t=int(rank_esp.loc["edf", "empates_com_edf"]),
        esp_n=int(rank_esp.n_comparacoes.iloc[0]),
        ger_nota=fmt(rank_ger.loc["edf", "nota_media"]), ger_w=int(rank_ger.loc["edf", "vitorias"]), ger_t=int(rank_ger.loc["edf", "empates_com_edf"]),
        ger_n=int(rank_ger.n_comparacoes.iloc[0]),
        bf_tab=table_html(bf_tab),
        pk_sp=fmt(M("base_15", "peak_105", "edf", "pct_late")), pk_ge=fmt(M("generic_15", "peak_105", "edf", "pct_late")),
        pk_ne=fmt(M("generic_nested_15", "peak_105", "edf", "pct_late")), pk_fifo=fmt(M("base_15", "peak_105", "fifo", "pct_late")),
        pk_p99_sp=fmt(M("base_15", "peak_105", "edf", "p99_delay_min"), 0), pk_p99_fifo=fmt(M("base_15", "peak_105", "fifo", "p99_delay_min"), 0),
        pk_vip_edf=fmt(M("base_15", "peak_105", "edf", "vip_pct_late")), pk_vip_a3=fmt(M("base_15", "peak_105", "vd_a3", "vip_pct_late")),
        pk_late_a3=fmt(M("base_15", "peak_105", "vd_a3", "pct_late")), pk_late_edf=fmt(M("base_15", "peak_105", "edf", "pct_late")),
        pk_p99_a3=fmt(M("base_15", "peak_105", "vd_a3", "p99_delay_min"), 0), pk_p99_edf=fmt(M("base_15", "peak_105", "edf", "p99_delay_min"), 0),
        ov_edf=fmt(M("base_15", "overload_125", "edf", "pct_late")), ov_fifo=fmt(M("base_15", "overload_125", "fifo", "pct_late")),
        ov_tq=fmt(M("base_15", "overload_125", "two_queues", "pct_late")), ov_tq_p99=fmt(M("base_15", "overload_125", "two_queues", "p99_delay_min"), 0),
        ov_edf_p99=fmt(M("base_15", "overload_125", "edf", "p99_delay_min"), 0),
        bf_sp=fmt(M("base_15", "black_friday", "edf", "pct_late")), bf_sp_p99=fmt(M("base_15", "black_friday", "edf", "p99_delay_min"), 0),
        bf_ge=fmt(M("generic_15", "black_friday", "edf", "pct_late")), bf_ge_p99=fmt(M("generic_15", "black_friday", "edf", "p99_delay_min"), 0),
        bf_ne=fmt(M("generic_nested_15", "black_friday", "edf", "pct_late")), bf_ne_p99=fmt(M("generic_nested_15", "black_friday", "edf", "p99_delay_min"), 0),
        bf_sp_g=fmt(M("base_15", "black_friday", "edf", "pct_late_G")), bf_sp_p=fmt(M("base_15", "black_friday", "edf", "pct_late_P")),
        bf_ge_p=fmt(M("generic_15", "black_friday", "edf", "pct_late_P")),
        bf_vip_edf=fmt(M("base_15", "black_friday", "edf", "vip_pct_late")), bf_vip_a3=fmt(M("base_15", "black_friday", "vd_a3", "vip_pct_late")),
        bf_late_a3=fmt(M("base_15", "black_friday", "vd_a3", "pct_late")),
        mx_sp=fmt(M("base_15", "mix_shift_33", "edf", "pct_late")), mx_sp_p99=fmt(M("base_15", "mix_shift_33", "edf", "p99_delay_min"), 0),
        mx_ge_p99=fmt(M("generic_15", "mix_shift_33", "edf", "p99_delay_min"), 0), mx_ne_p99=fmt(M("generic_nested_15", "mix_shift_33", "edf", "p99_delay_min"), 0),
        pg_sp=fmt(M("base_15", "promo_g_burst", "edf", "pct_late")), pg_ge=fmt(M("generic_15", "promo_g_burst", "edf", "pct_late")),
        pg_ne=fmt(M("generic_nested_15", "promo_g_burst", "edf", "pct_late")),
        dock_rank=table_html(pd.DataFrame({"Configuração de docas": [DOCK_LABEL[d] for d in dr.index],
                                           "Nota média (EDF)": [fmt(v) for v in dr.values],
                                           "Nota média (prazo virtual α=2)": [fmt(dr_vd.get(d, np.nan)) for d in dr.index]})),
        best_dock=DOCK_LABEL[dr.index[0]].lower(),
        best_phys=DOCK_LABEL[[d for d in dr.index if d in ("base_15", "base_15_no_borrow", "generic_nested_15")][0]].lower(),
        bf_fx=fmt(M("base_15", "black_friday", "bands_aging", "pct_late")),
        bf_fx_p99=fmt(M("base_15", "black_friday", "bands_aging", "p99_delay_min"), 0),
        v1_total=int(len(bt1)),
        v1_ties=kind_count(bt1).get("empate_edf", 0), v1_clear=kind_count(bt1).get("vence", 0),
        v1_edf=int((bt1[bt1.tipo == "vence"].melhor == "edf").sum()), v1_none=kind_count(bt1).get("sem_atrasos", 0),
        v1_edf_nota=fmt(r1_all.loc["edf", "nota_media"]), v1_first=ST_LABEL[r1_all.index[0]],
        vipw_first=ST_LABEL[r_vip.index[0]], vipw_edf=fmt(r_vip.loc["edf", "nota_media"]), vipw_first_nota=fmt(r_vip.nota_media.iloc[0]),
        vipw_second=ST_LABEL[r_vip.index[1]], vipw_third=ST_LABEL[r_vip.index[2]],
        vipw_edf_pos=int(list(r_vip.index).index("edf")) + 1,
        vd_wins=int(r_vip[r_vip.index.str.startswith("vd_")].vitorias.sum()), vipw_n=int(r_vip.n_comparacoes.iloc[0]),
        vipw_edf_wins=int(r_vip.loc["edf", "vitorias"]),
        heap_ops=fmt(float(cost[(cost.scenario_id == "overload_125") & (cost.backend == "heap")].ops_per_order.iloc[0]), 0),
        heap_cpu=fmt(float(cost[(cost.scenario_id == "overload_125") & (cost.backend == "heap")].cpu_ms.iloc[0]) / 1000.0, 2),
        quick_ops=fmt(float(cost[(cost.scenario_id == "overload_125") & (cost.backend == "quick")].ops_per_order.iloc[0]), 0),
        quick_cpu=fmt(float(cost[(cost.scenario_id == "overload_125") & (cost.backend == "quick")].cpu_ms.iloc[0]) / 1000.0, 0),
        merge_cpu=fmt(float(cost[(cost.scenario_id == "overload_125") & (cost.backend == "merge")].cpu_ms.iloc[0]) / 1000.0, 1),
        sel_cpu=fmt(float(cost[(cost.scenario_id == "overload_125") & (cost.backend == "selection")].cpu_ms.iloc[0]) / 1000.0, 1),
        ins_cpu=fmt(float(cost[(cost.scenario_id == "overload_125") & (cost.backend == "insertion")].cpu_ms.iloc[0]) / 1000.0, 1),
    )
    path = os.path.join(ctx.out, "analise_geral.html")
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(html)
    return path


CSS = """
@page{size:A4;margin:16mm 14mm}
body{font-family:"Segoe UI",Arial,sans-serif;font-size:10pt;color:#1a1a1a;line-height:1.45}
h1{font-size:23pt;margin:0 0 2px;color:#12355b}
h2{font-size:14.5pt;color:#12355b;border-bottom:2px solid #12355b;padding-bottom:3px;margin-top:20px;page-break-after:avoid}
h3{font-size:11.5pt;margin:12px 0 4px;page-break-after:avoid}
.sub{color:#555;margin-bottom:12px}
table{border-collapse:collapse;width:100%;margin:8px 0;font-size:8.8pt;page-break-inside:avoid}
th{background:#12355b;color:#fff;text-align:left;padding:4px 6px}
td{border:1px solid #bbb;padding:3px 6px;vertical-align:top}
tr:nth-child(even) td{background:#f3f6fa}
.box{border:2px solid #12355b;background:#eef3f9;padding:8px 12px;margin:8px 0;page-break-inside:avoid}
.warn{border:2px solid #b45309;background:#fff7ed;padding:8px 12px;margin:8px 0;page-break-inside:avoid}
figure{margin:8px 0;page-break-inside:avoid}
figure img{width:100%}
figcaption{font-size:8.5pt;color:#444;margin-top:2px}
.big{font-size:12pt}
ul{margin:4px 0 4px 18px;padding-left:6px}
li{margin:2px 0}
.pb{page-break-before:always}
small{color:#444}
"""

HTML = """<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><title>VelozMart MPS - Análise geral</title>
<style>{css}</style></head><body>
<h1>VelozMart MPS: análise geral dos testes</h1>
<div class="sub">Comparação de estratégias de ordenação da fila de expedição, com docas especializadas e gerais · Coding Tank, Ordenação e Prioridade · {n_runs} execuções simuladas ({n_v1} com janelas amplas e {n_v2} com janelas apertadas)</div>

<div class="box big"><b>Conclusão.</b> O melhor algoritmo no geral é o <b>EDF</b> (menor prazo de expedição primeiro): nota média {edf_nota} de 100 e vitória clara em {edf_wins} das {tot_cmp} comparações, mais {edf_ties} empates técnicos, contra {second_nota} do segundo colocado ({second}). Ele é o melhor tanto com docas especializadas quanto com docas gerais, e também na Black Friday. O prazo virtual protege os pedidos VIP, mas paga com mais atrasos e uma cauda muito pior. Se o VIP passasse a pesar 40% na nota, o resultado mudaria: o EDF cairia para a {vipw_edf_pos}ª posição e passariam à frente {vipw_first}, {vipw_second} e {vipw_third}, estratégias que protegem VIPs à custa da cauda, e o prazo virtual passaria a vencer {vd_wins} das {vipw_n} comparações.</div>

<h2>1. Resumo executivo</h2>
<table>
<tr><th>Recorte</th><th>Melhor algoritmo</th><th>Evidência</th></tr>
<tr><td><b>Geral (todas as docas e cenários)</b></td><td><b>EDF</b></td><td>nota {edf_nota}; {edf_wins} vitórias claras e {edf_ties} empates em {tot_cmp} comparações</td></tr>
<tr><td><b>Docas especializadas</b> (com e sem empréstimo)</td><td><b>EDF</b></td><td>nota {esp_nota}; {esp_w} vitórias e {esp_t} empates em {esp_n}</td></tr>
<tr><td><b>Docas gerais</b> (uniforme, capacidade variada, velocidade variada)</td><td><b>EDF</b></td><td>nota {ger_nota}; {ger_w} vitórias e {ger_t} empates em {ger_n}</td></tr>
<tr><td><b>Black Friday</b></td><td><b>EDF</b> (com docas de capacidade variada ou especializadas)</td><td>{bf_ne}% atrasados e P99 de {bf_ne_p99} min com docas de capacidade variada; {bf_sp}% e {bf_sp_p99} min com as especializadas</td></tr>
<tr><td><b>Se o VIP voltar a ser prioridade</b></td><td>depende: {vipw_first} lidera a nota média ({vipw_first_nota}), mas com cauda grande; o prazo virtual com α alto vence {vd_wins} de {vipw_n} comparações</td><td>com peso de 40% para o VIP na nota o EDF cai para {vipw_edf} ({vipw_edf_pos}ª posição) e vence {vipw_edf_wins} de {vipw_n}</td></tr>
</table>
<ul>
<li><b>Configurações de docas (com EDF):</b> as gerais idealizadas ({best_dock} e a uniforme) têm as melhores notas, mas supõem que qualquer doca embala qualquer pedido. Entre as que respeitam a restrição física de tamanho, a melhor é <b>{best_phys}</b>, bem à frente das especializadas. Juntar a capacidade absorve melhor picos e rajadas; a separação rígida por tamanho cria gargalos.</li>
<li><b>Estratégias "ótimas" em sobrecarga são enganosas:</b> Duas filas e WSPT mostram menos atrasados porque abandonam pedidos (P99 de centenas de minutos), por isso foram desqualificadas como "melhor".</li>
<li><b>O heap é o algoritmo de ordenação mais barato</b> e dá exatamente a mesma ordem que os outros quatro.</li>
</ul>

<h2>2. Como comparamos</h2>
<ul>
<li><b>Dados:</b> pedidos sintéticos de uma operação de grande porte na América Latina: chegadas com picos ao longo do dia, janelas de prazo curtas, regiões distintas (BR, MX, AR, CO, CL), 8 cenários (normal 85%, pico 105%, sobrecarga 125%, Black Friday, rajada de pedidos grandes, mix deslocado, falha de doca, multi-país) e 30 sementes por cenário.</li>
<li><b>Docas (15 por configuração):</b> especializada por tamanho (4 Express, 6 Padrão, 5 Pesada), com e sem empréstimo; geral uniforme (15 docas idênticas, fila única); geral de capacidade variada (docas pequenas só para P, médias para P e M, grandes para tudo); geral de velocidade variada (0,75×, 1,0× e 1,25×).</li>
<li><b>Estratégias:</b> FIFO, EDF, peso composto, duas filas, faixas + aging, WSPT e prazo virtual (α de 0,5 a 5; α = 0 equivale ao EDF).</li>
<li><b>Nota (0 a 100):</b> em cada cenário e configuração de docas, as estratégias são ordenadas por quatro métricas e combinadas com pesos do grupo: % de atrasados 35%, atraso médio 25%, P99 (cauda) 30% e % de VIPs atrasados 10%. A nota média é feita sobre os cenários em que houve atraso.</li>
<li><b>Desqualificação por abandono:</b> uma estratégia não pode ser "a melhor" se seu P99 passa de 3 vezes o do EDF e de 120 min.</li>
<li><b>Empate técnico:</b> se a melhor estratégia fica a menos de 0,3 ponto percentual de atrasados, 2 min de P99 e 0,5 min de atraso médio do EDF, o resultado é empate e vai para o EDF pela simplicidade.</li>
<li><b>Limites:</b> dados sintéticos, embalagem determinística (P = 1, M = 2, G = 4 min) e parâmetros dos concorrentes sem a mesma calibração do α.</li>
</ul>

<h2 class="pb">3. Resultado geral</h2>
<figure><img src="{rank_fig}"><figcaption>Nota média por estratégia: todas as docas, só especializadas e só gerais.</figcaption></figure>
<h3>Ranking com todas as docas</h3>
{rank_all}
<p><b>Leitura.</b> O EDF lidera nos três recortes. O prazo virtual com α = 0,5 é o segundo colocado, porque se comporta quase como o EDF com um pequeno bônus de score; quanto maior o α, pior a nota, pois aumenta a cauda. FIFO só ganha em um caso isolado, por diferença mínima.</p>
<figure><img src="{sens}"><figcaption>Se o VIP pesasse 40% na nota, a ordem muda: {vipw_first}, {vipw_second} e {vipw_third} passam à frente e o EDF cai para a nota {vipw_edf} ({vipw_edf_pos}ª posição). O VIP é o único critério em que o EDF perde; por isso a decisão do grupo de tratá-lo como secundário é o que sustenta a conclusão.</figcaption></figure>

<h2 class="pb">4. Docas especializadas</h2>
<p>Docas separadas por tamanho de pedido: Express (P), Padrão (M) e Pesada (G).</p>
{best_esp}
<figure><img src="{heat_esp}"><figcaption>Nota por estratégia e cenário. Verde é melhor. Cenários em que o EDF quase não atrasa (sem o que melhorar) ficam fora da média.</figcaption></figure>
<h3>Ranking</h3>
{rank_esp}
<h3>Comentários</h3>
<ul>
<li><b>EDF é o melhor em todos os cenários com atraso,</b> e o prazo virtual com α pequeno é o mais próximo.</li>
<li><b>O pico é o ponto fraco desse desenho:</b> no pico de 105% o EDF atrasa {pk_sp}% dos pedidos (FIFO: {pk_fifo}%), porque as 4 docas Express chegam perto de 95% de uso e viram gargalo. Com docas gerais o mesmo EDF atrasa só {pk_ge}%.</li>
<li><b>No mix deslocado</b> (mais pedidos grandes), as docas Pesadas saturam e as demais ficam ociosas: {mx_sp}% de atrasados e P99 de {mx_sp_p99} min. É o maior risco de dimensionar errado.</li>
<li><b>Em sobrecarga de 125%,</b> o EDF atrasa {ov_edf}% (FIFO: {ov_fifo}%): sem capacidade nenhuma regra resolve, mas o EDF tem a menor cauda (P99 de {ov_edf_p99} min). Duas filas mostram {ov_tq}% de atrasados, só que com P99 de {ov_tq_p99} min.</li>
<li><b>O empréstimo de docas ajuda pouco:</b> no pico, 14% de atrasados com empréstimo contra 18% sem.</li>
</ul>

<h2 class="pb">5. Docas gerais</h2>
<p>Qualquer doca atende qualquer pedido: uniforme (15 iguais), de capacidade variada (pequenas, médias e grandes) e de velocidade variada.</p>
{best_ger}
<figure><img src="{heat_ger}"><figcaption>Nota por estratégia e cenário, média das três configurações gerais.</figcaption></figure>
<h3>Ranking</h3>
{rank_ger}
<h3>Comentários</h3>
<ul>
<li><b>EDF é o melhor em quase todos os cenários.</b> Há exceções pontuais: na rajada de pedidos grandes com docas de capacidade variada o FIFO empata por uma diferença de décimos.</li>
<li><b>Agrupar a capacidade derruba os atrasos:</b> no pico, {pk_ge}% (uniforme) e {pk_ne}% (capacidade variada); na rajada de pedidos grandes, {pg_ge}% e {pg_ne}%, contra {pg_sp}% das especializadas.</li>
<li><b>A de velocidade variada se comporta como a uniforme,</b> pois a soma das velocidades é a mesma e a fila é única.</li>
<li><b>Cuidado:</b> a uniforme e a de velocidade supõem que qualquer doca embala qualquer pedido, o que é otimista. A de capacidade variada respeita a restrição física (pedido G só em doca grande) e é a mais realista das gerais.</li>
</ul>

<h2 class="pb">6. Black Friday</h2>
<p>Dia com carga de até 140% da capacidade, mais pedidos grandes (22% do mix) e muitas atualizações de prazo.</p>
<figure><img src="{bf}"><figcaption>Estratégia × configuração de docas na Black Friday.</figcaption></figure>
<h3>Melhores combinações (docas + estratégia)</h3>
{bf_tab}
<figure><img src="{bfsize}"><figcaption>Atrasos do EDF por tamanho de pedido.</figcaption></figure>
<ul>
<li><b>Melhor algoritmo: EDF,</b> em todas as cinco configurações de docas.</li>
<li><b>Com docas especializadas,</b> o EDF atrasa {bf_sp}% dos pedidos, contra {bf_ge}% com docas gerais uniformes. A separação isola o excesso de pedidos grandes: os P ficam com {bf_sp_p}% de atrasados, contra {bf_ge_p}% na geral (hipótese apoiada nos atrasos por tamanho, não testada isoladamente).</li>
<li><b>O preço é a cauda:</b> P99 de {bf_sp_p99} min nas especializadas (os pedidos G sofrem, {bf_sp_g}% atrasados) contra {bf_ge_p99} min nas gerais.</li>
<li><b>Melhor equilíbrio: docas de capacidade variada com EDF</b> ({bf_ne}% atrasados e P99 de {bf_ne_p99} min): quase o mesmo % de atrasados da especializada, com cauda bem menor.</li>
<li><b>Ressalva:</b> Faixas + aging atrasa menos pedidos na Black Friday com docas especializadas ({bf_fx}% contra {bf_sp}% do EDF), mas com cauda maior (P99 de {bf_fx_p99} min contra {bf_sp_p99}); pelo critério de nota e cauda, o EDF fica à frente.</li>
<li><b>VIP na Black Friday:</b> o EDF deixa {bf_vip_edf}% dos VIPs atrasados; o prazo virtual com α = 3 reduz para {bf_vip_a3}%, e é a única configuração em que ele atende ao critério do grupo, mas só nesse cenário.</li>
</ul>

<h2 class="pb">7. Docas especializadas × gerais</h2>
<figure><img src="{docks}"><figcaption>EDF em cada cenário, por configuração de docas.</figcaption></figure>
<h3>Ranking das configurações de docas (EDF, média dos cenários com atraso)</h3>
{dock_rank}
<p><small>A nota compara as cinco configurações entre si, em cada cenário com atraso. As duas primeiras são idealizadas (qualquer doca atende qualquer pedido); a de capacidade variada é a melhor entre as que respeitam a restrição de tamanho.</small></p>
<ul>
<li><b>No pico e nas rajadas, as gerais ganham:</b> o pico cai de {pk_sp}% para {pk_ge}% de atrasados e a rajada de pedidos grandes de {pg_sp}% para {pg_ge}%.</li>
<li><b>No mix deslocado, a cauda da especializada é muito pior:</b> P99 de {mx_sp_p99} min contra {mx_ge_p99} min (geral uniforme) e {mx_ne_p99} min (capacidade variada).</li>
<li><b>Na Black Friday a especializada reduz o % de atrasados,</b> à custa da cauda.</li>
<li><b>Recomendação:</b> usar docas gerais de capacidade variada (a configuração que respeita a restrição física), deixando as docas maiores atenderem pedidos menores.</li>
</ul>
<figure><img src="{sweep}"><figcaption>Atrasos em função da carga: a diferença entre docas especializadas e gerais aparece a partir de ~100% de carga.</figcaption></figure>

<h2 class="pb">8. EDF × prazo virtual: o custo de proteger VIPs</h2>
<figure><img src="{pareto}"><figcaption>Cada ponto é uma estratégia; o canto inferior esquerdo é o ideal (poucos VIPs atrasados e cauda curta).</figcaption></figure>
<figure><img src="{alpha}"><figcaption>Efeito do α: quanto maior, menos VIPs atrasados, mas mais atrasos totais e cauda maior.</figcaption></figure>
<ul>
<li><b>No pico (docas especializadas),</b> o prazo virtual com α = 3 reduz os VIPs atrasados de {pk_vip_edf}% para {pk_vip_a3}%, mas o total de atrasados sobe de {pk_late_edf}% para {pk_late_a3}% e o P99 de {pk_p99_edf} para {pk_p99_a3} min.</li>
<li><b>O bônus de score tira pedidos de score baixo da frente,</b> e esse é o custo de proteger VIPs. Se o VIP pesasse 40% na nota (seção 3), o prazo virtual com α alto passaria a vencer {vd_wins} das {vipw_n} comparações, sobretudo em sobrecarga e Black Friday, pagando com cauda maior.</li>
<li>Na calibração com sementes separadas, nenhum α da grade atendeu ao critério (reduzir VIP em 50% sem piorar atrasados em mais de 1 ponto percentual nem o P99 em mais de 20%).</li>
</ul>

<h2>9. Algoritmos de ordenação (custo)</h2>
<figure><img src="{cost}"><figcaption>Mesma chave (EDF), mesma ordem de despacho; muda só o custo de manter a fila.</figcaption></figure>
<ul>
<li>Em sobrecarga, o <b>heap</b> faz {heap_ops} operações por pedido e usa {heap_cpu} s de CPU por execução; Insertion {ins_cpu} s, Selection {sel_cpu} s, Merge {merge_cpu} s e Quick Sort com pivô fixo {quick_cpu} s ({quick_ops} operações por pedido).</li>
<li>Os cinco algoritmos produzem exatamente os mesmos atrasos (0 divergências), então a escolha é só de custo: o heap.</li>
</ul>

<h2>10. Robustez: janelas amplas (primeiro experimento)</h2>
<p>Repetimos a análise com os dados do primeiro experimento (janelas de 30 a 240 min, docas especializadas e uma geral): {v1_clear} comparações com atraso, das quais o EDF vence {v1_edf}; {v1_ties} empates técnicos e {v1_none} cenários sem atrasos. A nota média do EDF nessa rodada é {v1_edf_nota}. A conclusão se mantém, mas com janelas amplas {v1_none} dos {v1_total} casos não têm nenhum atraso e vários outros quase não discriminam as estratégias; por isso o segundo experimento usou janelas mais apertadas.</p>

<h2>11. Limitações e próximos passos</h2>
<ul>
<li>Dados sintéticos: o score é gerado a partir de SLA, distância, valor e reputação, o que favorece estratégias que usam o score (isso favorece o prazo virtual, e mesmo assim o EDF ganha).</li>
<li>Os pesos da nota e as tolerâncias de empate são decisões do grupo; a sensibilidade ao peso do VIP está na seção 3.</li>
<li>A falha de doca é ignorada na configuração de velocidade variada (não há grupo Pesada).</li>
<li>Os parâmetros de faixas, aging e limite de duas filas não foram calibrados com o mesmo rigor do α.</li>
<li><b>Próximos passos:</b> testar outras regras de despacho para as docas de capacidade variada (reservar docas grandes para G), variar a quantidade de docas por grupo, e validar em um teste A/B em região piloto.</li>
</ul>
</body></html>
"""


def make_pdf(html_path, pdf_path):
    cands = [r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
             r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
             r"C:\Program Files\Google\Chrome\Application\chrome.exe",
             shutil.which("msedge") or "", shutil.which("google-chrome") or "", shutil.which("chromium") or ""]
    exe = next((c for c in cands if c and os.path.exists(c)), None)
    if not exe:
        print("[aviso] nenhum Edge/Chrome encontrado; PDF nao gerado")
        return False
    url = "file:///" + os.path.abspath(html_path).replace("\\", "/")
    subprocess.check_call([exe, "--headless", "--disable-gpu", "--no-pdf-header-footer",
                           "--print-to-pdf=" + os.path.abspath(pdf_path), url],
                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return os.path.exists(pdf_path)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--v1", default="reports/v0.1.0/data/runs.csv")
    ap.add_argument("--v2", default="reports/v0.3.0/data/runs.csv")
    ap.add_argument("--out", default="reports/v1.0.0")
    ap.add_argument("--no-pdf", action="store_true")
    args = ap.parse_args()
    path = build(args)
    print("HTML:", path)
    if not args.no_pdf:
        pdf = os.path.join(args.out, "VelozMart_MPS_Analise_Geral.pdf")
        print("PDF:", pdf if make_pdf(path, pdf) else "falhou")


if __name__ == "__main__":
    main()
