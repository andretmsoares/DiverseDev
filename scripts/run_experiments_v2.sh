#!/usr/bin/env bash
# Experimento v2: janelas apertadas (30-120 min) e 5 configuracoes de docas (da raiz do repositorio).
# Requer: python -m mps.datagen --scenarios all --seeds 0-29 --window-profile tight --out data/synthetic_tight
#         python -m mps.datagen --scenarios all --calibration --window-profile tight --out data/synthetic_tight
# Variaveis: DATA (padrao data/synthetic_tight), OUT (padrao results/v2), WORKERS (padrao 6)
set -euo pipefail
DATA=${DATA:-data/synthetic_tight}
OUT=${OUT:-results/v2}
W=${WORKERS:-6}
P=$OUT/parts
SIM="python -m mps.sim --data $DATA --workers $W"
CORE=normal_85,peak_105,overload_125,black_friday,promo_g_burst,mix_shift_33,dock_outage,regional_mix
DOCKS=base_15,base_15_no_borrow,generic_15,generic_nested_15,generic_speed_15
rm -rf "$P"; mkdir -p "$P"

# A) comparacao de docas (especializadas x genericas) nos cenarios principais, todas as estrategias
$SIM --out $P/a_docks --docks $DOCKS --scenarios $CORE --strategies all --seeds 0-29

# B) curva carga x atraso com docas especializadas e com genericas uniformes
$SIM --out $P/b_sweep --docks base_15,generic_15 \
     --scenarios sweep_70,sweep_75,sweep_80,sweep_85,sweep_90,sweep_95,sweep_100,sweep_105,sweep_110,sweep_115,sweep_120,sweep_125,sweep_130 \
     --strategies fifo,edf,composite,two_queues,bands_aging,wspt,vd_a1,vd_a2,vd_a3 --seeds 0-29

# C) calibracao do alpha em sementes separadas (1000-1009), docas principais
$SIM --out $P/c_calib --calibration --docks base_15 \
     --scenarios normal_85,peak_105,overload_125,black_friday --strategies all

# D) algoritmos de ordenacao como backend (sementes 0-4)
$SIM --out $P/d_backends --docks base_15 --scenarios normal_85,peak_105,overload_125 \
     --strategies all --backends insertion,selection,merge,quick --seeds 0-4

python scripts/merge_results.py --out $OUT $P/a_docks $P/b_sweep $P/d_backends
# calibracao fica separada (prefixo calibration_)
cp $P/c_calib/calibration_runs.csv $OUT/calibration_runs.csv
cp results/bench_sorting.csv $OUT/bench_sorting.csv 2>/dev/null || true
echo "ok: $OUT/runs.csv pronto para analysis/analyze.py --results $OUT"
