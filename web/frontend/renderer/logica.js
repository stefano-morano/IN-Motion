/**
 * logica.js — direct port of td_face_points.py to JavaScript.
 *
 * Each frame computes positions and colors for 13,664 particles.
 * No Three.js dependency: returns raw Float32Arrays that the
 * renderer can load into BufferGeometry without further conversion.
 */

import {
    SCALE, CAM_TX, CAM_TY,
    screenAspect, visibleRadius,
} from './scena.js';

// ------------------------------------------------------------------ constants
const TOTALE_PARTICELLE = 13664;
const ESPONENTE_DENSITA = 0.45;

const PALETTE_CALMA = {
    fondo: [0.020, 0.045, 0.115],
    luce:  [0.300, 0.460, 0.640],
};

// The blue above is not THE color of the piece: it is the color from BEFORE
// the piece knows who is in front of it. The tint Claude derives from the
// story does not wait for the mandala to appear — it enters as soon as it
// exists and grows phase by phase. How much has entered is told by
// tintaForza(), which drives the Python state machine via /tinta_forza.
// Aligned with visuals/td_face_points.py: if you change the numbers here,
// change them there too and in visuals/mandala.py.
const DURATA_TINTA = 12.0;
const INTENSITA_COLORE = 1.35;

// The background halo. It follows the personal tint too, so color is not
// stuck on the particles but in the air around them. In the shader the SHAPE
// of the halo and its COLOR are separate, like the two nodes inside TD.
const SFONDO_CALMA = [0.030, 0.042, 0.085];
const NEBBIA_LUMINOSITA = 0.35;
const SCINTILLIO = 0.16;
const SCINTILLIO_VELOCITA = 0.35;
const PROFONDITA_COLORE = 0.30;

const MANDALA_PETALO = 0.26;
const MANDALA_ARMONICA = 0.10;
const MANDALA_SFASAMENTO = true;
const MANDALA_CUPOLA = 0.16;
const MANDALA_SPESSORE = 0.035;
const MANDALA_ROTAZIONE = 0.06;
const MANDALA_NEBBIA = 0.3;
// Color gradient by emotion (aligned with visuals/mandala.py GRADIENTE)
const MANDALA_GRADIENTE = {
    Q1: { apertura: 46.0, verso: 1,  satFondo: 0.86, satLuce: 0.60 },
    Q2: { apertura: 42.0, verso: -1, satFondo: 0.92, satLuce: 0.68 },
    Q3: { apertura: 24.0, verso: -1, satFondo: 0.88, satLuce: 0.55 },
    Q4: { apertura: 14.0, verso: 1,  satFondo: 0.80, satLuce: 0.45 },
};
const MANDALA_EMOZIONE_DEFAULT = 'Q2';
// Visible radius matches half the frustum height (SCALE/2)

const POLVERE_AMPIEZZA = 0.68;
const POLVERE_PROFONDITA = 1.00;
const POLVERE_ARRETRAMENTO = 0.30;
const SEME_POLVERE = 20260827;

const DURATA_TRANSIZIONE = 4.0;
const RITARDO_MAX = 0.7;
const ESPANSIONE = 0.10;
const FRAZIONE_NEBBIA = 0.40;
const NEBBIA_RAGGIO = 0.035;
const FLUTTUAZIONE = 0.012;
const FLUTTUAZIONE_NEBBIA = 3.0;
const CORRENTE_AMPIEZZA = 0.035;
const CURRENT_SCALE = 1.4;
const CORRENTE_VELOCITA = 0.25;
const INERZIA_MIN = 0.04;
const INERZIA_MAX = 0.28;

// dissolution
const NASO = 4;
const RAGGIO_NASO = 0.38;
const FORZA_NASO = 3.00;
const VELOCITA_LIBERAZIONE = 0.25;
const SPINTA_Z = 0.30;
const ATTRITO_FUGA = 0.999;
const SOGLIA_MOVIMENTO = 0.20;

