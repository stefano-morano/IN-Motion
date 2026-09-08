import { TEXT_WIDTH, TEXT_HEIGHT, CAM_TX, CAM_TY } from './scena.js';

/**
 * testo_canvas.js — sample text glyph positions from a Canvas 2D.
 *
 * Equivalent of the `testo_top → _campiona_scritta()` block in td_face_points.py:
 * draws text on an offscreen canvas, reads lit pixels, and returns their
 * coordinates in the scene's 3D reference frame.
 */

const CW = 800, CH = 300;
const _canvas = document.createElement('canvas');
_canvas.width  = CW;
_canvas.height = CH;
const _ctx = _canvas.getContext('2d', { willReadFrequently: true });

/** Find the largest font size that fits the lines within width CW-16. */
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

/** Split the phrase into 2 word-balanced lines. */
function _spezza(frase) {
    const p = frase.split(' ');
    const mid = Math.ceil(p.length / 2);
    return [p.slice(0, mid).join(' '), p.slice(mid).join(' ')];
}

/**
 * Returns a Float32Array[n*3] with 3D positions of lit text pixels,
 * scaled to fit inside TEXT_WIDTH × TEXT_HEIGHT.
 */
export function sampleText(frase, n, seme = 99) {
    _ctx.clearRect(0, 0, CW, CH);
    _ctx.fillStyle = '#000';
    _ctx.fillRect(0, 0, CW, CH);
    _ctx.fillStyle = '#fff';
    _ctx.textAlign = 'center';
    _ctx.textBaseline = 'middle';

    // Try a single line first; if font drops below 55px → 2 lines
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

    // Collect lit pixels with inline min/max
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
        console.warn('sampleText: no pixels for', frase);
        return null;
    }

    const scala = Math.min(
        TEXT_WIDTH / Math.max(cMax - cMin, 1),
        TEXT_HEIGHT   / Math.max(rMax - rMin, 1)
    );
    const cMed = (cMin + cMax) / 2;
    const rMed = (rMin + rMax) / 2;

    // Fixed-seed RNG for reproducibility
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
        // Y: canvas goes down, scene goes up → inverted sign
        pos[i * 3]     = CAM_TX + (colonne[idx] - cMed) * scala;
        pos[i * 3 + 1] = CAM_TY - (righe[idx]   - rMed) * scala;
        pos[i * 3 + 2] = 0.0;
    }
    return pos;
}
