"""
build_catalog.py
----------------
Audition the MuseMorphose reference pool. For each piece in a data split compute:
    - n_bars      : how long a session it can support (need >= your max_bars)
    - tempo       : sets duration AND is LOCKED at render (enforce_tempo)
    - minor_ratio : share of minor/diminished chords -> a VALENCE / tonal-color proxy

Writes a JSON catalog sorted brightest -> darkest. Row `idx` matches dset[idx] in
generate.py (same split, same sort order), so it drops into pieces=[idx] directly.

FIRST RUN IS A DISCOVERY RUN: it prints every chord-quality string it sees and how
each was classified. Eyeball that block; if a quality is miscategorised, edit the
MINOR_QUALITIES / MAJOR_QUALITIES sets below and re-run.
"""
import os, sys, json, pickle
from collections import Counter


def pickle_load(path):
    with open(path, 'rb') as f:
        return pickle.load(f)


# chorder emits ~7 qualities. Minor-family (darker) vs the rest (brighter/neutral).
MINOR_QUALITIES = {'m', 'min', 'minor', 'm7', 'min7', 'dim', 'o', 'dim7', 'm7b5', 'hdim7'}
MAJOR_QUALITIES = {'M', 'maj', 'major', 'M7', 'maj7', '7', 'dom7', 'sus2', 'sus4', '+', 'aug'}


def parse_quality(chord_value):
    """chord_value like 'C_m', 'A_M7', 'G_7', 'N_N'. Return quality string or None."""
    if chord_value is None:
        return None
    v = str(chord_value)
    if v in ('N_N', 'None', 'NC', ''):          # 'no chord' marker
        return None
    for sep in ('_', ':'):
        if sep in v:
            return v.split(sep)[-1]
    return None


def classify(quality, seen_major, seen_minor, seen_other):
    if quality is None:
        return None
    if quality in MINOR_QUALITIES:
        seen_minor[quality] += 1
        return 'minor'
    if quality in MAJOR_QUALITIES:
        seen_major[quality] += 1
        return 'major'
    seen_other[quality] += 1
    # fallback: a lone leading lowercase 'm' (not 'M') reads as minor
    return 'minor' if quality[:1] == 'm' else 'major'


def load_split_pieces(data_dir, split_path):
    """Mirror generate.py: sorted .pkl paths -> enumerate index == dset idx."""
    names = pickle_load(split_path)
    return sorted(os.path.join(data_dir, p) for p in names)


def first_tempo(events):
    for ev in events:
        if 'Tempo' in ev['name']:
            return ev.get('value')
    return None


def analyse(path, seen_major, seen_minor, seen_other):
    bar_pos, events = pickle_load(path)
    n_bars = sum(1 for ev in events if ev['name'] == 'Bar')
    n_major = n_minor = 0
    for ev in events:
        if 'Chord' in ev['name']:
            c = classify(parse_quality(ev.get('value')), seen_major, seen_minor, seen_other)
            if c == 'minor':
                n_minor += 1
            elif c == 'major':
                n_major += 1
    total = n_major + n_minor
    return {
        'n_bars': n_bars,
        'tempo': first_tempo(events),
        'n_chords': total,
        'minor_ratio': round(n_minor / total, 3) if total else None,
    }


if __name__ == "__main__":
    data_dir   = sys.argv[1] if len(sys.argv) > 1 else './remi_dataset'
    split_path = sys.argv[2] if len(sys.argv) > 2 else './pickles/test_pieces.pkl'
    out_path   = sys.argv[3] if len(sys.argv) > 3 else 'reference_catalog.json'

    paths = load_split_pieces(data_dir, split_path)
    seen_major, seen_minor, seen_other = Counter(), Counter(), Counter()
    rows = []
    for idx, path in enumerate(paths):
        info = analyse(path, seen_major, seen_minor, seen_other)
        info['idx'] = idx
        info['piece_id'] = os.path.basename(path).replace('.pkl', '')
        rows.append(info)
        if not idx % 50:
            print(f'[scan] {idx}/{len(paths)}')

    print('\n=== chord qualities seen (sanity-check the classifier) ===')
    print('MAJOR-classed:', dict(seen_major))
    print('MINOR-classed:', dict(seen_minor))
    if seen_other:
        print('UNRECOGNISED (guessed via fallback -- REVIEW):', dict(seen_other))

    rows.sort(key=lambda r: (r['minor_ratio'] is None, r['minor_ratio'] or 0))
    _coerce = lambda o: o.item() if hasattr(o, 'item') else str(o)
    json.dump(rows, open(out_path, 'w'), indent=2, default=_coerce)

    dark   = [r for r in rows if (r['minor_ratio'] or 0) >= 0.5 and (r['n_bars'] or 0) >= 40]
    bright = [r for r in rows if (r['minor_ratio'] or 0) <  0.2 and (r['n_bars'] or 0) >= 40]
    print(f'\n[done] {len(rows)} pieces -> {out_path}')
    print(f'[buckets @>=40 bars]  dark/minor: {len(dark)}   bright/major: {len(bright)}')
    print('  dark idxs  :', [r['idx'] for r in dark[:8]])
    print('  bright idxs:', [r['idx'] for r in bright[:8]])