// ------------------------------------------------------------------ RNG (xorshift128)
class RNG {
    constructor(seed) {
        this.x = (seed ^ 0x9e3779b9) >>> 0 || 1;
        this.y = 362436069;
        this.z = 521288629;
        this.w = 88675123;
    }
    next() {
        let t = this.x ^ (this.x << 11);
        this.x = this.y; this.y = this.z; this.z = this.w;
        this.w = (this.w ^ (this.w >>> 19)) ^ (t ^ (t >>> 8));
        return (this.w >>> 0) / 4294967296;
    }
    normal() {
        const u1 = Math.max(this.next(), 1e-10);
        const u2 = this.next();
        return Math.sqrt(-2 * Math.log(u1)) * Math.cos(2 * Math.PI * u2);
    }
    /** Single uniform float in [lo, hi) */
    uniform(lo, hi) { return lo + (hi - lo) * this.next(); }
    uniformF32(lo, hi, n) {
        const a = new Float32Array(n);
        for (let i = 0; i < n; i++) a[i] = lo + (hi - lo) * this.next();
        return a;
    }
    normalF32(n) {
        const a = new Float32Array(n);
        for (let i = 0; i < n; i++) a[i] = this.normal();
        return a;
    }
    randomF32(n) {
        const a = new Float32Array(n);
        for (let i = 0; i < n; i++) a[i] = this.next();
        return a;
    }
    choice(pool, n) {
        const a = new Int32Array(n);
        const len = pool.length;
        for (let i = 0; i < n; i++) a[i] = pool[Math.floor(this.next() * len)];
        return a;
    }
    integers(lo, hi, n) {
        const a = new Int32Array(n);
        const range = hi - lo;
        for (let i = 0; i < n; i++) a[i] = lo + Math.floor(this.next() * range);
        return a;
    }
    boolMask(prob, n) {
        const a = new Uint8Array(n);
        for (let i = 0; i < n; i++) a[i] = this.next() < prob ? 1 : 0;
        return a;
    }
}

// ------------------------------------------------------------------ helpers
function _riparti(n, gruppi) {
    const base = Math.floor(n / gruppi);
    const resto = n % gruppi;
    const arr = new Array(gruppi);
    for (let i = 0; i < gruppi; i++) arr[i] = base + (i < resto ? 1 : 0);
    return arr;
}

function _hsvToRgb(h, s, v) {
    const i = Math.floor(h * 6);
    const f = h * 6 - i;
    const p = v * (1 - s);
    const q = v * (1 - f * s);
    const t = v * (1 - (1 - f) * s);
    switch (i % 6) {
        case 0: return [v, t, p];
        case 1: return [q, v, p];
        case 2: return [p, v, t];
        case 3: return [p, q, v];
        case 4: return [t, p, v];
        case 5: return [v, p, q];
    }
}

function _rgbToHsv(r, g, b) {
    const max = Math.max(r, g, b), min = Math.min(r, g, b);
    const d = max - min;
    let h = 0;
    if (d > 1e-9) {
        if (max === r)      h = ((g - b) / d + (g < b ? 6 : 0)) / 6;
        else if (max === g) h = ((b - r) / d + 2) / 6;
        else                h = ((r - g) / d + 4) / 6;
    }
    return [h, max > 1e-9 ? d / max : 0, max];
}

/** The same color, with saturation raised by INTENSITA_COLORE. */
function _acceso(rgb) {
    const [h, s, v] = _rgbToHsv(rgb[0], rgb[1], rgb[2]);
    return _hsvToRgb(h, Math.min(1, s * INTENSITA_COLORE), v);
}

/**
 * The passage from blue to the personal tint, k from 0 to 1.
 *
 * It is NOT an average of the two colors, and that is a lesson learned the
 * hard way: blue sits at 212 degrees and the tints Claude chooses often sit
 * on the other side of the wheel, so averaging would walk the color along the
 * shortest path between them — and that path is a THIRD tint. With an amber
 * anchor the meditation stayed for a minute on a green that had nothing to
 * do with what the person had told.
 *
 * Here instead hue never moves: until halfway it is the blue discharging,
 * from halfway on it is the personal tint charging, and in the middle both
 * pass through grey. LIGHTNESS goes straight across: it is the only one of
 * the three that has no wrong road.
 */
function _miscela(blu, personale, k) {
    const [hB, sB, vB] = _rgbToHsv(blu[0], blu[1], blu[2]);
    const [hP, sP, vP] = _rgbToHsv(personale[0], personale[1], personale[2]);
    const v = vB + (vP - vB) * k;
    if (k < 0.5) return _hsvToRgb(hB, sB * (1 - 2 * k), v);
    return _hsvToRgb(hP, sP * (2 * k - 1), v);
}

// ------------------------------------------------------------------ main class
export class ParticleLogic {
    constructor() {
        this._c = {};          // cache: everything computed once
        this._triangoli = null;
        this._pronto = false;
        this._onResize = () => { this._c.polvere = null; };
        window.addEventListener('resize', this._onResize);
    }

    async init() {
        const resp = await fetch('/face_triangoli.txt');
        const txt = await resp.text();
        // Parse lines, skip comments
        const righe = txt.split('\n')
            .filter(r => r.trim() && !r.startsWith('#'))
            .map(r => r.trim().split(/\s+/).map(Number));
        this._triangoli = righe;
        this._prepara(null);
        this._pronto = true;
    }

    // ---------------------------------------------------------------- public API
    prepareTexts(frasi, canvasFn) {
        // canvasFn(frase) → Float32Array[n*3] of positions
        if (!canvasFn) return;
        const testi = this._c.testi || {};
        const n = this._c.n || TOTALE_PARTICELLE;
        for (const frase of (frasi || [])) {
            if (!testi[frase]) {
                const pos = canvasFn(frase, n);
                if (pos) testi[frase] = pos;
            }
        }
        this._c.testi = testi;
    }

