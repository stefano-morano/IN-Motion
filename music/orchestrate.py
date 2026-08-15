"""
orchestrate.py
--------------
Automatic instrumentation for the meditation pipeline. Splits the single-track
piano MIDI from MuseMorphose into musical ROLES (bass / harmony / melody),
optionally THINS the calm tail so the ending dissolves, and assigns each role an
instrument from the start emotion's palette. Renders to STEREO audio with a
deep reverb tail + fade-out.
"""
import pretty_midi

GM = {
    "grand_piano": 0, "rhodes": 4, "ep2": 5, "harpsichord": 6,
    "celesta": 8, "music_box": 10, "vibraphone": 11, "marimba": 12,
    "organ": 19, "nylon_guitar": 24, "acoustic_bass": 32, "cello": 42,
    "contrabass": 43, "pizzicato": 45, "harp": 46, "strings": 48,
    "warm_strings": 49, "synth_strings": 50, "choir": 52, "flute": 73,
    "pad_newage": 88, "pad_warm": 89,
}

DEFINED_PALETTES = {
    "Q1": {"bass": "acoustic_bass", "harmony": "pad_newage", "melody": "harp"},
    "Q2": {"bass": "cello",         "harmony": "pad_newage",       "melody": "harp"},
    "Q3": {"bass": "cello",         "harmony": "pad_newage", "melody": "harp"},
    "Q4": {"bass": "pad_warm",      "harmony": "pad_newage",   "melody": "harp"},
}
AMBIENT_PALETTES = {
    "Q1": {"bass": "pad_warm", "harmony": "pad_newage",   "melody": "celesta"},
    "Q2": {"bass": "pad_warm", "harmony": "synth_strings", "melody": "rhodes"},
    "Q3": {"bass": "pad_warm", "harmony": "warm_strings",  "melody": "grand_piano"},
    "Q4": {"bass": "pad_warm", "harmony": "pad_newage",    "melody": "harp"},
}
SOFTEN  = {"Q1": 0.40, "Q2": 0.40, "Q3": 0.40, "Q4": 0.48}
SUSTAIN = {"bass": 2.2, "harmony": 2.0, "melody": 1.25}


def split_voices(pm, group_window=0.05):
    notes = sorted((n for inst in pm.instruments for n in inst.notes),
                   key=lambda n: (n.start, n.pitch))
    bass, harmony, melody = [], [], []
    i, N = 0, len(notes)
    while i < N:
        t0 = notes[i].start
        j = i
        while j < N and notes[j].start - t0 <= group_window:
            j += 1
        group = sorted(notes[i:j], key=lambda n: n.pitch)
        if len(group) == 1:
            melody.append(group[0])
        elif len(group) == 2:
            bass.append(group[0]); melody.append(group[1])
        else:
            bass.append(group[0]); melody.append(group[-1])
            harmony.extend(group[1:-1])
        i = j
    return bass, harmony, melody


def _thin_ramp(notes, t0, t1, keep_start, keep_end):
    """Keep notes with probability ramping keep_start->keep_end across [t0,t1].
    Thinned EVENLY via an accumulator (deterministic, no clumps). Notes before
    t0 are untouched."""
    if t1 <= t0:
        return list(notes)
    kept, acc = [], 0.0
    for n in sorted(notes, key=lambda n: n.start):
        if n.start < t0:
            kept.append(n); continue
        prog = min(1.0, (n.start - t0) / (t1 - t0))
        keep_p = keep_start + (keep_end - keep_start) * prog
        acc += keep_p
        if acc >= 1.0:
            kept.append(n); acc -= 1.0
    return kept


def thin_tail(layers, tail_frac=0.55, keep_end=0.15, harmony_keep_start=0.5):
    """Dissolve the calm tail: ramp harmony out to zero, thin melody/bass,
    keep bass a touch denser as a low ground. Guarantees a sparse ending
    regardless of how busy the reference/generation was."""
    all_notes = [n for L in layers.values() for n in L]
    if not all_notes:
        return layers
    end = max(n.end for n in all_notes)
    t0  = end * (1.0 - tail_frac)
    layers["harmony"] = _thin_ramp(layers["harmony"], t0, end, harmony_keep_start, 0.0)
    layers["melody"]  = _thin_ramp(layers["melody"],  t0, end, 1.0, keep_end)
    layers["bass"]    = _thin_ramp(layers["bass"],    t0, end, 1.0, max(keep_end, 0.35))
    return layers


