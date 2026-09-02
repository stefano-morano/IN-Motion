/**
 * logica.js — porta diretta di td_face_points.py in JavaScript.
 *
 * Calcola ogni fotogramma le posizioni e i colori delle 13.664 particelle.
 * Nessuna dipendenza da Three.js: restituisce Float32Array grezze che il
 * renderer può caricare in BufferGeometry senza ulteriori conversioni.
 */

import {
    SCALA, CAM_TX, CAM_TY,
    aspettoSchermo, raggioVisibile,
} from './scena.js';

// ------------------------------------------------------------------ costanti
const TOTALE_PARTICELLE = 13664;
const ESPONENTE_DENSITA = 0.45;

const PALETTE_CALMA = {
    fondo: [0.020, 0.045, 0.115],
    luce:  [0.300, 0.460, 0.640],
};
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
// Il raggio visibile corrisponde a metà altezza del frustum (SCALA/2)

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
const CORRENTE_SCALA = 1.4;
const CORRENTE_VELOCITA = 0.25;
const INERZIA_MIN = 0.04;
const INERZIA_MAX = 0.28;

// dissoluzione
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
    /** Singolo float uniforme in [lo, hi) */
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

// ------------------------------------------------------------------ classe principale
export class LogicaParticelle {
    constructor() {
        this._c = {};          // cache: tutto quello che si calcola una volta
        this._triangoli = null;
        this._pronto = false;
        this._onResize = () => { this._c.polvere = null; };
        window.addEventListener('resize', this._onResize);
    }

    async init() {
        const resp = await fetch('/face_triangoli.txt');
        const txt = await resp.text();
        // Parsa le righe, salta i commenti
        const righe = txt.split('\n')
            .filter(r => r.trim() && !r.startsWith('#'))
            .map(r => r.trim().split(/\s+/).map(Number));
        this._triangoli = righe;
        this._prepara(null);
        this._pronto = true;
    }

