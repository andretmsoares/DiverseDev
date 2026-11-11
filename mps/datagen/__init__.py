"""Gerador de dados sinteticos (ver docs/CONTRACT.md secao 3 e docs/DATA.md)."""
from mps.datagen.config import CALIB_SEEDS, EVAL_SEEDS, load_config, resolve_scenario  # noqa: F401
from mps.datagen.generator import generate_events, generate_orders  # noqa: F401
