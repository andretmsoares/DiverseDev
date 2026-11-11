#!/usr/bin/env bash
# Experimento completo (da raiz do repositorio). Cada parte vai para results/parts/<nome>.
# Requer: python -m mps.datagen --scenarios all --seeds 0-29 --out data/synthetic
set -euo pipefail
W=${WORKERS:-6}
P=results/parts
SIM="python -m mps.sim --data data/synthetic --workers $W"
rm -rf "$P"; mkdir -p "$P"

# A) docas especializadas base_15, todos os cenarios e estrategias
$SIM --out $P/a_base --docks base_15 --scenarios all --strategies all --seeds 0-29

# B) variacoes de docas nos cenarios de carga e estresse
$SIM --out $P/b_docks --docks generic_15,base_15_no_borrow \
     --scenarios normal_85,peak_105,overload_125,black_friday,mix_shift_33,dock_outage,promo_g_burst \
     --strategies all --seeds 0-29

# C) algoritmos de ordenacao como backend da fila (apenas backends alem do heap; o heap vem da parte A)
$SIM --out $P/c_backends --docks base_15 --scenarios normal_85,peak_105,overload_125 \
     --strategies all --backends insertion,selection,merge,quick --seeds 0-9

# D) benchmark isolado dos algoritmos de ordenacao
python scripts/bench_sorting.py

python scripts/merge_results.py --out results $P/a_base $P/b_docks $P/c_backends
echo "ok: results/runs.csv pronto para analysis/analyze.py"