    prepareMandala(petali, anelli, tonalita, seed, emozione = MANDALA_EMOZIONE_DEFAULT) {
        const n = this._c.n || TOTALE_PARTICELLE;
        this._c.mandala_tonalita = tonalita;
        this._c.mandala_emozione = (emozione || MANDALA_EMOZIONE_DEFAULT).toUpperCase();
        this._genera_mandala(n, petali, anelli, seed);
    }

    /**
     * Register the personal tint Claude derives from the story.
     * It arrives well before the mandala: as soon as the model has answered.
     * Alone it changes nothing on screen — how much is visible is decided by tintaForza().
     */
    tinta(tonalita, emozione = MANDALA_EMOZIONE_DEFAULT) {
        this._c.mandala_tonalita = Number(tonalita);
        this._c.mandala_emozione = String(emozione || MANDALA_EMOZIONE_DEFAULT);
    }

    /**
     * How much personal tint is visible: 0 the usual blue, 1 only it.
     * Moves over 'durata' seconds instead of snapping, and starts from the
     * value reached NOW: so two close commands concatenate instead of
     * di strapparsi.
     */
    tintaForza(valore, durata = DURATA_TINTA) {
        this._c.tinta_da = this.quantaTinta();
        this._c.tinta_a = Math.min(1, Math.max(0, Number(valore)));
        this._c.tinta_t0 = performance.now() / 1000;
        this._c.tinta_durata = Math.max(0, Number(durata));
    }

    /** The blend in progress. Without a tint returns 0, i.e. blue. */
    quantaTinta(ora = null) {
        const c = this._c;
        if (c.tinta_a == null) return 0;
        if (ora === null) ora = performance.now() / 1000;
        const da = c.tinta_da || 0, a = c.tinta_a;
        if (!(c.tinta_durata > 0)) return a;
        let k = Math.min(1, Math.max(0, (ora - c.tinta_t0) / c.tinta_durata));
        // smoothstep: the blend starts and arrives FROM REST. A tint change
        // is noticed exactly at the instant it begins and the instant it ends.
        k = k * k * (3 - 2 * k);
        return da + (a - da) * k;
    }

    /**
     * Current background halo color. The shader multiplies the circular
     * gradient on top, which is white and carries only the shape.
     */
    backgroundColor(ora = null) {
        const blu = _acceso(SFONDO_CALMA);
        if (this._c.mandala_tonalita == null) return blu;
        // personal tint keeps saturation and lightness of the blue halo:
        // it must stay the barely perceptible halo it always was, not a blotch
        const [, sat, val] = _rgbToHsv(SFONDO_CALMA[0], SFONDO_CALMA[1], SFONDO_CALMA[2]);
        const h = (((this._c.mandala_tonalita % 360) + 360) % 360) / 360;
        return _miscela(blu, _acceso(_hsvToRgb(h, sat, val)), this.quantaTinta(ora));
    }

    goTo(tipo, testo = '', durata = null) {
        if (tipo === 'dissoluzione') {
            this._c.fuga = null;
            this._c.libera = null;
            this._c.naso_prec = null;
            this._c.t_diss = null;
        }
        this._c.scena_da = this._c.scena_a || ['volto', ''];
        this._c.scena_a = [tipo, testo];
        this._c.t0 = performance.now() / 1000;
        this._c.durata = durata !== null ? durata : DURATA_TRANSIZIONE;
    }

    reset() {
        this._c.fuga = null;
        this._c.libera = null;
        this._c.naso_prec = null;
        this._c.t_diss = null;
        this._c.testi = {};
        // personal tint leaves with the phrases: without this a new session
        // would start already colored by whoever was there before
        this._c.mandala_tonalita = null;
        this._c.mandala_emozione = null;
        this._c.tinta_a = null;
        this._c.tinta_da = null;
        this._c.scena_da = ['volto', ''];
        this._c.scena_a  = ['volto', ''];
        this._c.t0    = performance.now() / 1000;
        this._c.durata = 0.0;
    }

