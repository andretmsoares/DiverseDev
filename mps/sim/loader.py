"""Leitura de dados sinteticos e configuracoes (ver docs/CONTRACT.md, secao 3)."""
import csv
import json
import os

from mps.models import WARMUP_MIN, Order, OrderEvent

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _num(s):
    return None if s is None or s.strip() == "" else float(s)


def load_orders(path):
    orders = []
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            orders.append(Order(row["order_id"], float(row["arrival_min"]),
                                float(row["dispatch_window_min"]),
                                float(row["priority_score"]), row["size_category"],
                                float(row["deadline_min"])))
    # garante ordem de chegada (estavel) e atribui seq
    orders.sort(key=lambda o: o.arrival_min)
    for i, o in enumerate(orders):
        o.seq = i
    return orders


def load_events(path):
    events = []
    if not os.path.exists(path):
        return events
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            events.append(OrderEvent(row["event_id"], float(row["time_min"]), row["order_id"],
                                     row["kind"], _num(row.get("new_score")),
                                     _num(row.get("new_deadline_min"))))
    events.sort(key=lambda e: e.time_min)
    return events


def load_manifest(scenario_dir):
    p = os.path.join(scenario_dir, "manifest.json")
    if not os.path.exists(p):
        return {}
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def load_dock_configs(path=None):
    path = path or os.path.join(ROOT, "configs", "docks.json")
    with open(path, encoding="utf-8") as f:
        return json.load(f)["configs"]


def load_strategies(path=None):
    path = path or os.path.join(ROOT, "configs", "strategies.json")
    with open(path, encoding="utf-8") as f:
        return json.load(f)["strategies"]


def scenario_warmup(manifest):
    return float(manifest.get("warmup_min", WARMUP_MIN))


def load_strategy_config(path=None):
    path = path or os.path.join(ROOT, "configs", "strategies.json")
    with open(path, encoding="utf-8") as f:
        return json.load(f)
