"""Carrega e resolve `configs/scenarios.json` (defaults + cenario)."""
import copy
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DEFAULT_CONFIG = os.path.join(ROOT, "configs", "scenarios.json")

EVAL_SEEDS = tuple(range(0, 30))
CALIB_SEEDS = tuple(range(1000, 1010))


def load_config(path=None):
    with open(path or DEFAULT_CONFIG, "r", encoding="utf-8") as f:
        return json.load(f)


def scenario_ids(cfg):
    return list(cfg["scenarios"].keys())


def resolve_scenario(cfg, scenario_id):
    """Retorna dict completo do cenario (defaults aplicados, regioes e perfil resolvidos)."""
    if scenario_id not in cfg["scenarios"]:
        raise KeyError("cenario desconhecido: %s" % scenario_id)
    sc = copy.deepcopy(cfg["defaults"])
    sc.update(copy.deepcopy(cfg["scenarios"][scenario_id]))
    sc["scenario_id"] = scenario_id
    regions = {}
    for name, over in sc["regions"].items():
        r = copy.deepcopy(cfg["regions"][name])
        r.update(over)
        regions[name] = r
    tot = sum(r["share"] for r in regions.values())
    for r in regions.values():
        r["share"] = r["share"] / tot
    sc["regions"] = regions
    sc["profile_def"] = cfg["profiles"][sc["profile"]]
    return sc


def parse_seeds(text):
    """Aceita '0-29' ou '0,5,9' (ou mistura '0-2,9')."""
    out = []
    for part in str(text).split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            a, b = part.split("-", 1)
            out.extend(range(int(a), int(b) + 1))
        else:
            out.append(int(part))
    seen = []
    for s in out:
        if s not in seen:
            seen.append(s)
    return seen
