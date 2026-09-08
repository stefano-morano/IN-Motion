/**
 * emotions.js — arousal/valence analysis from MediaPipe face blend shapes.
 *
 * Samples the 52 FaceLandmarker blend shapes about once per second and computes:
 *   valence : [-1 negative … +1 positive] — smile vs frown
 *   arousal : [0 calm … 1 activated/tense] — wide eyes, jaw
 *
 * Produces a report() at the end of the experience used as extra context
 * for Claude's complex-emotion analysis.
 */

export class EmotionAnalyzer {
    constructor() {
        this._samples = [];
        this._lastSampleAt = 0;
        this._active = false;
    }

    start() {
        this._samples = [];
        this._lastSampleAt = 0;
        this._active = true;
    }

    stop() { this._active = false; }

    /** Time series (1 sample/s) for summary charts. */
    series() {
        return {
            valenza: this._samples.map(c => c.valenza),
            arousal: this._samples.map(c => c.arousal),
        };
    }

    /**
     * Call every frame with result.faceBlendshapes[0].categories
     * (array of {categoryName, score} from MediaPipe FaceLandmarker).
     * Records at most one sample per second.
     */
    update(blendshapes) {
        if (!this._active || !blendshapes) return;
        const now = performance.now();
        if (now - this._lastSampleAt < 1000) return;
        this._lastSampleAt = now;

        const m = {};
        for (const b of blendshapes) m[b.categoryName] = b.score;
        const get = (k) => m[k] ?? 0;

        const smile    = (get('mouthSmileLeft') + get('mouthSmileRight')) / 2;
        const duchenne = (get('cheekSquintLeft') + get('cheekSquintRight')) / 2;
        const frown    = (get('mouthFrownLeft')  + get('mouthFrownRight'))  / 2;
        const browDown = (get('browDownLeft')     + get('browDownRight'))    / 2;
        const browUp   =  get('browInnerUp');
        const eyesWide = (get('eyeWideLeft')      + get('eyeWideRight'))     / 2;
        const squint   = (get('eyeSquintLeft')    + get('eyeSquintRight'))   / 2;
        const jaw      =  get('jawOpen');
        const nose     = (get('noseSneerLeft')    + get('noseSneerRight'))   / 2;

        const valenza = Math.max(-1, Math.min(1,
            (smile * 1.2 + duchenne * 0.8) -
            (frown * 1.0 + browDown * 0.7 + nose * 0.5)
        ));
        const arousal = Math.min(1,
            eyesWide * 0.35 + browUp * 0.25 + jaw * 0.20 +
            squint  * 0.15 + browDown * 0.10
        );

        this._samples.push({ valenza, arousal, sorriso: smile, duchenne, brow_down: browDown, mascella: jaw });
    }

    /**
     * Session summary. Null if there is not enough data.
     * Field names stay Italian for backend / Firestore compatibility.
     */
    report() {
        const n = this._samples.length;
        if (n < 3) return null;

        const avg = (f) => this._samples.reduce((s, c) => s + c[f], 0) / n;
        const max = (f) => Math.max(...this._samples.map(c => c[f]));

        const mid = Math.floor(n / 2);
        const vStart = this._samples.slice(0, mid).reduce((s, c) => s + c.valenza, 0) / mid;
        const vEnd   = this._samples.slice(mid).reduce((s, c) => s + c.valenza, 0) / (n - mid);
        let arc = 'stabile';
        if (vEnd - vStart >  0.15) arc = 'miglioramento';
        if (vStart - vEnd >  0.15) arc = 'peggioramento';

        const fmt = (v) => parseFloat(v.toFixed(3));
        return {
            valenza_media:   fmt(avg('valenza')),
            arousal_medio:   fmt(avg('arousal')),
            sorriso_genuino: fmt(avg('duchenne')),
            tensione_brow:   fmt(avg('brow_down')),
            mascella_media:  fmt(avg('mascella')),
            picco_arousal:   fmt(max('arousal')),
            arco_emotivo:    arc,
            n_campioni:      n,
        };
    }
}