    /**
     * Update particles and return {posizioni, colori} as Float32Array[n*3].
     * P: array of normalized {x,y,z} (478 MediaPipe landmarks), or null.
     * ora: seconds (performance.now()/1000).
     */
    update(P, ora) {
        const n = this._c.n || TOTALE_PARTICELLE;

        // Convert MediaPipe landmarks → 3D scene coordinates
        let pts = null;
        if (P && P.length >= 478) {
            const aspetto = screenAspect();
            pts = new Float32Array(P.length * 3);
            for (let i = 0; i < P.length; i++) {
                pts[i * 3]     = (0.5 - P[i].x) * aspetto * SCALE;
                pts[i * 3 + 1] = (0.5 - P[i].y) * SCALE;
                pts[i * 3 + 2] = -P[i].z * SCALE;
            }
        }

        const [da_scena, a_scena, avanzamento] = this._stato_danza(ora);

        const posA = this._forma(a_scena, pts, n, ora, false);
        let bersaglio = new Float32Array(posA);
        let fioritura = null;

        if (da_scena[0] !== a_scena[0] && avanzamento < 1.0) {
            const posD = this._forma(da_scena, pts, n, ora, true);
            const ritardi = this._c.ritardi;
            const k = new Float32Array(n);
            for (let i = 0; i < n; i++) {
                let loc = avanzamento * (1 + RITARDO_MAX) - ritardi[i];
                loc = Math.min(Math.max(loc, 0), 1);
                k[i] = loc * loc * (3 - 2 * loc);  // smoothstep
                bersaglio[i * 3]     = posD[i * 3]     * (1 - k[i]) + posA[i * 3]     * k[i];
                bersaglio[i * 3 + 1] = posD[i * 3 + 1] * (1 - k[i]) + posA[i * 3 + 1] * k[i];
                bersaglio[i * 3 + 2] = posD[i * 3 + 2] * (1 - k[i]) + posA[i * 3 + 2] * k[i];
            }
            fioritura = k;
        }

        // Compute the extent of the target shape
        let minX = Infinity, maxX = -Infinity;
        let minY = Infinity, maxY = -Infinity;
        let minZ = Infinity, maxZ = -Infinity;
        for (let i = 0; i < n; i++) {
            if (posA[i*3]   < minX) minX = posA[i*3];
            if (posA[i*3]   > maxX) maxX = posA[i*3];
            if (posA[i*3+1] < minY) minY = posA[i*3+1];
            if (posA[i*3+1] > maxY) maxY = posA[i*3+1];
            if (posA[i*3+2] < minZ) minZ = posA[i*3+2];
            if (posA[i*3+2] > maxZ) maxZ = posA[i*3+2];
        }
        const estensione = Math.max(maxX - minX, maxY - minY, maxZ - minZ);

        // Bloom at mid-transition
        if (fioritura) {
            const dir = this._c.direzioni;
            for (let i = 0; i < n; i++) {
                const f = Math.sin(Math.PI * fioritura[i]) * ESPANSIONE * estensione;
                bersaglio[i*3]   += dir[i*3]   * f;
                bersaglio[i*3+1] += dir[i*3+1] * f;
                bersaglio[i*3+2] += dir[i*3+2] * f;
            }
        }

        // Fog: almost absent for text (otherwise letters wash out)
        let alone = NEBBIA_RAGGIO * estensione;
        if (a_scena[0] === 'mandala') alone *= MANDALA_NEBBIA;
        if (a_scena[0] === 'testo')   alone *= 0.08;  // text: minimal fog
        const nebbia = this._c.nebbia;
        for (let i = 0; i < n; i++) {
            bersaglio[i*3]   += nebbia[i*3]   * alone;
            bersaglio[i*3+1] += nebbia[i*3+1] * alone;
            bersaglio[i*3+2] += nebbia[i*3+2] * alone;
        }

        // Individual fluctuation (reduced for text)
        const fluttScala = a_scena[0] === 'testo' ? 0.1 : 1.0;
        const freq = this._c.frequenze, fasi = this._c.fasi, ampl = this._c.ampiezze;
        for (let i = 0; i < n; i++) {
            bersaglio[i*3]   += ampl[i] * fluttScala * Math.sin(ora * freq[i*3]   + fasi[i*3]);
            bersaglio[i*3+1] += ampl[i] * Math.sin(ora * freq[i*3+1] + fasi[i*3+1]);
            bersaglio[i*3+2] += ampl[i] * Math.sin(ora * freq[i*3+2] + fasi[i*3+2]);
        }

        // Shared current (coherent velocity field)
        for (let i = 0; i < n; i++) {
            const px = bersaglio[i*3]   * CURRENT_SCALE;
            const py = bersaglio[i*3+1] * CURRENT_SCALE;
            const tt = ora * CORRENTE_VELOCITA;
            bersaglio[i*3]   += Math.sin(py + tt)         * Math.cos(px * 0.6 + tt * 1.3) * CORRENTE_AMPIEZZA;
            bersaglio[i*3+1] += Math.sin(px + tt * 1.1)   * Math.cos(py * 0.6 + tt * 0.9) * CORRENTE_AMPIEZZA;
            bersaglio[i*3+2] += Math.sin(px * 0.8 + tt * 0.8) * Math.cos(py * 0.8 + tt * 1.2) * CORRENTE_AMPIEZZA;
        }

        // Inertia: each particle chases the target with its own laziness
        let pos = this._c.posizioni;
        if (!pos || pos.length !== n * 3) {
            pos = bersaglio.slice();
        } else if (a_scena[0] === 'dissoluzione' && pts) {
            pos = this._fuga(pos, bersaglio, pts, ora);
        } else {
            const inerzia = this._c.inerzia;
            for (let i = 0; i < n; i++) {
                pos[i*3]   += (bersaglio[i*3]   - pos[i*3])   * inerzia[i];
                pos[i*3+1] += (bersaglio[i*3+1] - pos[i*3+1]) * inerzia[i];
                pos[i*3+2] += (bersaglio[i*3+2] - pos[i*3+2]) * inerzia[i];
            }
        }
        this._c.posizioni = pos;

        const colori = this._colori(da_scena[0], a_scena[0], avanzamento, pos, ora);

        return { posizioni: pos, colori , background: this.backgroundColor(ora) };
    }

