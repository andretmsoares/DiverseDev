"""Gerador de pedidos e eventos sinteticos (apenas biblioteca padrao)."""
import math
import random
import zlib

from mps.models import SIZES, VIP_THRESHOLD

W_SLA, W_DIST, W_VALUE, W_REP = 0.40, 0.20, 0.25, 0.15
WIN_MIN, WIN_MAX = 30.0, 240.0

# Valor mediano (BRL) por tamanho e dispersao log-normal
VALUE_MEDIAN = {"P": 60.0, "M": 180.0, "G": 700.0}
VALUE_SIGMA = 0.8
VALUE_LO, VALUE_HI = 10.0, 1500.0   # faixa mapeada para componente 0-100
DIST_LO, DIST_HI = 10.0, 1500.0
DIST_SIGMA = 0.7
LATENT_RHO = 0.5                    # correlacao com o fator latente "cliente premium"


def stable_seed(scenario_id, seed):
    """Seed independente de hash() de str (determinismo entre processos)."""
    return (zlib.crc32(scenario_id.encode("utf-8")) * 1000003 + int(seed) * 7919 + 12345) & 0xFFFFFFFF


def _clip(x, lo, hi):
    return lo if x < lo else hi if x > hi else x


def _phi(x):
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def profile_curve(profile_def, duration_min, shift_min=0.0):
    """Multiplicador por minuto (lista de len duration_min+1), media 1 antes do shift."""
    hourly = profile_def["hourly"]
    amp = profile_def.get("amplitude", 1.0)
    vals = [1.0 + amp * (h - 1.0) for h in hourly]
    n = len(vals)
    base_len = n * 60.0

    def at(t):
        t = (t - shift_min) % base_len
        x = t / 60.0 - 0.5          # centros de hora em 0.5, 1.5, ...
        i = int(math.floor(x))
        f = x - i
        a = vals[i % n]
        b = vals[(i + 1) % n]
        return a + (b - a) * f

    m = int(duration_min) + 1
    curve = [at(float(k)) for k in range(m)]
    mean_all = sum(at(k + 0.5) for k in range(int(base_len))) / base_len
    return [c / mean_all for c in curve]


def knots_curve(knots, duration_min):
    m = int(duration_min) + 1
    if not knots:
        return [1.0] * m
    out = []
    j = 0
    for k in range(m):
        t = float(k)
        while j + 1 < len(knots) and knots[j + 1][0] <= t:
            j += 1
        if t <= knots[0][0]:
            out.append(float(knots[0][1]))
        elif j + 1 >= len(knots):
            out.append(float(knots[-1][1]))
        else:
            t0, v0 = knots[j]
            t1, v1 = knots[j + 1]
            out.append(v0 + (v1 - v0) * (t - t0) / float(t1 - t0))
    return out


def rate_curves(sc):
    """Taxa (pedidos/min) por minuto, por regiao; media global == base_rate_per_h/60."""
    dur = sc["duration_min"]
    kn = knots_curve(sc.get("rate_knots"), dur)
    per_region = {}
    names = sorted(sc["regions"].keys())
    for name in names:
        r = sc["regions"][name]
        pc = profile_curve(sc["profile_def"], dur, r.get("shift_min", 0.0))
        per_region[name] = [r["share"] * pc[k] * kn[k] for k in range(len(pc))]
    total = [sum(per_region[n][k] for n in names) for k in range(int(dur) + 1)]
    mean = sum(total[:int(dur)]) / float(int(dur))
    scale = (sc["base_rate_per_h"] / 60.0) / mean
    for n in names:
        per_region[n] = [v * scale for v in per_region[n]]
    return names, per_region


def _interp(arr, t):
    i = int(t)
    if i >= len(arr) - 1:
        return arr[-1]
    f = t - i
    return arr[i] + (arr[i + 1] - arr[i]) * f


def mix_at(sc, t):
    for w in sc.get("mix_windows", []):
        if w["start_min"] <= t < w["end_min"]:
            return w["size_mix"]
    return sc["size_mix"]


def expected_size_mix(sc):
    """Mix esperado no dia (ponderado pela taxa)."""
    names, per = rate_curves(sc)
    dur = int(sc["duration_min"])
    acc = dict((s, 0.0) for s in SIZES)
    tot = 0.0
    for k in range(dur):
        lam = sum(per[n][k] for n in names)
        mx = mix_at(sc, k + 0.5)
        for s in SIZES:
            acc[s] += lam * mx[s]
        tot += lam
    return dict((s, acc[s] / tot) for s in SIZES)


def _pick_size(rng, mix):
    u = rng.random()
    acc = 0.0
    for s in SIZES:
        acc += mix[s]
        if u < acc:
            return s
    return SIZES[-1]


def _pick_tier(tiers, u):
    acc = 0.0
    for sla, p in tiers:
        acc += p
        if u < acc:
            return float(sla)
    return float(tiers[-1][0])


def _window(rng, sla, frac, sigma, lo=WIN_MIN, hi=WIN_MAX):
    mu = math.log(sla * frac)
    for _ in range(50):
        w = math.exp(rng.gauss(mu, sigma))
        if lo <= w <= hi:
            return w
    return _clip(math.exp(mu), lo, hi)


def compute_score(window, distance, value, rep, win_lo=WIN_MIN, win_hi=WIN_MAX, sla_gamma=1.0):
    """Componentes normalizados 0-100 e score ponderado (40/20/25/15)."""
    c_sla = 100.0 * ((win_hi - window) / (win_hi - win_lo)) ** sla_gamma
    c_dist = 100.0 * _clip(math.log(distance / DIST_LO) / math.log(DIST_HI / DIST_LO), 0.0, 1.0)
    c_val = 100.0 * _clip(math.log(value / VALUE_LO) / math.log(VALUE_HI / VALUE_LO), 0.0, 1.0)
    c_rep = _clip(rep, 0.0, 100.0)
    s = W_SLA * c_sla + W_DIST * c_dist + W_VALUE * c_val + W_REP * c_rep
    return _clip(s, 0.0, 100.0)


