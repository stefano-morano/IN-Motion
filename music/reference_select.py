import json, random

# Russell quadrants -> reference criteria + arc parameters
EMOTION_PROFILES = {
    "Q1": {  # happy / excited
        "reference": {"tonal": "bright", "tempo": None},
        "schedule":  {"start": "Q1", "target": (0.85, 0.0),
                      "shape": "ease_out", "tail_hold_bars": 16},
    },
    "Q2": {  # tense / anxious
        "reference": {"tonal": "dark", "tempo": None},   
        "schedule":  {"start": "Q2", "target": (0.85, 0.0),
                      "shape": "ease_out", "tail_hold_bars": 16},
    },
    "Q3": {  # sad / depressed
        "reference": {"tonal": "dark", "tempo": None},   
        "schedule":  {"start": "Q3", "target": (0.85, 0.05),
                      "shape": "ease_out", "hold_bars": 6, "tail_hold_bars": 16},
    },
    "Q4": {  # calm / relaxed (already near target)
        "reference": {"tonal": "bright", "tempo": None},
        "schedule":  {"start": "Q4", "target": (0.85, 0.05),
                      "shape": "ease_out", "tail_hold_bars": 20},
    },
}


def load_catalog(path="reference_catalog.json"):
    with open(path) as f:
        return json.load(f)


def schedule_kwargs(emotion):
    return dict(EMOTION_PROFILES[emotion]["schedule"])


def pick_references(emotion, catalog, n=1, min_bars=40,
                    top_frac=0.20, seed=None, deterministic=False):
    prof = EMOTION_PROFILES[emotion]["reference"]
    tonal, tempo = prof["tonal"], prof.get("tempo")

    base = [r for r in catalog if r.get("minor_ratio") is not None]
    cands = [r for r in base if (r.get("n_bars") or 0) >= min_bars]
    if not cands:
        print(f"[warn] no pieces with >= {min_bars} bars; dropping length filter")
        cands = base
    if tempo:
        lo, hi = tempo
        toned = [r for r in cands if r.get("tempo") is not None and lo <= r["tempo"] <= hi]
        cands = toned or cands            # tempo is a soft preference

    if tonal == "neutral":
        cands.sort(key=lambda r: abs(r["minor_ratio"] - 0.5))
    else:
        cands.sort(key=lambda r: r["minor_ratio"], reverse=(tonal == "dark"))

    pool = cands[:max(1, int(len(cands) * top_frac))]
    if deterministic:
        chosen = pool[:n]
    else:
        chosen = random.Random(seed).sample(pool, min(n, len(pool)))
    return [r["idx"] for r in chosen]


if __name__ == "__main__":
    import sys
    cat = load_catalog(sys.argv[1] if len(sys.argv) > 1 else "reference_catalog.json")
    for emo in ("Q1", "Q2", "Q3", "Q4"):
        idxs = pick_references(emo, cat, n=2, min_bars=40, deterministic=True)
        print(f"{emo}: reference idxs -> {idxs}")