    // ---------------------------------------------------------------- internal: initialization
    _prepara(P) {
        const triangoli = this._triangoli;
        if (!triangoli) return;

        const rng = new RNG(7);
        const T = triangoli.length;

        // Compute per-triangle quotas (area-weighted with exponent)
        let conteggi;
        if (P) {
            const aree = new Float32Array(T);
            for (let t = 0; t < T; t++) {
                const [a, b, c] = triangoli[t];
                const ax = P[a*3], ay = P[a*3+1], az = P[a*3+2];
                const bx = P[b*3], by = P[b*3+1], bz = P[b*3+2];
                const cx = P[c*3], cy = P[c*3+1], cz = P[c*3+2];
                const ux = bx-ax, uy = by-ay, uz = bz-az;
                const vx = cx-ax, vy = cy-ay, vz = cz-az;
                aree[t] = 0.5 * Math.sqrt(
                    (uy*vz - uz*vy)**2 + (uz*vx - ux*vz)**2 + (ux*vy - uy*vx)**2
                );
            }
            let somma = 0;
            const peso = new Float32Array(T);
            for (let t = 0; t < T; t++) {
                peso[t] = Math.pow(aree[t], ESPONENTE_DENSITA);
                somma += peso[t];
            }
            conteggi = new Int32Array(T);
            let totale = 0;
            for (let t = 0; t < T; t++) {
                conteggi[t] = Math.max(1, Math.round(peso[t] / somma * TOTALE_PARTICELLE));
                totale += conteggi[t];
            }
            // Adjust the remainder onto the larger triangles
            let diff = TOTALE_PARTICELLE - totale;
            if (diff !== 0) {
                const ordine = Array.from({length: T}, (_, i) => i)
                    .sort((a, b) => aree[b] - aree[a]);
                const passo = diff > 0 ? 1 : -1;
                for (let i = 0; i < Math.abs(diff); i++) {
                    const j = ordine[i % T];
                    if (conteggi[j] + passo >= 1) conteggi[j] += passo;
                }
            }
        } else {
            const q = Math.max(1, Math.floor(TOTALE_PARTICELLE / T));
            conteggi = new Int32Array(T);
            conteggi.fill(q);
        }

        // Expand: one row per particle (repeat each triangle conteggi[t] times)
        let n = 0;
        for (let t = 0; t < T; t++) n += conteggi[t];

        const idxA = new Int32Array(n);
        const idxB = new Int32Array(n);
        const idxC = new Int32Array(n);
        let pos = 0;
        for (let t = 0; t < T; t++) {
            for (let k = 0; k < conteggi[t]; k++) {
                idxA[pos] = triangoli[t][0];
                idxB[pos] = triangoli[t][1];
                idxC[pos] = triangoli[t][2];
                pos++;
            }
        }

        // Random barycentric coordinates
        const pesi = new Float32Array(n * 3);
        for (let i = 0; i < n; i++) {
            let r0 = rng.next(), r1 = rng.next();
            if (r0 + r1 > 1.0) { r0 = 1 - r0; r1 = 1 - r1; }
            pesi[i*3]   = 1 - r0 - r1;
            pesi[i*3+1] = r0;
            pesi[i*3+2] = r1;
        }

        const inerzia = rng.uniformF32(INERZIA_MIN, INERZIA_MAX, n);

        const e_nebbia = rng.boolMask(FRAZIONE_NEBBIA, n);
        const nebbia   = rng.normalF32(n * 3);
        for (let i = 0; i < n; i++) {
            if (!e_nebbia[i]) {
                nebbia[i*3] = nebbia[i*3+1] = nebbia[i*3+2] = 0;
            }
        }

        const frequenze = rng.uniformF32(0.15, 0.6, n * 3);
        const fasi      = rng.uniformF32(0.0, 2 * Math.PI, n * 3);
        const ampiezze  = new Float32Array(n);
        for (let i = 0; i < n; i++) {
            ampiezze[i] = e_nebbia[i] ? FLUTTUAZIONE * FLUTTUAZIONE_NEBBIA : FLUTTUAZIONE;
        }

        const ritardi   = rng.uniformF32(0.0, RITARDO_MAX, n);

        const direzioni = rng.normalF32(n * 3);
        for (let i = 0; i < n; i++) {
            const len = Math.sqrt(
                direzioni[i*3]**2 + direzioni[i*3+1]**2 + direzioni[i*3+2]**2
            ) || 1;
            direzioni[i*3] /= len; direzioni[i*3+1] /= len; direzioni[i*3+2] /= len;
        }

        const tono = rng.uniformF32(0.45, 1.0, n);
        for (let i = 0; i < n; i++) {
            if (e_nebbia[i]) tono[i] = rng.uniform(0, NEBBIA_LUMINOSITA);
        }
        const scint_freq = rng.uniformF32(0.5, 1.6, n);
        const scint_fase = rng.uniformF32(0.0, 2 * Math.PI, n);

        Object.assign(this._c, {
            n, idxA, idxB, idxC, pesi, inerzia, e_nebbia, nebbia,
            frequenze, fasi, ampiezze, ritardi, direzioni,
            tono, scint_freq, scint_fase,
            posizioni: null,
            scena_da: ['volto', ''],
            scena_a:  ['volto', ''],
            t0: performance.now() / 1000,
            durata: 0,
            testi: {},
            per_area: P !== null,
        });
    }