def generate_orders(sc, seed):
    """Lista de dicts de pedidos ordenados por arrival_min."""
    rng = random.Random(stable_seed(sc["scenario_id"], seed))
    names, per = rate_curves(sc)
    dur = float(sc["duration_min"])
    n_min = int(dur) + 1
    tot = [sum(per[n][k] for n in names) for k in range(n_min)]
    lam_max = max(tot) * 1.001
    orders = []
    t = 0.0
    while True:
        t += rng.expovariate(lam_max)
        if t >= dur:
            break
        if rng.random() * lam_max > _interp(tot, t):
            continue
        # regiao proporcional a taxa local
        k = min(int(t), n_min - 1)
        u = rng.random() * tot[k]
        acc = 0.0
        region = names[-1]
        for n in names:
            acc += per[n][k]
            if u < acc:
                region = n
                break
        orders.append(_make_order(rng, sc, region, t, len(orders) + 1))
    return orders


def _make_order(rng, sc, region, t, idx):
    r = sc["regions"][region]
    size = _pick_size(rng, mix_at(sc, t))
    z = rng.gauss(0.0, 1.0)                      # fator latente "cliente premium"
    eps = rng.gauss(0.0, 1.0)
    u_sla = _phi(-(LATENT_RHO * z + math.sqrt(1 - LATENT_RHO ** 2) * eps))  # premium -> SLA mais apertado
    sla = _pick_tier(r["sla_tiers"], u_sla)
    wlo, whi = sc.get("win_lo", WIN_MIN), sc.get("win_hi", WIN_MAX)
    window = _window(rng, sla, r["window_median_frac"], r["window_sigma"], wlo, whi)
    distance = r["distance_median_km"] * math.exp(rng.gauss(0.0, DIST_SIGMA) + 0.3 * z)
    value = (VALUE_MEDIAN[size] * r["value_scale"]
             * math.exp(rng.gauss(0.0, VALUE_SIGMA) + 0.35 * z))
    a, b = r["rep_beta"]
    rep = 100.0 * rng.betavariate(a, b)
    score = compute_score(window, distance, value, rep, wlo, whi, sc.get("sla_gamma", 1.0))
    arr = round(t, 3)
    win = round(window, 3)
    return {
        "order_id": "O%06d" % idx,
        "arrival_min": arr,
        "dispatch_window_min": win,
        "deadline_min": round(arr + win, 3),
        "priority_score": round(score, 2),
        "size_category": size,
        "region": region,
        "distance_km": round(distance, 1),
        "sla_min": int(sla),
        "value_brl": round(value, 2),
        "seller_reputation": round(rep, 1),
    }


def generate_events(sc, orders, seed):
    """Eventos de update/cancel; tempo em [chegada, prazo]."""
    rng = random.Random(stable_seed(sc["scenario_id"], seed) ^ 0x5EED5EED)
    up_p, ca_p = sc["update_prob"], sc["cancel_prob"]
    dl_share = sc["update_deadline_share"]
    evs = []
    for o in orders:
        u = rng.random()
        if u < ca_p:
            tm = o["arrival_min"] + rng.uniform(0.05, 1.0) * o["dispatch_window_min"]
            evs.append((min(round(tm, 3), o["deadline_min"]), o["order_id"], "cancel", None, None))
        elif u < ca_p + up_p:
            frac = rng.uniform(0.05, 0.9)
            tm = round(o["arrival_min"] + frac * o["dispatch_window_min"], 3)
            new_score = new_dl = None
            change_dl = rng.random() < dl_share
            change_sc = (not change_dl) or rng.random() < 0.4
            if change_sc:
                new_score = round(_clip(o["priority_score"] + rng.gauss(0.0, 15.0), 0.0, 100.0), 2)
            if change_dl:
                delta = rng.uniform(-0.4, 0.5) * o["dispatch_window_min"]
                new_dl = max(o["deadline_min"] + delta, tm + 5.0)
                if sc.get("win_hi", WIN_MAX) < WIN_MAX:
                    # perfil apertado: prazo novo a [lo, hi] min do instante do evento
                    new_dl = tm + _clip(new_dl - tm, sc["win_lo"], sc["win_hi"])
                new_dl = round(new_dl, 3)
            evs.append((tm, o["order_id"], "update", new_score, new_dl))
    evs.sort(key=lambda e: (e[0], e[1]))
    return [("E%06d" % (i + 1),) + e for i, e in enumerate(evs)]


def summarize(sc, orders, events):
    n = len(orders)
    dur_h = sc["duration_min"] / 60.0
    mix = dict((s, 0) for s in SIZES)
    reg = {}
    vip = 0
    for o in orders:
        mix[o["size_category"]] += 1
        reg[o["region"]] = reg.get(o["region"], 0) + 1
        if o["priority_score"] >= VIP_THRESHOLD:
            vip += 1
    return {
        "n_orders": n,
        "mean_rate_per_h": round(n / dur_h, 2),
        "pct_vip": round(100.0 * vip / n, 2) if n else 0.0,
        "size_mix": dict((s, round(mix[s] / float(n), 4) if n else 0.0) for s in SIZES),
        "region_counts": dict(sorted(reg.items())),
        "n_updates": sum(1 for e in events if e[3] == "update"),
        "n_cancels": sum(1 for e in events if e[3] == "cancel"),
    }