def _soften(notes, factor):
    for n in notes:
        n.velocity = max(1, min(127, int(round(n.velocity * factor))))
    return notes


def _sustain(notes, factor):
    for n in notes:
        n.end = n.start + (n.end - n.start) * factor
    return notes


def orchestrate(in_path, emotion, out_path, mode="predefinedt",
                thin=True, tail_frac=0.55, tail_keep_end=0.15):
    palettes = AMBIENT_PALETTES if mode == "ambient" else DEFINED_PALETTES
    pm = pretty_midi.PrettyMIDI(in_path)
    bass, harmony, melody = split_voices(pm)
    layers = {"bass": bass, "harmony": harmony, "melody": melody}
    pal = palettes[emotion]
    soft = SOFTEN.get(emotion, 0.7)

    if thin:                                        # dissolve the tail FIRST
        layers = thin_tail(layers, tail_frac=tail_frac, keep_end=tail_keep_end)

    _soften(layers["bass"], soft)
    _soften(layers["harmony"], soft)
    _soften(layers["melody"], min(1.0, soft + 0.8))
    if mode == "ambient":
        for role in layers:
            _sustain(layers[role], SUSTAIN[role])

    pm.instruments = []
    for role in ("bass", "harmony", "melody"):
        notes = layers[role]
        if not notes:
            continue
        inst = pretty_midi.Instrument(program=GM[pal[role]], name=f"{emotion}:{role}")
        inst.notes = sorted(notes, key=lambda n: n.start)
        pm.instruments.append(inst)
    pm.write(out_path)
    return {r: len(n) for r, n in layers.items()}


def render(midi_path, wav_path, soundfont, sample_rate=44100,
           room_size=0.9, wet_level=0.55, damping=0.3, lowpass_hz=6500,
           tail_seconds=4.0, fade_seconds=3.0):
    """Render to STEREO audio with deep reverb tail + fade-out."""
    import numpy as np
    from scipy.io import wavfile
    pm = pretty_midi.PrettyMIDI(midi_path)
    audio = pm.fluidsynth(fs=sample_rate, sf2_path=soundfont).astype("float32")

    pad = np.zeros(int(tail_seconds * sample_rate), dtype="float32")
    audio = np.concatenate([audio, pad])

    try:
        from pedalboard import Pedalboard, Reverb, LowpassFilter, Gain
        board = Pedalboard([
            Reverb(room_size=room_size, damping=damping,
                   wet_level=wet_level, dry_level=1.0 - wet_level, width=1.0),
            LowpassFilter(cutoff_frequency_hz=lowpass_hz),
            Gain(gain_db=2.0),
        ])
        audio = board(audio, sample_rate)
    except ImportError:
        print("[render] pedalboard not installed; writing dry mono audio")
        audio = np.stack([audio, audio])

    if audio.ndim == 1:
        audio = np.stack([audio, audio], axis=0)
    audio = audio.T if audio.shape[0] == 2 else audio     # (N, 2)

    fade_len = min(int(fade_seconds * sample_rate), len(audio))
    env = np.ones(len(audio), dtype="float32")
    env[-fade_len:] = np.linspace(1.0, 0.0, fade_len) ** 2
    audio = audio * env[:, None]

    audio = audio / (np.max(np.abs(audio)) + 1e-9)
    wavfile.write(wav_path, sample_rate, (audio * 0.9 * 32767).astype("int16"))
    return wav_path


if __name__ == "__main__":
    import sys
    in_path, emotion, out_path = sys.argv[1], sys.argv[2], sys.argv[3]
    mode = sys.argv[4] if len(sys.argv) > 4 else "ambient"
    counts = orchestrate(in_path, emotion, out_path, mode=mode)
    print(f"[orchestrate/{mode}] {emotion}: {counts} -> {out_path}")