    // ---------------------------------------------------------------- internal: shapes
    _forma_volto(pts, n) {
        const { idxA, idxB, idxC, pesi } = this._c;
        const out = new Float32Array(n * 3);
        if (!pts) {
            // Fallback: dust cloud if there is no face
            return this._forma_polvere(n);
        }
        for (let i = 0; i < n; i++) {
            const a = idxA[i], b = idxB[i], c = idxC[i];
            const wa = pesi[i*3], wb = pesi[i*3+1], wc = pesi[i*3+2];
            out[i*3]   = pts[a*3]   * wa + pts[b*3]   * wb + pts[c*3]   * wc;
            out[i*3+1] = pts[a*3+1] * wa + pts[b*3+1] * wb + pts[c*3+1] * wc;
            out[i*3+2] = pts[a*3+2] * wa + pts[b*3+2] * wb + pts[c*3+2] * wc;
        }
        return out;
    }

    _forma_polvere(n) {
        if (this._c.polvere && this._c.polvere.length === n * 3) {
            return this._c.polvere;
        }
        const rng = new RNG(SEME_POLVERE);
        const aspetto = screenAspect();
        const raggio  = visibleRadius();
        const pos = new Float32Array(n * 3);
        for (let i = 0; i < n; i++) {
            pos[i*3]   = CAM_TX + rng.normal() * raggio * POLVERE_AMPIEZZA * aspetto;
            pos[i*3+1] = CAM_TY + rng.normal() * raggio * POLVERE_AMPIEZZA;
            pos[i*3+2] = rng.normal() * raggio * POLVERE_PROFONDITA - raggio * POLVERE_ARRETRAMENTO;
        }
        this._c.polvere = pos;
        return pos;
    }

    _genera_mandala(n, petali, anelli, seed) {
        anelli  = Math.max(Math.floor(anelli), 1);
        petali  = Math.max(Math.floor(petali), 2);
        const rng = new RNG(Math.floor(seed));
        const ragMax = visibleRadius();
        const conteggi = _riparti(n, anelli);
        const spaziatura = (0.82 / anelli) * ragMax;
        const sfogo = spaziatura * 0.45;

        const angoli = new Float32Array(n);
        const raggi  = new Float32Array(n);
        let inizio = 0;

        for (let i = 0; i < anelli; i++) {
            const cnt = conteggi[i];
            if (!cnt) continue;
            const fine = inizio + cnt;

            const quota = (i + 1) / anelli;
            const raggio_base = ragMax * (0.18 + 0.82 * quota);
            const ampiezza = Math.min(MANDALA_PETALO * raggio_base, sfogo) / raggio_base;
            const armonica = Math.min(MANDALA_ARMONICA * raggio_base, sfogo * 0.4) / raggio_base;

            const tipo = i % 3;
            let gruppi = 0, dispersione = 0;
            if (tipo === 0)      { gruppi = petali;     dispersione = 0.20; }
            else if (tipo === 1) { gruppi = petali * 2; dispersione = 0.13; }
            else                 { gruppi = 0; }

            const fase_base = (MANDALA_SFASAMENTO ? (Math.PI / petali) * (i % 2) : 0)
                            + rng.uniform(0, 0.4);

            for (let j = inizio; j < fine; j++) {
                let a;
                if (gruppi > 0) {
                    const passo = 2 * Math.PI / gruppi;
                    a = Math.floor(rng.next() * gruppi) * passo
                      + rng.normal() * passo * dispersione;
                } else {
                    a = rng.next() * 2 * Math.PI;
                }
                const mod = 1
                    + ampiezza * Math.cos(petali * a + fase_base)
                    + armonica * Math.cos(2 * petali * a + fase_base * 2);
                const spessore = rng.normal() * Math.min(MANDALA_SPESSORE * ragMax, spaziatura * 0.16);
                angoli[j] = a;
                raggi[j]  = raggio_base * mod + spessore;
            }
            inizio = fine;
        }

        // Normalize to the maximum visible radius
        let picco = 0;
        for (let i = 0; i < n; i++) if (Math.abs(raggi[i]) > picco) picco = Math.abs(raggi[i]);
        if (picco > 1e-6) for (let i = 0; i < n; i++) raggi[i] *= ragMax / picco;

        this._c.mandala_angoli   = angoli;
        this._c.mandala_raggi    = raggi;
        this._c.mandala_raggio_max = ragMax;
    }