    // ---------------------------------------------------------------- API pubblica
    prepara_testi(frasi, canvasFn) {
        // canvasFn(frase) → Float32Array[n*3] delle posizioni
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

    prepara_mandala(petali, anelli, tonalita, seed, emozione = 'Q2') {
        const n = this._c.n || TOTALE_PARTICELLE;
        this._c.mandala_tonalita = tonalita;
        // L'emozione decide quanto il colore si apre in gradiente (GRADIENTE in
        // mandala.py). Il gradiente non e' ancora portato in JavaScript: il
        // valore si conserva qui perche' chi lo portera' lo trovi gia' pronto.
        this._c.mandala_emozione = emozione;
        this._genera_mandala(n, petali, anelli, seed);
    }

    vai_a(tipo, testo = '', durata = null) {
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

    azzera() {
        this._c.fuga = null;
        this._c.libera = null;
        this._c.naso_prec = null;
        this._c.t_diss = null;
        this._c.testi = {};
        this._c.scena_da = ['volto', ''];
        this._c.scena_a  = ['volto', ''];
        this._c.t0    = performance.now() / 1000;
        this._c.durata = 0.0;
    }

    /**
     * Aggiorna le particelle e restituisce {posizioni, colori} come Float32Array[n*3].
     * P: array di {x,y,z} normalizzati (478 landmark MediaPipe), o null.
     * ora: secondi (performance.now()/1000).
     */
    aggiorna(P, ora) {
        const n = this._c.n || TOTALE_PARTICELLE;

        // Converti landmark MediaPipe → coordinate scena 3D
        let pts = null;
        if (P && P.length >= 478) {
            const aspetto = aspettoSchermo();
            pts = new Float32Array(P.length * 3);
            for (let i = 0; i < P.length; i++) {
                pts[i * 3]     = (0.5 - P[i].x) * aspetto * SCALA;
                pts[i * 3 + 1] = (0.5 - P[i].y) * SCALA;
                pts[i * 3 + 2] = -P[i].z * SCALA;
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

        // Calcola l'estensione della forma target
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

        // Fioritura a metà transizione
        if (fioritura) {
            const dir = this._c.direzioni;
            for (let i = 0; i < n; i++) {
                const f = Math.sin(Math.PI * fioritura[i]) * ESPANSIONE * estensione;
                bersaglio[i*3]   += dir[i*3]   * f;
                bersaglio[i*3+1] += dir[i*3+1] * f;
                bersaglio[i*3+2] += dir[i*3+2] * f;
            }
        }

        // Nebbia: quasi assente per il testo (altrimenti le lettere si sfumano)
        let alone = NEBBIA_RAGGIO * estensione;
        if (a_scena[0] === 'mandala') alone *= MANDALA_NEBBIA;
        if (a_scena[0] === 'testo')   alone *= 0.08;  // testo: nebbia minima
        const nebbia = this._c.nebbia;
        for (let i = 0; i < n; i++) {
            bersaglio[i*3]   += nebbia[i*3]   * alone;
            bersaglio[i*3+1] += nebbia[i*3+1] * alone;
            bersaglio[i*3+2] += nebbia[i*3+2] * alone;
        }

        // Fluttuazione individuale (ridotta per testo)
        const fluttScala = a_scena[0] === 'testo' ? 0.1 : 1.0;
        const freq = this._c.frequenze, fasi = this._c.fasi, ampl = this._c.ampiezze;
        for (let i = 0; i < n; i++) {
            bersaglio[i*3]   += ampl[i] * fluttScala * Math.sin(ora * freq[i*3]   + fasi[i*3]);
            bersaglio[i*3+1] += ampl[i] * Math.sin(ora * freq[i*3+1] + fasi[i*3+1]);
            bersaglio[i*3+2] += ampl[i] * Math.sin(ora * freq[i*3+2] + fasi[i*3+2]);
        }

        // Corrente comune (campo di velocità coerente)
        for (let i = 0; i < n; i++) {
            const px = bersaglio[i*3]   * CORRENTE_SCALA;
            const py = bersaglio[i*3+1] * CORRENTE_SCALA;
            const tt = ora * CORRENTE_VELOCITA;
            bersaglio[i*3]   += Math.sin(py + tt)         * Math.cos(px * 0.6 + tt * 1.3) * CORRENTE_AMPIEZZA;
            bersaglio[i*3+1] += Math.sin(px + tt * 1.1)   * Math.cos(py * 0.6 + tt * 0.9) * CORRENTE_AMPIEZZA;
            bersaglio[i*3+2] += Math.sin(px * 0.8 + tt * 0.8) * Math.cos(py * 0.8 + tt * 1.2) * CORRENTE_AMPIEZZA;
        }

        // Inerzia: ogni particella insegue il bersaglio con la sua pigrizia
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

        return { posizioni: pos, colori };
    }

    // ---------------------------------------------------------------- interno: inizializzazione
    _prepara(P) {
        const triangoli = this._triangoli;
        if (!triangoli) return;

        const rng = new RNG(7);
        const T = triangoli.length;

        // Calcola le quote per triangolo (area-weighted con esponente)
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
            // Aggiusta la differenza sui triangoli più grandi
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

        // Espandi: una riga per particella (ripeti ogni triangolo conteggi[t] volte)
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

        // Coordinate baricentriche casuali
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

    // ---------------------------------------------------------------- interno: forme
    _forma_volto(pts, n) {
        const { idxA, idxB, idxC, pesi } = this._c;
        const out = new Float32Array(n * 3);
        if (!pts) {
            // Fallback: nuvola di polvere se non c'è il volto
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
        const aspetto = aspettoSchermo();
        const raggio  = raggioVisibile();
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
        const ragMax = raggioVisibile();
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

        // Normalizza al raggio massimo visibile
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
            // cupola verso l'osservatore al centro
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

    // ---------------------------------------------------------------- dissoluzione
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

        // Calcola grado di libertà (cricchetto: può solo crescere)
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
    _palette(tipo) {
        if ((tipo === 'mandala' || tipo === 'dissoluzione') && this._c.mandala_tonalita != null) {
            const h = ((this._c.mandala_tonalita % 360) + 360) % 360 / 360;
            const fondo = _hsvToRgb(h, 0.80, 0.090);
            const luce  = _hsvToRgb((h - 0.045 + 1) % 1, 0.42, 0.620);
            return { fondo, luce };
        }
        return { fondo: PALETTE_CALMA.fondo, luce: PALETTE_CALMA.luce };
    }

    _colori(tipo_da, tipo_a, avanzamento, pos, ora) {
        const n = pos.length / 3;
        const pa = this._palette(tipo_a);
        let fondo, luce;
        if (tipo_da !== tipo_a && avanzamento < 1.0) {
            const pd = this._palette(tipo_da);
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

        // Calcola range Z per profondità
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
