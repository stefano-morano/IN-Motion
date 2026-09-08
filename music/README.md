# IN-Motion — Music Engine

The music half of **IN-Motion**, a guided meditation experience. Given the
user's start emotion, this engine generates a piano piece that *begins* in that
emotional state and *develops toward calm*, arranges it for a small ensemble,
and renders it to audio. The visual half (TouchDesigner particles) lives in the
sibling `visuals/` folder and plays the audio this engine produces.

Built on **MuseMorphose** (Wu & Yang, TASLP 2022) — a Transformer-VAE for
fine-grained piano style transfer. The model itself is **unmodified**;
everything emotional is a thin control layer around it (reference selection +
a per-bar attribute schedule + post-hoc orchestration). See the original work
and citation at the bottom.

## What it does

The start emotion is one of the four Russell valence/arousal quadrants:


Every session ends at **Q4 (calm)** — the *journey* is what differs:

* **Q1 / Q2** — a smooth arousal *descent* (busy → sparse), following the
  iso-principle: meet the user's energy first, then wind down.
* **Q3** — a gentle *settle* (a plain descent from already-low
  arousal has nowhere to go).
* **Q4** — *sustain* and deepen a calm that's already there.

The pipeline, per session:

1. **Select a reference** whose tonal colour matches the emotion (minor-leaning
   for low valence, brighter for high) from `reference_catalog.json`.
2. **Build an arousal schedule** — a per-bar `(rhythmic intensity, polyphony)`
   curve fed to MuseMorphose, which re-performs the reference at that density.
   Render tempo is locked to a fixed 75 BPM regardless of the reference's
   original tempo, so every session lands in the same calm tempo range.
3. **Orchestrate** — split the single piano track into bass / harmony / melody,
   assign a per-emotion instrument palette, and dissolve the calm tail.
4. **Render** to stereo `.wav` with a deep reverb tail and fade-out.

## Prerequisites

* Python >= 3.8
* Install Python dependencies:
  ```bash
  pip3 install -r requirements.txt
  ```
* **FluidSynth** (the synth used to render MIDI → audio) — a system binary, not
  a pip package. On macOS:
  ```bash
  brew install fluid-synth
  ```
* A GM **soundfont**. Download `FluidR3_GM.sf2` into this folder (it is not
  committed to git — too large):
  ```bash
  curl -L -o FluidR3_GM.sf2 "https://github.com/urish/cinto/raw/master/media/FluidR3%20GM.sf2"
  ```

## Setup

```bash
# 1) reference pieces (the material MuseMorphose morphs)
wget -O remi_dataset.tar.gz "https://zenodo.org/record/4782721/files/remi_dataset.tar.gz?download=1"
tar xzvf remi_dataset.tar.gz && rm remi_dataset.tar.gz
python3 attributes.py

# 2) pretrained MuseMorphose weights
wget -O musemorphose_pretrained_weights.pt "https://zenodo.org/record/5119525/files/musemorphose_pretrained_weights.pt?download=1"

# 3) reference catalog (already committed; regenerate only if the dataset changes)
python3 build_catalog.py ./remi_dataset ./pickles/test_pieces.pkl reference_catalog.json
```

`config/default.yaml` is tuned for this use case (`generate.max_bars: 25`,
`generate.dec_seqlen: 1280`, `device: cpu`) — adjust `device` to `cuda` if you
have a GPU.


## Usage

**One session** → `sessions/<emotion>_<timestamp>/session_<emotion>.wav`:

```bash
python3 session.py Q2
```

**Build the pre-rendered library** the visual app plays from. This writes N
variations per emotion into `../visuals/musica_libreria/`:

```bash
python3 session.py library          # 4 variations per quadrant
python3 session.py library 6 Q2 Q3  # 6 variations, only Q2 and Q3
```


## Files

| File | Role |
|---|---|
| `session.py` | the engine — `run(emotion)` for one piece, `build_library()` for the batch |
| `emotion_schedule.py` | maps an emotion's VA trajectory → per-bar attribute classes |
| `reference_select.py` | per-emotion profiles + catalog-based reference picker |
| `build_catalog.py` | audits the dataset: bar count, tempo, minor/major tonal colour |
| `orchestrate.py` | voice split, per-emotion palettes, tail dissolve, stereo render |
| `reference_catalog.json` | the audited reference pool (small; committed) |
| `generate.py` | MuseMorphose generation (emotion arg added; schedule injected) |
| `attributes.py`, `dataloader.py`, `model/`, `remi2midi.py`, `utils.py` | MuseMorphose internals |


## Credit & citation
```
@article{wu2023musemorphose,
    title={{MuseMorphose}: Full-Song and Fine-Grained Piano Music Style Transfer with One {Transformer VAE}},
    author={Shih-Lun Wu and Yi-Hsuan Yang},
    year={2023},
    journal={IEEE/ACM Transactions on Audio, Speech, and Language Processing},
}
```

Original repository & demo: <https://slseanwu.github.io/site-musemorphose/> ·
paper: <https://arxiv.org/abs/2105.04090>