    _forma_mandala(ora) {
        const angoli = this._c.mandala_angoli;
        const raggi  = this._c.mandala_raggi;
        if (!angoli) return null;
        const n = angoli.length;
        const ragMax = this._c.mandala_raggio_max;
        const pos = new Float32Array(n * 3);
        const rotazione = ora * MANDALA_ROTAZIONE * 2 * Math.PI;
        for (let i = 0; i < n; i++) {
            const a = angoli[i] + rotazione;
            const r = raggi[i];
            pos[i*3]   = CAM_TX + r * Math.cos(a);
            pos[i*3+1] = CAM_TY + r * Math.sin(a);
            // dome toward the viewer at the center
            pos[i*3+2] = Math.cos(Math.min(Math.abs(r) / ragMax, 1) * (Math.PI / 2)) * MANDALA_CUPOLA;
        }
        return pos;
    }

    _forma(scena, pts, n, ora, sorgente = false) {
        const tipo = scena[0];
        if (tipo === 'dissoluzione') {
            if (sorgente) {
                const p = this._c.posizioni;
                return (p && p.length === n * 3) ? p : this._forma_volto(pts, n);
            }
            return this._forma_mandala(ora) || this._forma_volto(pts, n);
        }
        if (tipo === 'mandala') {
            const m = this._forma_mandala(ora);
            return m || this._forma_volto(pts, n);
        }
        if (tipo === 'polvere') return this._forma_polvere(n);
        if (tipo === 'testo') {
            const p = this._c.testi?.[scena[1]];
            if (p && p.length === n * 3) return p;
        }
        return this._forma_volto(pts, n);
    }

    // ---------------------------------------------------------------- dissolution
    _fuga(pos, bersaglio, pts, ora) {
        let fuga = this._c.fuga;
        const n = pos.length / 3;
        if (!fuga || fuga.length !== pos.length) fuga = new Float32Array(pos.length);

        const prev = this._c.t_diss;
        const dt = prev === null ? 0.016 : Math.min(Math.max(ora - prev, 1/240), 0.1);
        this._c.t_diss = ora;

        // Naso
        const naso = [pts[NASO*3], pts[NASO*3+1], pts[NASO*3+2]];
        const nasoPrev = this._c.naso_prec;
        this._c.naso_prec = naso.slice();
        const velNaso = nasoPrev
            ? Math.max(0, Math.sqrt((naso[0]-nasoPrev[0])**2+(naso[1]-nasoPrev[1])**2+(naso[2]-nasoPrev[2])**2)/dt - SOGLIA_MOVIMENTO)
            : 0;

        if (velNaso > 0) {
            for (let i = 0; i < n; i++) {
                const dx = pos[i*3]-naso[0], dy = pos[i*3+1]-naso[1], dz = pos[i*3+2]-naso[2];
                const dist = Math.sqrt(dx*dx+dy*dy+dz*dz) + 1e-5;
                if (dist < RAGGIO_NASO) {
                    const vic = 1 - dist / RAGGIO_NASO;
                    const spinta = FORZA_NASO * velNaso * vic * vic;
                    fuga[i*3]   += dx/dist * spinta * dt;
                    fuga[i*3+1] += dy/dist * spinta * dt;
                    fuga[i*3+2] += dz/dist * SPINTA_Z * spinta * dt;
                }
            }
        }

        // Attrito
        for (let i = 0; i < fuga.length; i++) fuga[i] *= ATTRITO_FUGA;
        this._c.fuga = fuga;

        // Compute freedom degree (ratchet: can only grow)
        let libera = this._c.libera;
        if (!libera || libera.length !== n) libera = new Float32Array(n);
        for (let i = 0; i < n; i++) {
            const vel = Math.sqrt(fuga[i*3]**2+fuga[i*3+1]**2+fuga[i*3+2]**2);
            const adesso = Math.min(vel / VELOCITA_LIBERAZIONE, 1);
            if (adesso > libera[i]) libera[i] = adesso;
        }
        this._c.libera = libera;

        // Muovi
        const inerzia = this._c.inerzia;
        const out = new Float32Array(pos.length);
        for (let i = 0; i < n; i++) {
            const lib = libera[i];
            out[i*3]   = pos[i*3]   + (bersaglio[i*3]   - pos[i*3])   * inerzia[i] * (1-lib) + fuga[i*3]   * dt;
            out[i*3+1] = pos[i*3+1] + (bersaglio[i*3+1] - pos[i*3+1]) * inerzia[i] * (1-lib) + fuga[i*3+1] * dt;
            out[i*3+2] = pos[i*3+2] + (bersaglio[i*3+2] - pos[i*3+2]) * inerzia[i] * (1-lib) + fuga[i*3+2] * dt;
        }
        return out;
    }

