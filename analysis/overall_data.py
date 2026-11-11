"""Calculos da analise geral (usados por analysis/overall.py).

Metodologia de ranking: em cada grupo (conjunto de docas, cenario) as estrategias sao
ordenadas por quatro metricas (menor e melhor) e combinadas numa nota ponderada de postos.
Pesos padrao: % atrasados 35%, atraso medio 25%, P99 30%, % VIP atrasados 10% (o grupo
decidiu que o VIP e criterio secundario). Pesos alternativos servem para testar robustez.
"""
import os

import numpy as np
import pandas as pd

WEIGHTS = {"pct_late": 0.35, "mean_delay_min": 0.25, "p99_delay_min": 0.30, "vip_pct_late": 0.10}
WEIGHTS_VIP = {"pct_late": 0.25, "mean_delay_min": 0.15, "p99_delay_min": 0.20, "vip_pct_late": 0.40}
SCENARIOS = ["normal_85", "peak_105", "overload_125", "black_friday", "promo_g_burst",
             "mix_shift_33", "dock_outage", "regional_mix"]
SPECIALIZED = ["base_15", "base_15_no_borrow"]
GENERAL = ["generic_15", "generic_nested_15", "generic_speed_15"]
ALL_DOCKS = SPECIALIZED + GENERAL
STRATS = ["fifo", "edf", "composite", "two_queues", "bands_aging", "wspt",
          "vd_a0.5", "vd_a1", "vd_a2", "vd_a3", "vd_a5"]  # vd_a0 == EDF (com outro desempate), fica fora do ranking
TIE_LATE_PP = 0.3
TIE_P99_MIN = 2.0

METRICS = ["pct_late", "mean_delay_min", "p95_delay_min", "p99_delay_min", "max_delay_min", "vip_pct_late",
           "throughput_per_h", "pct_late_P", "pct_late_M", "pct_late_G", "idle_pct", "n_loans"]


def load_runs(path):
    r = pd.read_csv(path)
    if "backend" not in r.columns:
        r["backend"] = "heap"
    r["backend"] = r["backend"].fillna("heap")
    return r


def summarize(runs):
    """media por (dock_config, scenario_id, strategy_id) so com backend heap."""
    h = runs[runs.backend == "heap"]
    cols = [c for c in METRICS if c in h.columns] + [c for c in h.columns if c.startswith("util_")]
    g = h.groupby(["dock_config", "scenario_id", "strategy_id"])[cols].mean().reset_index()
    return g


NO_LATE_PP = 0.5       # EDF abaixo disso (e P99 < 2 min) => cenario sem atrasos relevantes
TOL_LATE_PP = 0.3     # diferenca de % atrasados dentro da qual duas estrategias empatam
TOL_P99_MIN = 2.0      # idem para o P99
TOL_MEAN_MIN = 0.5     # idem para o atraso medio
GUARD_FACTOR = 3.0     # desqualifica quem tem P99 > 3x o do EDF ...
GUARD_FLOOR_MIN = 120  # ... e acima de 120 min (abandono de pedidos)


def score_group(df, weights=WEIGHTS):
    """Nota (0-100) por posto ponderado e flag `qualificada` (guarda contra abandono de pedidos)."""
    df = df[df.strategy_id.isin(STRATS)].copy()
    n = len(df)
    wr = np.zeros(n)
    for m, w in weights.items():
        wr += w * df[m].rank(method="average").values
    df["rank_score"] = wr
    df["nota"] = 100.0 * (n - wr) / (n - 1) if n > 1 else 100.0
    edf = df[df.strategy_id == "edf"]
    lim = max(GUARD_FACTOR * float(edf.p99_delay_min.iloc[0]), GUARD_FLOOR_MIN) if len(edf) else float("inf")
    df["qualificada"] = df.p99_delay_min <= lim
    return df.sort_values("rank_score")


