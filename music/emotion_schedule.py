"""
emotion_schedule.py
-------------------
Maps an emotional trajectory in valence/arousal (VA) space onto per-bar
MuseMorphose control attributes (rhythmic intensity + polyphony, classes 0-7),
implementing an iso-principle "meet-then-calm" arc for a meditation session.

Pipeline role:
    start emotion (V,A) -> per-bar (rhym_cls, poly_cls) -> MuseMorphose generate.py

MuseMorphose exposes two ordinal bar-level attributes, each in [0..7]:
    - rhythmic intensity : fraction of beats carrying a note onset  (strong AROUSAL proxy)
    - polyphony          : avg notes per beat / harmonic fullness   (arousal + some valence)

Valence is NOT directly controllable in MuseMorphose. We still compute and return
the valence curve so it can (a) inform seed/key choice, and (b) later drive the image
side and a continuous-VA model from the SAME trajectory. See notes at the bottom.
"""

from dataclasses import dataclass
import math
import numpy as np

# Russell 4-quadrant reference points in [0,1]^2  (valence, arousal)
QUADRANTS = {
    "Q1": (0.85, 0.85),  # happy / excited   (high V, high A)
    "Q2": (0.15, 0.85),  # tense / anxious   (low  V, high A)
    "Q3": (0.15, 0.15),  # sad / depressed   (low  V, low  A)
    "Q4": (0.85, 0.0),  # calm / relaxed    (high V, low  A)  <- meditation target
}
CALM = QUADRANTS["Q4"]


def _progress(n_bars, hold_bars, tail_hold_bars = 0,shape="ease_out"):
    """p[i] in [0,1]: 0 = still at start emotion, 1 = fully arrived at target.
    The first `hold_bars` stay at 0 (iso-principle: sit with the starting feeling)."""
    p = np.zeros(n_bars, dtype=float)
    move = max(1, n_bars - hold_bars - tail_hold_bars)
    for i in range(n_bars):
        if i < hold_bars:
            continue
        if i >= n_bars - tail_hold_bars:
            p[i] = 1.0
            continue
        t = (i - hold_bars) / (move - 1) if move > 1 else 1.0
        if shape == "linear":
            p[i] = t
        elif shape == "ease_out":                 # decelerating approach = restful landing
            p[i] = math.sin(t * math.pi / 2)
        elif shape == "smoother":                 # slow-fast-slow (smootherstep)
            p[i] = t * t * t * (t * (t * 6 - 15) + 10)
        elif shape == "logistic":
            p[i] = 1.0 / (1.0 + math.exp(-8.0 * (t - 0.5)))
        else:
            raise ValueError(f"unknown shape {shape!r}")
    return p


def _cls(x, lo=0, hi=7):
    return int(round(min(hi, max(lo, x))))


@dataclass
class Schedule:
    valence: np.ndarray     # float [0,1] per bar  (metadata / image side)
    arousal: np.ndarray     # float [0,1] per bar
    rhym_cls: np.ndarray    # int 0..7 per bar     (MuseMorphose)
    poly_cls: np.ndarray    # int 0..7 per bar     (MuseMorphose)


def emotion_schedule(
    start,                  # (valence, arousal) in [0,1], or a quadrant name e.g. "Q2"
    n_bars,                 # MUST equal the #bars of the MuseMorphose reference piece
    hold_bars=None,         # bars to sit at the start emotion (default ~20% of n_bars)
    tail_hold_bars=0,        # bars to sit at the target emotion (default 0)
    shape="ease_out",
    target=CALM,
    rhym_floor=0, rhym_ceil=7,   # keep a faint pulse at the calm end (0 = total stillness)
    poly_floor=0, poly_ceil=6,   # chords may stay a touch fuller than rhythm is busy
):
    if isinstance(start, str):
        start = QUADRANTS[start]
    sv, sa = start
    tv, ta = target
    if hold_bars is None:
        hold_bars = max(1, round(0.20 * n_bars))

    p = _progress(n_bars, hold_bars, tail_hold_bars, shape)
    valence = sv + (tv - sv) * p
    arousal = sa + (ta - sa) * p

    rhym = np.array([_cls(rhym_floor + a * (rhym_ceil - rhym_floor)) for a in arousal])
    poly = np.array([_cls(poly_floor + a * (poly_ceil - poly_floor)) for a in arousal])
    return Schedule(valence, arousal, rhym, poly)


def to_musemorphose_attrs(sched: Schedule):
    return sched.rhym_cls.tolist(), sched.poly_cls.tolist()


if __name__ == "__main__":
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    N = 48                       # ~3 min at ~4 s/bar; set to your reference piece's bar count
    s = emotion_schedule(start="Q2", n_bars=N, shape="ease_out")

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 4.4))

    bars = np.arange(N)
    ax1.step(bars, s.rhym_cls, where="mid", label="rhythmic intensity", lw=2)
    ax1.step(bars, s.poly_cls, where="mid", label="polyphony", lw=2)
    ax1.set_xlabel("bar"); ax1.set_ylabel("MuseMorphose class (0-7)")
    ax1.set_ylim(-0.4, 7.4); ax1.set_title("Per-bar attribute descent (Q2 -> Q4)")
    ax1.legend(); ax1.grid(alpha=0.3)

    for name, (v, a) in QUADRANTS.items():
        ax2.scatter(v, a, s=40); ax2.annotate(name, (v, a), textcoords="offset points", xytext=(6, 4))
    ax2.plot(s.valence, s.arousal, "-o", ms=3, lw=1.5)
    ax2.set_xlim(0, 1); ax2.set_ylim(0, 1)
    ax2.set_xlabel("valence"); ax2.set_ylabel("arousal")
    ax2.set_title("Trajectory in VA space (iso-principle: hold, then ease)")
    ax2.grid(alpha=0.3)

    plt.tight_layout()
    plt.savefig("schedule_preview.png", dpi=130)
    print("bars:", N, "| hold:", max(1, round(0.2 * N)))
    print("rhym:", s.rhym_cls.tolist())
    print("poly:", s.poly_cls.tolist())