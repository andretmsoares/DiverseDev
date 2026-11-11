"""Layout de docas e filas a partir de uma entrada de configs/docks.json.

Grupo de docas: `name`, `sizes`, `count`, `speed` (padrao 1.0; tempo de servico =
PACK_MIN/speed). Fila: uma estrategia por fila.
 - borrow 'one_way'/'none': cada grupo usa a fila de nome `queue` (padrao = nome do
   grupo); grupos com o mesmo `queue` compartilham a fila (ex.: generic_speed_15).
 - borrow 'best_eligible': uma fila por TAMANHO de pedido (P, M, G); nenhuma doca
   tem fila propria.
"""
from mps.models import SIZES


def layout(cfg):
    borrow = cfg.get("borrow", "none")
    groups = []
    for g in cfg["classes"]:
        groups.append({"name": g["name"], "sizes": tuple(g["sizes"]), "count": int(g["count"]),
                       "speed": float(g.get("speed", 1.0)), "queue_name": g.get("queue", g["name"]),
                       "alias": g.get("alias")})
    queues = []
    if borrow == "best_eligible":
        accepted = set(s for g in groups for s in g["sizes"])
        for s in SIZES:
            if s in accepted:
                queues.append({"name": s, "sizes": (s,)})
    else:
        for g in groups:
            q = [x for x in queues if x["name"] == g["queue_name"]]
            if q:
                q[0]["sizes"] = tuple(sorted(set(q[0]["sizes"]) | set(g["sizes"]), key=SIZES.index))
            else:
                queues.append({"name": g["queue_name"], "sizes": g["sizes"]})
    qidx = dict((q["name"], i) for i, q in enumerate(queues))
    for g in groups:
        g["queue"] = None if borrow == "best_eligible" else qidx[g["queue_name"]]
    return {"borrow": borrow, "groups": groups, "queues": queues}


def names(cfg):
    """(nomes dos grupos de docas, nomes das filas)."""
    lay = layout(cfg)
    return [g["name"] for g in lay["groups"]], [q["name"] for q in lay["queues"]]