    // ---------------------------------------------------------------- colori
    /** The hue Claude chose, in a deep version and a bright one. */
    _tintaPersonale() {
        const h = ((this._c.mandala_tonalita % 360) + 360) % 360 / 360;
        const g = MANDALA_GRADIENTE[this._c.mandala_emozione]
            || MANDALA_GRADIENTE[MANDALA_EMOZIONE_DEFAULT];
        const mezza = (g.apertura / 2.0) / 360.0 * g.verso;
        // Values stay low as in the blue palette: they are the light of ONE
        // particle, and in additive blending where they overlap they add up.
        return {
            fondo: _hsvToRgb((h - mezza + 1) % 1, Math.min(1, g.satFondo * INTENSITA_COLORE), 0.090),
            luce:  _hsvToRgb((h + mezza + 1) % 1, Math.min(1, g.satLuce  * INTENSITA_COLORE), 0.620),
        };
    }

    /**
     * The two tints each particle draws from.
     *
     * The mandala and its dissolution use the FULL personal tint: they are the
     * moment when the meditator's color is the subject. All other shapes mix
     * it with blue to the degree decided by tintaForza().
     */
    _palette(tipo, ora = null) {
        const bluFondo = _acceso(PALETTE_CALMA.fondo);
        const bluLuce  = _acceso(PALETTE_CALMA.luce);
        if (this._c.mandala_tonalita == null) {
            return { fondo: bluFondo, luce: bluLuce };
        }
        const p = this._tintaPersonale();
        // dissolution is the mandala coming apart: it keeps its color
        if (tipo === 'mandala' || tipo === 'dissoluzione') return p;

        const k = this.quantaTinta(ora);
        if (k <= 0) return { fondo: bluFondo, luce: bluLuce };
        return {
            fondo: _miscela(bluFondo, p.fondo, k),
            luce:  _miscela(bluLuce,  p.luce,  k),
        };
    }

    _colori(tipo_da, tipo_a, avanzamento, pos, ora) {
        const n = pos.length / 3;
        const pa = this._palette(tipo_a, ora);
        let fondo, luce;
        if (tipo_da !== tipo_a && avanzamento < 1.0) {
            const pd = this._palette(tipo_da, ora);
            const k = avanzamento;
            fondo = pd.fondo.map((v, i) => v * (1-k) + pa.fondo[i] * k);
            luce  = pd.luce.map((v, i)  => v * (1-k) + pa.luce[i]  * k);
        } else {
            fondo = pa.fondo; luce = pa.luce;
        }

        const colori = new Float32Array(n * 3);
        const tono = this._c.tono;
        const sf   = this._c.scint_freq;
        const sfase = this._c.scint_fase;

        // Compute Z range for depth
        let zMin = Infinity, zMax = -Infinity;
        for (let i = 0; i < n; i++) {
            if (pos[i*3+2] < zMin) zMin = pos[i*3+2];
            if (pos[i*3+2] > zMax) zMax = pos[i*3+2];
        }
        const zRange = zMax - zMin || 1;

        for (let i = 0; i < n; i++) {
            const scint = Math.sin(ora * sf[i] * SCINTILLIO_VELOCITA + sfase[i]) * SCINTILLIO;
            const profondita = ((pos[i*3+2] - zMin) / zRange - 0.5) * PROFONDITA_COLORE;
            let t = tono[i] + scint + profondita;
            t = Math.min(Math.max(t, 0), 1);
            colori[i*3]   = fondo[0] + (luce[0] - fondo[0]) * t;
            colori[i*3+1] = fondo[1] + (luce[1] - fondo[1]) * t;
            colori[i*3+2] = fondo[2] + (luce[2] - fondo[2]) * t;
        }
        return colori;
    }

    // ---------------------------------------------------------------- stato danza
    _stato_danza(ora) {
        const c = this._c;
        if (!c.scena_a) {
            c.scena_da = ['volto', '']; c.scena_a = ['volto', ''];
            c.t0 = ora; c.durata = DURATA_TRANSIZIONE;
        }
        const av = Math.min(Math.max((ora - c.t0) / Math.max(c.durata, 0.001), 0), 1);
        return [c.scena_da, c.scena_a, av];
    }
}
