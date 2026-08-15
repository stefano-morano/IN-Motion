#!/usr/bin/env python3
"""
session.py -- the music engine. Two entry points, one pipeline.

    python3 session.py Q2            # render ONE session -> sessions/
    python3 session.py library       # build the pre-rendered library
    python3 session.py library 6 Q2 Q3   # 6 variations, only Q2 and Q3

run(emotion) is importable and side-effect-free (the live app can call it).
build_library() reuses run() so the pipeline is defined once.

Every path is anchored to THIS file's folder, so it works regardless of the
directory you launch from.
"""
import sys, os, glob, shutil, subprocess, time

# ---- paths: anchored to this file, not the working directory ---------------
HERE        = os.path.dirname(os.path.abspath(__file__))
CONFIG      = os.path.join(HERE, "config", "default.yaml")
CKPT        = os.path.join(HERE, "musemorphose_pretrained_weights.pt")
SOUNDFONT   = os.path.join(HERE, "FluidR3_GM.sf2")
GENERATE    = os.path.join(HERE, "generate.py")
OUT_ROOT    = os.path.join(HERE, "sessions")
# the library lives on the VISUALS side, ready for the app to play:
LIBRARY_OUT = os.path.join(HERE, "..", "visuals", "musica_libreria")
N_PIECES    = 1
N_SAMPLES   = 1
# ----------------------------------------------------------------------------

from orchestrate import orchestrate, render


def newest_generated_midi(out_dir):
    """The generation (not the _orig reference) written most recently."""
    mids = [m for m in glob.glob(os.path.join(out_dir, "*.mid"))
            if "_orig" not in os.path.basename(m)]
    if not mids:
        raise FileNotFoundError(f"no generated .mid found in {out_dir}")
    return max(mids, key=os.path.getmtime)


def run(emotion):
    """Generate + orchestrate + render ONE session. Returns the .wav path."""
    stamp   = time.strftime("%Y%m%d_%H%M%S")
    out_dir = os.path.join(OUT_ROOT, f"{emotion}_{stamp}")
    os.makedirs(out_dir, exist_ok=True)

    print(f"[1/3] generating {emotion} ...")
    subprocess.run(
        [sys.executable, GENERATE, CONFIG, CKPT, out_dir,
         str(N_PIECES), str(N_SAMPLES), emotion],
        check=True, cwd=HERE,              # generate.py's own relative paths resolve here
    )
    midi = newest_generated_midi(out_dir)
    print(f"      -> {midi}")

    print("[2/3] orchestrating ...")
    arranged = os.path.join(out_dir, f"arranged_{emotion}.mid")
    counts = orchestrate(midi, emotion, arranged)
    print(f"      voices: {counts}")

    print("[3/3] rendering wav ...")
    wav = os.path.join(out_dir, f"session_{emotion}.wav")
    render(arranged, wav, soundfont=SOUNDFONT)
    print(f"[done] {wav}")
    return wav


def build_library(variations=4, emotions=("Q1", "Q2", "Q3", "Q4"), dest=LIBRARY_OUT):
    """Batch: N variations per emotion into the library the app plays from.
    Offline, run once. Reuses run() so the pipeline is defined in one place."""
    for emo in emotions:
        folder = os.path.join(dest, emo)
        os.makedirs(folder, exist_ok=True)
        for i in range(variations):
            print(f"\n=== [{emo}] variation {i + 1}/{variations} ===")
            wav = run(emo)
            shutil.move(wav, os.path.join(folder, f"{emo}_{i:02d}.wav"))
    print(f"\n[library ready] {dest}/")


if __name__ == "__main__":
    args = sys.argv[1:]
    if args and args[0] == "library":
        n = int(args[1]) if len(args) > 1 and args[1].isdigit() else 4
        emos = [a for a in args if a.startswith("Q")] or ("Q1", "Q2", "Q3", "Q4")
        build_library(n, emos)
    else:
        emotion = args[0] if args else "Q2"
        if emotion not in ("Q1", "Q2", "Q3", "Q4"):
            sys.exit(f"emotion must be Q1..Q4, got {emotion!r}")
        run(emotion)