/**
 * emozioni.js — analisi arousal/valence da MediaPipe face blend shapes.
 *
 * Campiona le 52 blend shapes di FaceLandmarker ogni ~1s e calcola:
 *   valenza  : [-1 negativa … +1 positiva]  — sorriso vs cipiglio
 *   arousal  : [0 calmo … 1 attivato/teso]  — occhi sbarrati, mascella
 *
 * Produce un report() al termine dell'esperienza usato come contesto
 * aggiuntivo per l'analisi Claude di emozioni complesse.
 */

export class AnalizzatoreEmozioni {
    constructor() {
        this._campioni = [];
        this._tUltimoRec = 0;
        this._attivo = false;
    }

    inizia() {
        this._campioni = [];
        this._tUltimoRec = 0;
        this._attivo = true;
    }

    ferma() { this._attivo = false; }

    /**
     * Chiama ogni frame con result.faceBlendshapes[0].categories
     * (array di {categoryName, score} da MediaPipe FaceLandmarker).
     * Registra max 1 campione al secondo.
     */
    aggiorna(blendshapes) {
        if (!this._attivo || !blendshapes) return;
        const ora = performance.now();
        if (ora - this._tUltimoRec < 1000) return;   // 1 campione/s
        this._tUltimoRec = ora;

        // Estrai score per nome (robusto rispetto all'ordine)
        const m = {};
        for (const b of blendshapes) m[b.categoryName] = b.score;

        const get = (k) => m[k] ?? 0;

        // --- indicatori ---
        const sorriso   = (get('mouthSmileLeft') + get('mouthSmileRight')) / 2;
        const duchenne  = (get('cheekSquintLeft') + get('cheekSquintRight')) / 2; // Duchenne
        const cipiglio  = (get('mouthFrownLeft')  + get('mouthFrownRight'))  / 2;
        const brow_down = (get('browDownLeft')     + get('browDownRight'))    / 2;
        const brow_up   =  get('browInnerUp');
        const occhi_w   = (get('eyeWideLeft')      + get('eyeWideRight'))     / 2;
        const squint    = (get('eyeSquintLeft')    + get('eyeSquintRight'))   / 2;
        const mascella  =  get('jawOpen');
        const naso      = (get('noseSneerLeft')    + get('noseSneerRight'))   / 2;

        // --- calcolo dimensioni ---
        const valenza = Math.max(-1, Math.min(1,
            (sorriso * 1.2 + duchenne * 0.8) -
            (cipiglio * 1.0 + brow_down * 0.7 + naso * 0.5)
        ));
        const arousal = Math.min(1,
            occhi_w * 0.35 + brow_up * 0.25 + mascella * 0.20 +
            squint  * 0.15 + brow_down * 0.10
        );

        this._campioni.push({ valenza, arousal, sorriso, duchenne, brow_down, mascella });
    }

    /**
     * Restituisce il riassunto della sessione.
     * Null se non ci sono dati sufficienti.
     */
    report() {
        const n = this._campioni.length;
        if (n < 3) return null;

        const avg = (f) => this._campioni.reduce((s, c) => s + c[f], 0) / n;
        const max = (f) => Math.max(...this._campioni.map(c => c[f]));

        // Arco emotivo: confronta prima e seconda metà della sessione
        const meta = Math.floor(n / 2);
        const vInizio = this._campioni.slice(0, meta).reduce((s, c) => s + c.valenza, 0) / meta;
        const vFine   = this._campioni.slice(meta).reduce((s, c) => s + c.valenza, 0) / (n - meta);
        let arco = 'stabile';
        if (vFine - vInizio >  0.15) arco = 'miglioramento';
        if (vInizio - vFine >  0.15) arco = 'peggioramento';

        const fmt = (v) => parseFloat(v.toFixed(3));
        return {
            valenza_media:   fmt(avg('valenza')),
            arousal_medio:   fmt(avg('arousal')),
            sorriso_genuino: fmt(avg('duchenne')),
            tensione_brow:   fmt(avg('brow_down')),
            mascella_media:  fmt(avg('mascella')),
            picco_arousal:   fmt(max('arousal')),
            arco_emotivo:    arco,
            n_campioni:      n,
        };
    }
}