def is_tie(df):
    d = df[df.strategy_id.isin(STRATS)]
    if (d.pct_late.max() - d.pct_late.min() < TIE_LATE_PP) and (d.p99_delay_min.max() - d.p99_delay_min.min() < TIE_P99_MIN):
        return True
    # o proprio EDF quase nao atrasa: nao ha o que melhorar (diferencas entre estrategias sao ruido)
    edf = d[d.strategy_id == "edf"]
    return bool(len(edf) and float(edf.pct_late.iloc[0]) < NO_LATE_PP and float(edf.p99_delay_min.iloc[0]) < TIE_P99_MIN)


def outcome(d, weights=WEIGHTS):
    """Resultado de um grupo (dock, cenario): (tipo, melhor_id, linha_do_melhor, tabela).
    tipo: 'sem_atrasos' | 'empate_edf' | 'vence'."""
    s = score_group(d, weights)
    if is_tie(d):
        return "sem_atrasos", "edf", s.iloc[0], s
    q = s[s.qualificada]
    top = q.iloc[0]
    edf = s[s.strategy_id == "edf"].iloc[0]
    if top.strategy_id != "edf" and abs(top.pct_late - edf.pct_late) < TOL_LATE_PP             and abs(top.p99_delay_min - edf.p99_delay_min) < TOL_P99_MIN             and abs(top.mean_delay_min - edf.mean_delay_min) < TOL_MEAN_MIN:
        return "empate_edf", "edf", edf, s
    return "vence", top.strategy_id, top, s


def best_table(summ, docks, scenarios=SCENARIOS, weights=WEIGHTS):
    rows = []
    for dk in docks:
        for sc in scenarios:
            d = summ[(summ.dock_config == dk) & (summ.scenario_id == sc)]
            if d.empty:
                continue
            kind, bid, row, s = outcome(d, weights)
            edf = s[s.strategy_id == "edf"].iloc[0]
            rows.append({"dock": dk, "cenario": sc, "tipo": kind, "melhor": bid, "nota": row.nota,
                         "pct_late": row.pct_late, "p99": row.p99_delay_min, "vip": row.vip_pct_late,
                         "edf_pct_late": edf.pct_late, "edf_p99": edf.p99_delay_min, "edf_vip": edf.vip_pct_late,
                         "desqualificadas": ", ".join(s[~s.qualificada].strategy_id)})
    return pd.DataFrame(rows)


def notas_matrix(summ, docks, scenarios=SCENARIOS, weights=WEIGHTS):
    """nota media por estrategia x cenario (media sobre os docks do grupo), ignorando grupos sem atrasos."""
    acc = {}
    for dk in docks:
        for sc in scenarios:
            d = summ[(summ.dock_config == dk) & (summ.scenario_id == sc)]
            if d.empty or is_tie(d):
                continue
            acc.setdefault(sc, []).append(score_group(d, weights).set_index("strategy_id")["nota"])
    return pd.DataFrame({sc: pd.concat(l, axis=1).mean(axis=1) for sc, l in acc.items()}).reindex(STRATS)


def overall_ranking(summ, docks, scenarios=SCENARIOS, weights=WEIGHTS):
    m = notas_matrix(summ, docks, scenarios, weights)
    out = pd.DataFrame({"nota_media": m.mean(axis=1)})
    wins = {x: 0 for x in STRATS}
    ties = 0
    total = 0
    for dk in docks:
        for sc in scenarios:
            d = summ[(summ.dock_config == dk) & (summ.scenario_id == sc)]
            if d.empty:
                continue
            kind, bid, _, _ = outcome(d, weights)
            if kind == "sem_atrasos":
                continue
            total += 1
            if kind == "empate_edf":
                ties += 1
            else:
                wins[bid] += 1
    out["vitorias"] = pd.Series(wins)
    out["empates_com_edf"] = 0
    out.loc["edf", "empates_com_edf"] = ties
    out["n_comparacoes"] = total
    return out.sort_values("nota_media", ascending=False), m
