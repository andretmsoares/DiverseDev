"""CLI: python -m mps.sim --data data/synthetic --out results ..."""
import argparse
import sys

from mps.sim.runner import parse_seeds, run_all


def main(argv=None):
    ap = argparse.ArgumentParser(prog="python -m mps.sim",
                                 description="Simulador da fila de expedicao VelozMart MPS")
    ap.add_argument("--data", default="data/synthetic")
    ap.add_argument("--out", default="results")
    ap.add_argument("--scenarios", default="all", help="'all' ou ids separados por virgula")
    ap.add_argument("--strategies", default="all", help="'all' ou ids de configs/strategies.json")
    ap.add_argument("--docks", default="base_15", help="ids de configs/docks.json, separados por virgula")
    ap.add_argument("--seeds", default=None, help="ex.: 0-29 ou 0,5,9 (padrao 0-29)")
    ap.add_argument("--workers", type=int, default=1)
    ap.add_argument("--calibration", action="store_true",
                    help="usa seeds 1000-1009 e escreve calibration_*.csv")
    args = ap.parse_args(argv)
    seeds_text = args.seeds or ("1000-1009" if args.calibration else "0-29")
    scen = "all" if args.scenarios == "all" else [s for s in args.scenarios.split(",") if s]
    strat = "all" if args.strategies == "all" else [s for s in args.strategies.split(",") if s]
    run_all(args.data, args.out, scen, strat, [d for d in args.docks.split(",") if d],
            parse_seeds(seeds_text), workers=args.workers, calibration=args.calibration,
            argv=["python", "-m", "mps.sim"] + (argv if argv is not None else sys.argv[1:]))


if __name__ == "__main__":
    main()
