/**
 * testo_canvas.js — campiona le posizioni di una scritta da Canvas 2D.
 *
 * Equivalente del blocco `testo_top → _campiona_scritta()` in td_face_points.py:
 * disegna il testo su un canvas offscreen, legge i pixel accesi e ne restituisce
 * le coordinate nel sistema di riferimento 3D della scena.
 */

const TESTO_LARGHEZZA = 1.9;
const TESTO_ALTEZZA   = 0.9;
const CAM_TX  = 0.0;
const CAM_TY  = 0.0;

// Canvas 800×300: spazio sufficiente per testo a 2 righe con font grande.
// 800×300=240K pixel × 11 testi ≈ 2.6M iterazioni (<<10M con 1280×720).
const CW = 800, CH = 300;
const _canvas = document.createElement('canvas');
_canvas.width  = CW;
_canvas.height = CH;
const _ctx = _canvas.getContext('2d', { willReadFrequently: true });

/** Trova il font più grande che fa stare le righe in larghezza CW-16. */
function _trovafont(righe) {
    let fs = 150;
    _ctx.font = `bold ${fs}px sans-serif`;
    while (fs > 10) {
        const maxW = Math.max(...righe.map(r => _ctx.measureText(r).width));
        if (maxW <= CW - 16) break;
        fs -= 2;
        _ctx.font = `bold ${fs}px sans-serif`;
    }
    return fs;
}

/** Spezza la frase in 2 righe bilanciate per parole. */
function _spezza(frase) {
    const p = frase.split(' ');
    const mid = Math.ceil(p.length / 2);
    return [p.slice(0, mid).join(' '), p.slice(mid).join(' ')];
}

/**
 * Restituisce un Float32Array[n*3] con le posizioni 3D dei pixel accesi
 * del testo, scalate per stare dentro TESTO_LARGHEZZA × TESTO_ALTEZZA.
 */
export function campionaTesto(frase, n, seme = 99) {
    _ctx.clearRect(0, 0, CW, CH);
    _ctx.fillStyle = '#000';
    _ctx.fillRect(0, 0, CW, CH);
    _ctx.fillStyle = '#fff';
    _ctx.textAlign = 'center';
    _ctx.textBaseline = 'middle';

    // Prima prova su riga singola; se il font scende sotto 55px → 2 righe
    let fontSize = _trovafont([frase]);
    if (fontSize < 55 && frase.includes(' ')) {
        const [r1, r2] = _spezza(frase);
        fontSize = _trovafont([r1, r2]);
        const lh = fontSize * 1.25;
        _ctx.fillText(r1, CW / 2, CH / 2 - lh / 2);
        _ctx.fillText(r2, CW / 2, CH / 2 + lh / 2);
    } else {
        _ctx.fillText(frase, CW / 2, CH / 2);
    }

    const img  = _ctx.getImageData(0, 0, CW, CH);
    const data = img.data;

    // Raccoglie pixel accesi con min/max inline
    const colonne = [];
    const righe   = [];
    let cMin = CW, cMax = 0, rMin = CH, rMax = 0;
    for (let y = 0; y < CH; y++) {
        for (let x = 0; x < CW; x++) {
            if (data[(y * CW + x) * 4] > 127) {
                colonne.push(x); righe.push(y);
                if (x < cMin) cMin = x; if (x > cMax) cMax = x;
                if (y < rMin) rMin = y; if (y > rMax) rMax = y;
            }
        }
    }
    if (colonne.length === 0) {
        console.warn('campionaTesto: nessun pixel per', frase);
        return null;
    }

    const scala = Math.min(
        TESTO_LARGHEZZA / Math.max(cMax - cMin, 1),
        TESTO_ALTEZZA   / Math.max(rMax - rMin, 1)
    );
    const cMed = (cMin + cMax) / 2;
    const rMed = (rMin + rMax) / 2;

    // RNG con seme fisso per riproducibilità
    let state = (seme ^ 0x9e3779b9) >>> 0 || 1;
    const rnd = () => {
        let t = state ^ (state << 11);
        state = (state ^ (state >>> 19)) ^ (t ^ (t >>> 8));
        return (state >>> 0) / 4294967296;
    };

    const pool = colonne.length;
    const pos  = new Float32Array(n * 3);
    for (let i = 0; i < n; i++) {
        const idx = Math.floor(rnd() * pool);
        // Y: canvas va giù, scena va su → segno invertito
        pos[i * 3]     = CAM_TX + (colonne[idx] - cMed) * scala;
        pos[i * 3 + 1] = CAM_TY - (righe[idx]   - rMed) * scala;
        pos[i * 3 + 2] = 0.0;
    }
    return pos;
}

