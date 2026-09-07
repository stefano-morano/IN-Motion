/**
 * app.js — orchestratore lato browser.
 *
 * Collega WebSocket, MediaPipe face tracking, Web Audio API
 * e il renderer Three.js in un unico ciclo di animazione.
 */

import { FaceLandmarker, FilesetResolver }
    from 'https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@0.10.14/vision_bundle.mjs';
import { RendererParticelle } from './renderer/particelle.js';
import { LogicaParticelle }   from './renderer/logica.js';
import { campionaTesto }      from './renderer/testo_canvas.js';
import { AnalizzatoreEmozioni } from './renderer/emozioni.js';
import { loginGoogle, logout, onAuth, salvaSessione, inizializza,
         loginEmail, registraEmail, resetPassword,
         caricaProfilo, salvaProfilo,
         salvaSessioneGiornaliera, caricaSessioniCalendario } from './firebase.js';

// ------------------------------------------------------------------ stato globale
let ws;
let renderer;
let logica;
let faceLandmarker;
let video;
let landmarks    = null;
let blendshapes  = null;                       // MediaPipe face blend shapes
let _utenteCorrente = null;
let _tInizio        = null;
let _testoSessione  = '';
let _profiloUtente  = null;                    // dati profilo (nome, età, obiettivo…)
const _analizzatore = new AnalizzatoreEmozioni();

// Dati per grafici e storico
let _emozionePre    = null;   // report facciale pre-meditazione
let _seriePre       = { valenza: [], arousal: [] };
let _seriePost      = { valenza: [], arousal: [] };
let _durataSessione = 0;
let _analizzatorePost = null; // analizzatore per la fase post
let _tInizioPost    = false;  // true durante la riflessione post
let _calSessioni    = {};     // { 'YYYY-MM-DD': [{...}] } per il calendario
let _calMese        = new Date();
let _calCharts      = [];       // istanze Chart.js nel dettaglio calendario
let _sessioneIniziata = false;
let _pendingInizia    = false;
let _postMostrato     = false;
let _esperienzaFinita = false;
let _inRiflessione    = false;
let _riflessioneCompletata = false;

const WS_URL = `ws://${location.host}/ws`;
const stato = document.getElementById('stato');
const ui    = document.getElementById('ui');

// ------------------------------------------------------------------ audio
// ------------------------------------------------------------------ il tappeto
// Allineati a visuals/musica.py. Il motore musicale genererebbe direttamente
// una versione cosi' (bastano polifonia e intensita' ritmica piu' basse), ma
// qui la libreria e' gia' resa: si lavora sull'audio.
const RALLENTAMENTO = 0.40;
const TAGLIO_ALTE = 2600.0;

class AudioManager {
    constructor() {
        this.ctx = null;
        this._masterVolume = 1;
        this._muted = false;
        this._sorgenti = {
            // Tre guadagni per sorgente, non uno: si moltiplicano fra loro e
            // rispondono a tre domande diverse.
            //   gainVol   quanto forte va in questa scena?      (macchina a stati)
            //   gainAtt   quanto la abbasso per la campana?     (stacco)
            //   gainVoce  quanto la abbasso perche' si parla?   (voce)
            // Con un numero solo si sovrascriverebbero a vicenda: lo stacco
            // riporterebbe su una musica che la voce voleva bassa.
            principale: { node: null, gainVol: null, gainAtt: null, gainVoce: null, volume: 0 },
            tappeto:    { node: null, gainVol: null, gainAtt: null, gainVoce: null, volume: 0 },
        };
        this._cache = new Map();
        this._recorder = null;
        this._audioChunks = [];
        this._micStream = null;
        this._onAudioReady = null;
    }

    async _ensure() {
        if (!this.ctx) {
            this.ctx = new AudioContext({ sampleRate: 44100 });
            this._masterGain = this.ctx.createGain();
            this._masterGain.gain.value = this._muted ? 0 : this._masterVolume;
            this._masterGain.connect(this.ctx.destination);
        }
        if (this.ctx.state === 'suspended') await this.ctx.resume();
    }

    setMasterVolume(livello) {
        this._masterVolume = Math.max(0, Math.min(1, livello));
        if (!this.ctx || !this._masterGain || this._muted) return;
        const t = this.ctx.currentTime;
        this._masterGain.gain.cancelScheduledValues(t);
        this._masterGain.gain.setValueAtTime(this._masterGain.gain.value, t);
        this._masterGain.gain.linearRampToValueAtTime(this._masterVolume, t + 0.08);
    }

    toggleMute() {
        if (!this.ctx || !this._masterGain) return this._muted;
        this._muted = !this._muted;
        const t = this.ctx.currentTime;
        this._masterGain.gain.cancelScheduledValues(t);
        this._masterGain.gain.setValueAtTime(this._masterGain.gain.value, t);
        this._masterGain.gain.linearRampToValueAtTime(
            this._muted ? 0 : this._masterVolume,
            t + 0.3
        );
        return this._muted;
    }

    async _carica(url) {
        if (this._cache.has(url)) return this._cache.get(url);
        const r   = await fetch(url);
        const arr = await r.arrayBuffer();
        const buf = await this.ctx.decodeAudioData(arr);
        this._cache.set(url, buf);
        return buf;
    }

    /**
     * Quanti attacchi al secondo ha una traccia.
     *
     * E' un descrittore audio, la porta di visuals/musica.py: si divide il
     * segnale in finestre da 20 ms, si misura l'energia di ciascuna, e si
     * contano i SALTI di energia che superano una frazione della media. Un
     * salto e' una nota che entra.
     */
    _densitaAttacchi(buf) {
        const sr = buf.sampleRate;
        const ch = buf.getChannelData(0);
        const n = Math.floor(sr * 0.02);
        const finestre = Math.floor(ch.length / n);
        if (finestre < 2) return 0;
        const energia = new Float32Array(finestre);
        let somma = 0;
        for (let i = 0; i < finestre; i++) {
            let acc = 0;
            for (let j = 0; j < n; j++) { const v = ch[i * n + j]; acc += v * v; }
            energia[i] = Math.sqrt(acc / n);
            somma += energia[i];
        }
        const soglia = (somma / finestre) * 0.35;
        let attacchi = 0;
        for (let i = 1; i < finestre; i++) {
            if (energia[i] - energia[i - 1] > soglia) attacchi++;
        }
        return attacchi / (ch.length / sr);
    }

    /**
     * Fra le quattro variazioni del quadrante, quella con MENO attacchi.
     *
     * Sotto le scritte deve stare la piu' silenziosa, non una a caso: fra le
     * quattro la differenza e' piu' del doppio. Si sceglie una volta sola e si
     * ricorda, perche' il tappeto si carica all'avvio e non cambia piu'.
     */
    async _piuRada(emozione) {
        if (this._rade?.has(emozione)) return this._rade.get(emozione);
        if (!this._rade) this._rade = new Map();
        let scelta = null, minimo = Infinity;
        for (let i = 0; i < 4; i++) {
            const url = `/musica/${emozione}/${emozione}_${String(i).padStart(2, '0')}.wav`;
            try {
                const buf = await this._carica(url);
                const d = this._densitaAttacchi(buf);
                if (d < minimo) { minimo = d; scelta = buf; }
            } catch (_) { /* variazione mancante: si passa oltre */ }
        }
        if (!scelta) throw new Error(`nessuna traccia per ${emozione}`);
        this._rade.set(emozione, scelta);
        return scelta;
    }

    async handle(msg) {
        const { azione, sorgente: nome, emozione, fade, volume, durata, val } = msg;
        const s = this._sorgenti[nome];
        if (!s) return;

        if (azione === 'play') {
            await this._ensure();
            this._stop(nome);
            const morbido = !!msg.morbido;
            try {
                const buf = morbido
                    ? await this._piuRada(emozione)
                    : await this._carica(`/musica/${emozione}/${emozione}_`
                        + Math.floor(Math.random() * 4).toString().padStart(2, '0') + '.wav');
                s.gainVol  = this.ctx.createGain();
                s.gainAtt  = this.ctx.createGain();
                s.gainVoce = this.ctx.createGain();
                s.gainVol.gain.value = 0;
                s.gainAtt.gain.value = 1;
                // se la voce sta gia' parlando, la sorgente che entra adesso
                // entra gia' abbassata invece di coprirla
                s.gainVoce.gain.value = this._voceInCorso ? this._voceAtt : 1;
                s.gainVol.connect(s.gainAtt).connect(s.gainVoce).connect(this._masterGain);
                s.node = this.ctx.createBufferSource();
                s.node.buffer = buf;
                s.node.loop = true;
                if (morbido) {
                    // La voce del tappeto: piu' grave, piu' rada, con attacchi
                    // piu' lenti. Non e' un time-stretch — velocita' e altezza
                    // scendono INSIEME, ed e' proprio quello che serve: con una
                    // sola operazione le note si abbassano, gli attacchi si
                    // diradano nel tempo e i transienti si allungano.
                    s.node.playbackRate.value = RALLENTAMENTO;
                    // Poi si smorzano le alte, dove vive lo schiocco del
                    // martelletto: senza, le note colpiscono invece di entrare.
                    s.filtro = this.ctx.createBiquadFilter();
                    s.filtro.type = 'lowpass';
                    s.filtro.frequency.value = TAGLIO_ALTE;
                    s.filtro.Q.value = 0.5;
                    s.node.connect(s.filtro).connect(s.gainVol);
                } else {
                    s.node.connect(s.gainVol);
                }
                s.node.start();
                s.volume = volume ?? 1;
                const t = this.ctx.currentTime;
                s.gainVol.gain.setValueAtTime(0, t);
                s.gainVol.gain.linearRampToValueAtTime(s.volume, t + (fade || 0.1));
            } catch (e) {
                console.warn('audio play error:', e);
            }
        } else if (azione === 'volume') {
            if (!s.gainVol) return;
            s.volume = volume;
            const t = this.ctx.currentTime;
            s.gainVol.gain.cancelScheduledValues(t);
            s.gainVol.gain.setValueAtTime(s.gainVol.gain.value, t);
            s.gainVol.gain.linearRampToValueAtTime(volume, t + (fade || 0.1));
        } else if (azione === 'fade_out') {
            if (!s.gainVol) return;
            const t = this.ctx.currentTime;
            s.gainVol.gain.cancelScheduledValues(t);
            s.gainVol.gain.setValueAtTime(s.gainVol.gain.value, t);
            s.gainVol.gain.linearRampToValueAtTime(0, t + (durata || 1));
        } else if (azione === 'ferma') {
            this._stop(nome);
        } else if (azione === 'attenua') {
            if (!s.gainAtt) return;
            const t = this.ctx.currentTime;
            s.gainAtt.gain.cancelScheduledValues(t);
            s.gainAtt.gain.setValueAtTime(s.gainAtt.gain.value, t);
            s.gainAtt.gain.linearRampToValueAtTime(val, t + (fade || 0.1));
        }
    }

    /**
     * La guida legge una frase. La clip arriva gia' sintetizzata dalla cache
     * del backend — la stessa che usa la versione desktop.
     */
    async voce(msg) {
        await this._ensure();
        this.zittisci();
        this._voceAtt = msg.attenuazione ?? 0.35;
        try {
            const buf = await this._carica(msg.url);
            const g = this.ctx.createGain();
            g.gain.value = msg.volume ?? 0.75;
            const n = this.ctx.createBufferSource();
            n.buffer = buf;
            n.connect(g).connect(this._masterGain);
            n.onended = () => { if (this._voceNode === n) this._rialzaDopoVoce(); };
            this._voceNode = n;
            this._voceInCorso = true;
            this._duckVoce(this._voceAtt, 0.25);
            n.start();
        } catch (e) {
            console.warn('voce:', e);
            this._rialzaDopoVoce();
        }
    }

    /** Tronca la clip in corso: si fa prima di accendere il microfono. */
    zittisci() {
        if (this._voceNode) {
            try { this._voceNode.stop(); } catch (_) {}
            this._voceNode = null;
        }
        this._rialzaDopoVoce();
    }

    _rialzaDopoVoce() {
        this._voceNode = null;
        this._voceInCorso = false;
        this._duckVoce(1, 0.5);
    }

    _duckVoce(valore, tempo) {
        if (!this.ctx) return;
        for (const nome of ['principale', 'tappeto']) {
            const s = this._sorgenti[nome];
            if (!s.gainVoce) continue;
            const t = this.ctx.currentTime;
            s.gainVoce.gain.cancelScheduledValues(t);
            s.gainVoce.gain.setValueAtTime(s.gainVoce.gain.value, t);
            s.gainVoce.gain.linearRampToValueAtTime(valore, t + tempo);
        }
    }

    stacco(chiusura, discesa, respiro, ritorno) {
        // Abbassa entrambe le sorgenti, suona la campanella, le rialza
        for (const nome of ['principale', 'tappeto']) {
            const s = this._sorgenti[nome];
            if (!s.gainAtt || !this.ctx) continue;
            const t = this.ctx.currentTime;
            s.gainAtt.gain.cancelScheduledValues(t);
            s.gainAtt.gain.setValueAtTime(s.gainAtt.gain.value, t);
            s.gainAtt.gain.linearRampToValueAtTime(0, t + discesa);
            s.gainAtt.gain.setValueAtTime(0, t + discesa + respiro);
            s.gainAtt.gain.linearRampToValueAtTime(1, t + discesa + respiro + ritorno);
        }
        // Campana sintetizzata
        this._campana(chiusura, discesa);
    }

    staccoAnnulla() {
        for (const nome of ['principale', 'tappeto']) {
            const s = this._sorgenti[nome];
            if (!s.gainAtt || !this.ctx) continue;
            const t = this.ctx.currentTime;
            s.gainAtt.gain.cancelScheduledValues(t);
            s.gainAtt.gain.setValueAtTime(s.gainAtt.gain.value, t);
            s.gainAtt.gain.linearRampToValueAtTime(1, t + 0.3);
        }
    }

    // Le stesse parziali di visuals/campanella.py: rapporto, peso, e in quanti
    // secondi svanisce. I rapporti sono quelli di una ciotola cantante — NON
    // sono multipli interi, ed e' quell'irregolarita' che l'orecchio riconosce
    // come "percosso" invece che "suonato". Le acute si spengono per prime,
    // cosi' il suono comincia brillante e diventa scuro mentre svanisce: se
    // svanissero tutte insieme si sentirebbe un accordo d'organo.
    static get PARZIALI() {
        return [[1.00, 1.00, 3.20], [2.71, 0.55, 1.80],
                [5.18, 0.28, 1.00], [8.35, 0.12, 0.55]];
    }

    _campana(chiusura, ritardo = 2.2) {
        if (!this.ctx) return;
        // Frequenza fondamentale: la grave per chiusura, una quinta sopra per
        // apertura. La quinta giusta e' l'intervallo piu' consonante dopo
        // l'ottava: con qualunque tonalita' del tappeto non litiga.
        const freq = chiusura ? 220 : 330;
        const BATTIMENTO = 0.9;   // Hz di scarto fra le due meta' di ogni parziale
        const ATTACCO = 0.012;    // senza salita morbida si sentirebbe un click
        const t0 = this.ctx.currentTime + ritardo;

        for (const [mult, peso, decadimento] of AudioManager.PARZIALI) {
            // Una ciotola non e' mai perfettamente simmetrica, quindi ogni modo
            // di vibrazione si sdoppia in due frequenze vicinissime: le due onde
            // vanno a tempo e poi in opposizione, e il volume ondeggia. E' quel
            // respiro che fa sembrare il suono vivo invece che stampato.
            const battito = BATTIMENTO * mult;
            for (const scarto of [-battito / 2, battito / 2]) {
                const osc  = this.ctx.createOscillator();
                const gain = this.ctx.createGain();
                osc.type = 'sine';
                osc.frequency.value = freq * mult + scarto;
                const picco = peso * 0.06 / 2;   // due oscillatori per parziale
                gain.gain.setValueAtTime(0.0001, t0);
                gain.gain.linearRampToValueAtTime(picco, t0 + ATTACCO);
                gain.gain.exponentialRampToValueAtTime(0.0001, t0 + decadimento);
                osc.connect(gain).connect(this.ctx.destination);
                osc.start(t0);
                osc.stop(t0 + decadimento + 0.1);
            }
        }
    }

    _stop(nome) {
        const s = this._sorgenti[nome];
        if (s.node) { try { s.node.stop(); } catch (_) {} s.node = null; }
        if (s.filtro) { try { s.filtro.disconnect(); } catch (_) {} s.filtro = null; }
        s.gainVoce = null;
    }

    // ---- registrazione microfono ----
    async apriMicrofono() {
        if (this._micStream) return;
        try {
            this._micStream = await navigator.mediaDevices.getUserMedia({ audio: true });
        } catch (e) {
            console.warn('microfono non disponibile:', e);
        }
    }

    async inizia() {
        if (this._recorder?.state === 'recording') return;
        try {
            if (!this._micStream) {
                this._micStream = await navigator.mediaDevices.getUserMedia({ audio: true });
            }
            const stream = this._micStream;
            this._audioChunks = [];
            const opts = MediaRecorder.isTypeSupported('audio/webm;codecs=opus')
                ? { mimeType: 'audio/webm;codecs=opus' }
                : undefined;
            this._recorder = new MediaRecorder(stream, opts);
            this._recorder.ondataavailable = e => { if (e.data.size > 0) this._audioChunks.push(e.data); };
            this._recorder.onstop = () => {
                const blob = new Blob(this._audioChunks, { type: 'audio/webm' });
                blob.arrayBuffer().then(buf => {
                    if (ws && ws.readyState === WebSocket.OPEN) {
                        ws.send(buf);
                    }
                });
            };
            this._recorder.start();
        } catch (e) {
            console.warn('microfono non disponibile:', e);
        }
    }

    ferma() {
        if (this._recorder && this._recorder.state !== 'inactive') {
            this._recorder.stop();
        }
    }
}

const audio = new AudioManager();

// Trascrizione live durante la fase ascolto (occhi chiusi)
let _ascoltoRec     = null;
let _ascoltoAttivo  = false;
let _ascoltoBase    = '';
let _ascoltoMotivo  = null;   // 'racconto' | 'riflessione'

function _iniziaAscoltoVisivo() {
    if (_ascoltoAttivo) return;
    _ascoltoAttivo = true;
    _ascoltoBase   = '';
    const testoEl  = document.getElementById('testo-sessione-testo');
    if (testoEl) testoEl.textContent = '';
    document.getElementById('testo-sessione')?.classList.add('visibile');

    const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SR) return;

    _ascoltoRec = new SR();
    _ascoltoRec.lang = 'en-US';
    _ascoltoRec.continuous = true;
    _ascoltoRec.interimResults = true;
    _ascoltoRec.onresult = ev => {
        let interim = '';
        for (let i = ev.resultIndex; i < ev.results.length; i++) {
            if (ev.results[i].isFinal) _ascoltoBase += ev.results[i][0].transcript;
            else interim = ev.results[i][0].transcript;
        }
        if (testoEl) testoEl.textContent = (_ascoltoBase + interim).trim();
    };
    _ascoltoRec.onend = () => {
        if (_ascoltoAttivo) {
            try { _ascoltoRec?.start(); } catch (_) {}
        }
    };
    _ascoltoRec.onerror = () => { /* Whisper fa da backup */ };

    try { _ascoltoRec.start(); } catch (_) {}
}

function _fermaAscoltoVisivo() {
    _ascoltoAttivo = false;
    if (_ascoltoRec) {
        try { _ascoltoRec.stop(); } catch (_) {}
        _ascoltoRec = null;
    }
    return document.getElementById('testo-sessione-testo')?.textContent?.trim() || '';
}

async function _avviaAscolto() {
    if (_ascoltoAttivo) return;
    _iniziaAscoltoVisivo();
    try { await audio.apriMicrofono(); } catch (_) {}
    try { await audio.inizia(); } catch (e) {
        console.warn('registrazione audio:', e);
    }
}

function _inviaInizia() {
    if (!ws || ws.readyState !== WebSocket.OPEN) return;
    ws.send(JSON.stringify({
        tipo:    'inizia',
        profilo: _profiloUtente || {},
    }));
}

function _mostraBtnFineRiflessione() {
    const el = document.getElementById('ui-riflessione');
    if (!el) return;
    el.classList.remove('nascosto');
    el.classList.add('visibile');
}

function _nascondiBtnFineRiflessione() {
    const el = document.getElementById('ui-riflessione');
    if (!el) return;
    el.classList.remove('visibile');
    el.classList.add('nascosto');
}

function _apriRiflessioneInEsperienza() {
    if (_inRiflessione) return;
    _inRiflessione = true;
    _riflessioneCompletata = false;
    _postMostrato = true;
    _ascoltoMotivo = 'riflessione';

    _durataSessione = Math.round((Date.now() - _tInizio) / 1000 / 60);
    _seriePre       = _analizzatore.serie();
    _emozionePre    = _analizzatore.report();
    _analizzatore.ferma();
    _tInizio = null;

    _analizzatorePost = new AnalizzatoreEmozioni();
    _analizzatorePost.inizia();
    _tInizioPost = true;

    stato.textContent = 'come ti senti adesso?';
    _mostraBtnFineRiflessione();
}

async function _concludiRiflessione() {
    if (!_inRiflessione || _riflessioneCompletata) return;
    _riflessioneCompletata = true;
    _nascondiBtnFineRiflessione();
    const testo = _fermaAscoltoVisivo();
    _ascoltoMotivo = null;
    audio.ferma();
    await _completaSessione(testo);
}

function _nascondiOverlayEsperienza() {
    document.getElementById('panel-risultati')?.classList.remove('visibile');
    _nascondiBtnFineRiflessione();
    _inRiflessione = false;
    _riflessioneCompletata = false;
    _ascoltoMotivo = null;
}

// ------------------------------------------------------------------ WebSocket
function connect() {
    if (ws && (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING)) {
        return;
    }
    stato.textContent = 'connessione...';
    ws = new WebSocket(WS_URL);

    ws.onopen = () => {
        stato.textContent = 'connesso';
        if (_pendingInizia) {
            _inviaInizia();
            _pendingInizia = false;
        }
    };

    ws.onmessage = async (ev) => {
        // I messaggi audio arrivano come Blob/ArrayBuffer, non JSON
        if (typeof ev.data !== 'string') return;

        let msg;
        try { msg = JSON.parse(ev.data); }
        catch (e) { console.warn('ws: messaggio non-JSON ignorato'); return; }

        const { tipo } = msg;
        console.log('ws ←', tipo, msg.scena || msg.azione || '');

        if (tipo === 'pronto') {
            if (!_sessioneIniziata) {
                _resetUiIngresso();
                ui.classList.remove('nascosto');
            }
            stato.textContent = 'pronto';

        } else if (!_sessioneIniziata) {
            return;

        } else if (tipo === 'prepara') {
            const t0 = performance.now();
            logica.prepara_testi(msg.frasi, (frase, n) => campionaTesto(frase, n));
            console.log(`prepara: ${msg.frasi.length} scritte in ${(performance.now()-t0).toFixed(0)}ms`);

        } else if (tipo === 'prepara_mandala') {
            logica.prepara_mandala(msg.petali, msg.anelli, msg.tonalita, msg.seed, msg.emozione);

        } else if (tipo === 'tinta') {
            // la tinta personale esiste da adesso; quanta se ne veda lo dice
            // tinta_forza, che arriva fase per fase
            logica.tinta(msg.tonalita, msg.emozione);

        } else if (tipo === 'tinta_forza') {
            logica.tintaForza(msg.valore, msg.durata);

        } else if (tipo === 'vai_a') {
            logica.vai_a(msg.scena, msg.testo, msg.durata);
            // Accende lo schermo al primo evento visivo (se ancora buio)
            if (renderer && renderer._t_accendi === null && renderer._post) {
                renderer.accendi(3.0, performance.now() / 1000);
            }

        } else if (tipo === 'azzera') {
            logica.azzera();

        } else if (tipo === 'buio') {
            renderer.buio();

        } else if (tipo === 'accendi') {
            renderer.accendi(msg.durata, performance.now() / 1000);

        } else if (tipo === 'musica') {
            await audio.handle(msg);

        } else if (tipo === 'voce') {
            if (msg.azione === 'di') await audio.voce(msg);
            else audio.zittisci();

        } else if (tipo === 'stacco') {
            audio.stacco(msg.chiusura, msg.discesa, msg.respiro, msg.ritorno);

        } else if (tipo === 'stacco_annulla') {
            audio.staccoAnnulla();

        } else if (tipo === 'ascolto') {
            if (msg.azione === 'apri') {
                await audio.apriMicrofono();
            } else if (msg.azione === 'inizia') {
                if (!_inRiflessione) _ascoltoMotivo = 'racconto';
                await _avviaAscolto();
            } else if (msg.azione === 'ferma') {
                const motivo = _ascoltoMotivo || 'racconto';
                const testo  = _fermaAscoltoVisivo();
                _ascoltoMotivo = null;
                audio.ferma();
                if (motivo === 'riflessione') {
                    if (!_riflessioneCompletata) {
                        _riflessioneCompletata = true;
                        _nascondiBtnFineRiflessione();
                        await _completaSessione(testo);
                    }
                } else {
                    _testoSessione = testo;
                    if (testo && ws?.readyState === WebSocket.OPEN) {
                        ws.send(JSON.stringify({
                            tipo:    'racconto',
                            testo,
                            profilo: _profiloUtente || {},
                        }));
                    }
                }
            }

        } else if (tipo === 'ui') {
            if (msg.fase === 'riflessione' && msg.azione === 'apri') {
                _apriRiflessioneInEsperienza();
                await _avviaAscolto();
            } else if (msg.fase === 'nascondi') {
                _nascondiOverlayEsperienza();
            }

        } else if (tipo === 'fine') {
            _nascondiOverlayEsperienza();
            _esperienzaFinita = true;
            stato.textContent = 'a presto';
        }
    };

    ws.onclose = () => {
        stato.textContent = 'disconnesso';
        if (_sessioneIniziata && !_esperienzaFinita) {
            setTimeout(connect, 2000);
        }
    };
    ws.onerror = () => ws.close();
}

// ------------------------------------------------------------------ face tracking
async function initFaceTracking() {
    stato.textContent = 'carico MediaPipe...';
    const vision = await FilesetResolver.forVisionTasks(
        'https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@0.10.14/wasm'
    );
    faceLandmarker = await FaceLandmarker.createFromOptions(vision, {
        baseOptions: {
            modelAssetPath:
                'https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task',
            delegate: 'GPU',
        },
        runningMode: 'VIDEO',
        numFaces: 1,
        outputFaceBlendshapes: true,   // abilita le 52 blend shapes per analisi emotiva
    });

    // Webcam (nascosta: l'anteprima non serve, le coordinate sì)
    video = document.getElementById('video');
    try {
        const stream = await navigator.mediaDevices.getUserMedia({ video: true, audio: false });
        video.srcObject = stream;
        await new Promise(res => { video.onloadedmetadata = res; });
        await video.play();
    } catch (e) {
        console.warn('webcam non disponibile:', e);
    }
    stato.textContent = 'pronto';
}

// ------------------------------------------------------------------ loop
let _lastSend = 0;
const SEND_INTERVAL = 1 / 30; // 30fps verso il server

function loop(timestamp) {
    requestAnimationFrame(loop);
    const ora = timestamp / 1000;

    // Aggiorna i landmark del viso
    if (faceLandmarker && video && video.readyState >= 2) {
        try {
            const res = faceLandmarker.detectForVideo(video, timestamp);
            if (res.faceLandmarks.length > 0) {
                landmarks = res.faceLandmarks[0];
                // Salva blend shapes per l'analisi emotiva
                if (res.faceBlendshapes?.length > 0) {
                    blendshapes = res.faceBlendshapes[0].categories;
                    if (_tInizio)      _analizzatore.aggiorna(blendshapes);
                    if (_tInizioPost)  _analizzatorePost?.aggiorna(blendshapes);
                }
                // Manda al server ~30fps
                if (ws && ws.readyState === WebSocket.OPEN && ora - _lastSend > SEND_INTERVAL) {
                    _lastSend = ora;
                    ws.send(JSON.stringify({
                        tipo: 'frame',
                        punti: landmarks.map(p => [p.x, p.y, p.z]),
                    }));
                }
            }
        } catch (_) {}
    }

    // Aggiorna la logica delle particelle e disegna
    if (logica && renderer) {
        const { posizioni, colori, sfondo } = logica.aggiorna(landmarks, ora);
        renderer.aggiorna(posizioni, colori);
        renderer.sfondo(sfondo);
        renderer.render(ora);
    }
}

// ------------------------------------------------------------------ avvio
async function init() {
    const canvas = document.getElementById('canvas');

    renderer = new RendererParticelle(canvas);
    logica   = new LogicaParticelle();
    await logica.init();

    await initFaceTracking();
    _mostraUiIngresso();

    requestAnimationFrame(loop);
}

function _mostraUiIngresso() {
    _resetUiIngresso();
    ui.classList.remove('nascosto');
    stato.textContent = 'pronto';
}

// ------------------------------------------------------------------ Firebase auth
const loginOverlay   = document.getElementById('login-overlay');
const profiloOverlay = document.getElementById('profilo-overlay');
const ctrlItemProfilo = document.getElementById('ctrl-item-profilo');
const utenteNome     = document.getElementById('utente-nome');
const utenteAvatar   = document.getElementById('utente-avatar');
const utenteAvatarFallback = document.getElementById('utente-avatar-fallback');
const loginErrore    = document.getElementById('login-errore');
const loginOk        = document.getElementById('login-ok');
const utenteFlyout   = document.getElementById('utente-flyout');
const volumeFlyout   = document.getElementById('volume-flyout');

// Inizializza Firebase (recupera config dal server) poi registra il listener auth
const _firebaseConfigurato = await inizializza();

onAuth(async utente => {
    _utenteCorrente = utente;
    if (utente) {
        // Nascondi login overlay
        loginOverlay.classList.add('nascosto');
        utenteNome.textContent = utente.displayName || utente.email || '';
        if (utente.photoURL) {
            utenteAvatar.src = utente.photoURL;
            utenteAvatar.style.display = 'block';
            if (utenteAvatarFallback) utenteAvatarFallback.style.display = 'none';
        } else {
            utenteAvatar.style.display = 'none';
            if (utenteAvatarFallback) utenteAvatarFallback.style.display = 'block';
        }
        ctrlItemProfilo?.classList.add('visibile');

        // Controlla se il profilo esiste già su Firestore (primo accesso?)
        try { _profiloUtente = await caricaProfilo(utente.uid); }
        catch (_) { _profiloUtente = null; }

        if (!_profiloUtente) {
            // Primo accesso: mostra il form profilo
            profiloOverlay?.classList.add('visibile');
        } else {
            // Profilo già esistente: avvia direttamente
            profiloOverlay?.classList.remove('visibile');
            if (!renderer) init();
        }
    } else {
        // Non loggato
        profiloOverlay?.classList.remove('visibile');
        if (_firebaseConfigurato) {
            loginOverlay.classList.remove('nascosto');
            ctrlItemProfilo?.classList.remove('visibile');
        } else {
            // Firebase non configurato: salta il login e avvia direttamente
            loginOverlay.classList.add('nascosto');
            if (!renderer) init();
        }
    }
});

document.getElementById('btn-google').addEventListener('click', async () => {
    if (loginErrore) loginErrore.textContent = '';
    if (loginOk)     loginOk.textContent     = '';
    // Sblocca AudioContext durante la user gesture del login
    try { await audio._ensure(); } catch (_) {}
    try {
        await loginGoogle();
    } catch (e) {
        console.warn('login error:', e);
        loginErrore.textContent = _messaggioErrore(e);
    }
});

document.getElementById('btn-logout').addEventListener('click', async () => {
    await logout();
});

// ------------------------------------------------------------------ form email/password
let _modalitaAuth   = 'accedi';   // 'accedi' | 'registrati'

// Tab switch
document.querySelectorAll('.login-tab').forEach(tab => {
    tab.addEventListener('click', () => {
        _modalitaAuth = tab.dataset.tab;
        document.querySelectorAll('.login-tab').forEach(t => t.classList.remove('attivo'));
        tab.classList.add('attivo');
        const isReg = _modalitaAuth === 'registrati';
        document.getElementById('auth-conferma').style.display = isReg ? 'block' : 'none';
        document.getElementById('link-reset').style.display    = isReg ? 'none'  : 'block';
        document.getElementById('btn-submit-auth').textContent = isReg ? 'Registrati' : 'Accedi';
        loginErrore.textContent = '';
        loginOk.textContent = '';
    });
});

// Submit (Accedi o Registrati)
document.getElementById('btn-submit-auth').addEventListener('click', async () => {
    loginErrore.textContent = '';
    loginOk.textContent = '';
    const email    = document.getElementById('auth-email').value.trim();
    const password = document.getElementById('auth-password').value;
    const conferma = document.getElementById('auth-conferma').value;

    if (!email || !password) { loginErrore.textContent = 'Inserisci email e password.'; return; }

    // Sblocca AudioContext durante la user gesture del login
    try { await audio._ensure(); } catch (_) {}

    try {
        if (_modalitaAuth === 'registrati') {
            if (password !== conferma) { loginErrore.textContent = 'Le password non coincidono.'; return; }
            if (password.length < 6)   { loginErrore.textContent = 'La password deve avere almeno 6 caratteri.'; return; }
            await registraEmail(email, password);
        } else {
            await loginEmail(email, password);
        }
    } catch (e) {
        loginErrore.textContent = _messaggioErrore(e);
    }
});

// Password dimenticata
document.getElementById('link-reset').addEventListener('click', async () => {
    loginErrore.textContent = '';
    loginOk.textContent = '';
    const email = document.getElementById('auth-email').value.trim();
    if (!email) { loginErrore.textContent = 'Inserisci la tua email sopra.'; return; }
    try {
        await resetPassword(email);
        loginOk.textContent = 'Email di recupero inviata. Controlla la posta.';
    } catch (e) {
        loginErrore.textContent = _messaggioErrore(e);
    }
});

// Invio con Enter nei campi
['auth-email','auth-password','auth-conferma'].forEach(id => {
    document.getElementById(id)?.addEventListener('keydown', e => {
        if (e.key === 'Enter') document.getElementById('btn-submit-auth')?.click();
    });
});

/** Traduce i codici di errore Firebase in messaggi leggibili. */
function _messaggioErrore(e) {
    const m = { 'auth/invalid-email': 'Email non valida.',
                'auth/user-not-found': 'Nessun account con questa email.',
                'auth/wrong-password': 'Password errata.',
                'auth/email-already-in-use': 'Email già registrata.',
                'auth/weak-password': 'Password troppo debole (min. 6 caratteri).',
                'auth/too-many-requests': 'Troppi tentativi. Riprova più tardi.',
                'auth/popup-closed-by-user': '' };
    return m[e.code] || e.message || 'Errore sconosciuto.';
}

// ------------------------------------------------------------------ form profilo (primo accesso)
let _sessoSelezionato = '';

document.querySelectorAll('.sesso-btn').forEach(btn => {
    btn.addEventListener('click', () => {
        document.querySelectorAll('.sesso-btn').forEach(b => b.classList.remove('selezionato'));
        btn.classList.add('selezionato');
        _sessoSelezionato = btn.dataset.val;
    });
});

document.getElementById('btn-profilo-salva').addEventListener('click', async () => {
    const profiloErrore = document.getElementById('profilo-errore');
    profiloErrore.textContent = '';

    const nome      = document.getElementById('profilo-nome').value.trim();
    const cognome   = document.getElementById('profilo-cognome').value.trim();
    const eta       = parseInt(document.getElementById('profilo-eta').value, 10);
    const obiettivo = document.getElementById('profilo-obiettivo').value.trim();

    if (!nome)                  { profiloErrore.textContent = 'Inserisci il tuo nome.'; return; }
    if (!_sessoSelezionato)     { profiloErrore.textContent = 'Seleziona il sesso.'; return; }
    if (!eta || eta < 10 || eta > 120) { profiloErrore.textContent = 'Inserisci un\'età valida.'; return; }
    if (!obiettivo)             { profiloErrore.textContent = 'Raccontaci cosa vuoi migliorare.'; return; }

    const profilo = { nome, cognome, eta, sesso: _sessoSelezionato, obiettivo };

    // Salva su Firestore se disponibile
    if (_utenteCorrente) await salvaProfilo(_utenteCorrente.uid, profilo);
    _profiloUtente = profilo;

    // Sblocca AudioContext qui — il click del profilo È la user gesture
    try { await audio._ensure(); } catch (_) {}

    // Nascondi il form e avvia l'esperienza
    profiloOverlay.classList.remove('visibile');
    if (!renderer) init();
});

// ------------------------------------------------------------------ UI ingresso (solo Inizia)
const uiStep1 = document.getElementById('ui-step1');

function _resetUiIngresso() {
    uiStep1?.classList.remove('nascosto');
    _nascondiBtnFineRiflessione();
    document.getElementById('testo-sessione')?.classList.remove('visibile');
    const testoEl = document.getElementById('testo-sessione-testo');
    if (testoEl) testoEl.textContent = '';
}

document.getElementById('inizia').addEventListener('click', async () => {
    _sessioneIniziata = true;
    _postMostrato = false;
    _esperienzaFinita = false;
    _inRiflessione = false;
    _riflessioneCompletata = false;
    _seriePre  = { valenza: [], arousal: [] };
    _seriePost = { valenza: [], arousal: [] };
    _testoSessione = '';
    _tInizio = Date.now();
    _analizzatore.inizia();
    ui.classList.add('nascosto');
    stato.textContent = 'esperienza in corso';
    try { await audio._ensure(); } catch (_) {}

    if (ws && ws.readyState === WebSocket.OPEN) {
        _inviaInizia();
    } else {
        _pendingInizia = true;
        connect();
    }
});

document.getElementById('btn-fine-riflessione')?.addEventListener('click', () => {
    _concludiRiflessione();
});

// ------------------------------------------------------------------ Flyout controlli sinistra
const ctrlItemProfiloEl = document.getElementById('ctrl-item-profilo');
const ctrlItemVolumeEl  = document.getElementById('ctrl-item-volume');

function _posizionaFlyout(btn, flyout) {
    if (!btn || !flyout) return;
    const r = btn.getBoundingClientRect();
    flyout.style.left = `${Math.round(r.right + 7)}px`;
    flyout.style.top  = `${Math.round(r.top + r.height / 2)}px`;
}

function _chiudiFlyout(...els) {
    for (const el of els) el?.classList.remove('aperto');
    ctrlItemProfiloEl?.classList.remove('aperto');
    ctrlItemVolumeEl?.classList.remove('aperto');
}
function _toggleFlyout(el, btn, itemEl, altro = null) {
    if (!el) return false;
    const apri = !el.classList.contains('aperto');
    if (altro) _chiudiFlyout(altro);
    el.classList.toggle('aperto', apri);
    itemEl?.classList.toggle('aperto', apri);
    if (apri) _posizionaFlyout(btn, el);
    return apri;
}

const btnProfiloToggle = document.getElementById('btn-profilo-toggle');
btnProfiloToggle?.addEventListener('click', e => {
    e.stopPropagation();
    const aperto = _toggleFlyout(utenteFlyout, btnProfiloToggle, ctrlItemProfiloEl, volumeFlyout);
    btnProfiloToggle.setAttribute('aria-expanded', aperto ? 'true' : 'false');
});

// Pulsante volume + slider
const volumeSlider = document.getElementById('volume-slider');
const btnMuto = document.getElementById('btn-muto');

btnMuto?.addEventListener('click', async e => {
    e.stopPropagation();
    try { await audio._ensure(); } catch (_) {}
    const aperto = _toggleFlyout(volumeFlyout, btnMuto, ctrlItemVolumeEl, utenteFlyout);
    btnMuto.setAttribute('aria-expanded', aperto ? 'true' : 'false');
});

window.addEventListener('resize', () => {
    if (utenteFlyout?.classList.contains('aperto')) _posizionaFlyout(btnProfiloToggle, utenteFlyout);
    if (volumeFlyout?.classList.contains('aperto')) _posizionaFlyout(btnMuto, volumeFlyout);
});

volumeSlider?.addEventListener('input', async () => {
    try { await audio._ensure(); } catch (_) {}
    audio.setMasterVolume(Number(volumeSlider.value) / 100);
    btnMuto?.classList.remove('attivo');
});

btnMuto?.addEventListener('dblclick', async e => {
    e.preventDefault();
    e.stopPropagation();
    try { await audio._ensure(); } catch (_) {}
    const muted = audio.toggleMute();
    btnMuto.classList.toggle('attivo', muted);
    btnMuto.title = muted ? 'Riattiva musica (doppio clic)' : 'Volume musica (doppio clic per muto)';
});

document.addEventListener('click', e => {
    if (e.target.closest('#controls-left')) return;
    _chiudiFlyout(utenteFlyout, volumeFlyout);
    btnProfiloToggle?.setAttribute('aria-expanded', 'false');
    btnMuto?.setAttribute('aria-expanded', 'false');
});

// Pulsante info / modal
const modalInfo = document.getElementById('modal-info');
document.getElementById('btn-info').addEventListener('click', () => {
    _chiudiFlyout(utenteFlyout, volumeFlyout);
    modalInfo.classList.add('visibile');
});
document.getElementById('modal-chiudi').addEventListener('click', () => {
    modalInfo.classList.remove('visibile');
});
modalInfo.addEventListener('click', e => {
    if (e.target === modalInfo) modalInfo.classList.remove('visibile');
});

// Calendario dal top-right
document.getElementById('btn-calendario-top')?.addEventListener('click', () => {
    _chiudiFlyout(utenteFlyout, volumeFlyout);
    apriCalendario();
});

// ------------------------------------------------------------------ Panel post-meditazione (riflessione via particelle + voce)

async function _completaSessione(riflessione) {
    _nascondiBtnFineRiflessione();
    if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ tipo: 'riflessione_post', testo: riflessione }));
    }

    _tInizioPost = false;
    _seriePost       = _analizzatorePost?.serie() || { valenza: [], arousal: [] };
    const emozionePost = _analizzatorePost?.report() || {};
    _analizzatorePost?.ferma();

    document.getElementById('testo-sessione')?.classList.remove('visibile');

    // Chiama Claude con dati pre+post
    const payload = {
        racconto:      _testoSessione.slice(0, 400),
        riflessione:   riflessione.slice(0, 400),
        durata_minuti: _durataSessione,
        emozioni:      _emozionePre || {},
        emozioni_post: emozionePost,
        profilo:       _profiloUtente || {},
    };

    let analisi = {};
    try {
        const r = await fetch('/analisi', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
        });
        ({ analisi } = await r.json());
    } catch (e) {
        console.warn('analisi: errore Claude', e);
    }

    // Salva su Firestore (serie + spiegazioni per il calendario)
    const testiRisultato = _testiRisultati(
        _emozionePre, emozionePost, _seriePre, _seriePost
    );
    const datiSessione = {
        racconto:            _testoSessione,
        riflessione_post:    riflessione,
        durata_minuti:       _durataSessione,
        emozioni_pre:        _emozionePre || {},
        emozioni_post:       emozionePost,
        serie_pre:           _seriePre,
        serie_post:          _seriePost,
        spiegazione_umore:   testiRisultato.spiegaUmore,
        spiegazione_energia: testiRisultato.spiegaEnergia,
        analisi_claude:      analisi,
        completata:          _durataSessione >= 2,
    };

    if (_utenteCorrente) {
        const id = await salvaSessioneGiornaliera(_utenteCorrente.uid, datiSessione);
        const oggi = new Date().toISOString().split('T')[0];
        if (!_calSessioni[oggi]) _calSessioni[oggi] = [];
        _calSessioni[oggi].unshift({ id: id || `local-${Date.now()}`, ...datiSessione, data_giorno: oggi });
    }

    // Mostra il pannello risultati con i grafici
    mostraRisultati(_emozionePre || {}, emozionePost, analisi, _seriePre, _seriePost);
    document.getElementById('panel-risultati').classList.add('visibile');
}

// ------------------------------------------------------------------ Grafici Chart.js
let _chartV, _chartA;

function _umoreInParole(v) {
    if (v > 0.3)  return 'Umore aperto e leggero';
    if (v > 0.1)  return 'Umore leggermente positivo';
    if (v < -0.3) return 'Umore chiuso o pensieroso';
    if (v < -0.1) return 'Umore un po\' cupo';
    return 'Umore neutro';
}

function _energiaInParole(a) {
    if (a > 0.65) return 'Molto attivo/a o in tensione';
    if (a > 0.4)  return 'Vigile, con un po\' di carica';
    if (a < 0.2)  return 'Rilassato/a e quieto/a';
    if (a < 0.35) return 'Abbastanza calmo/a';
    return 'Equilibrio tra calma e attenzione';
}

function _etichetteAsse(nPre, nPost) {
    const tot = nPre + nPost;
    const labels = new Array(tot).fill('');
    if (tot === 0) return labels;
    labels[0] = 'Inizio';
    if (nPre > 1) labels[nPre - 1] = 'Fine meditazione';
    if (nPost > 0 && nPre < tot) labels[nPre] = 'Dopo';
    if (tot > 1) labels[tot - 1] = 'Ora';
    return labels;
}

function _datiDueFasi(seriePre, seriePost) {
    const nPre  = seriePre.length;
    const nPost = seriePost.length;
    const pad   = (src, len, offset) => {
        const out = new Array(len).fill(null);
        for (let i = 0; i < src.length; i++) out[offset + i] = src[i];
        return out;
    };
    const len = nPre + nPost || 1;
    return {
        labels: _etichetteAsse(nPre, nPost),
        len,
        datasets: (valsPre, valsPost) => [
            {
                label: 'Durante la meditazione',
                data: pad(valsPre, len, 0),
                borderColor: 'rgba(120, 220, 160, 0.9)',
                backgroundColor: 'rgba(120, 220, 160, 0.12)',
                tension: 0.35,
                pointRadius: 0,
                pointHitRadius: 12,
                spanGaps: false,
            },
            {
                label: 'Dopo la riflessione',
                data: pad(valsPost, len, nPre),
                borderColor: 'rgba(255, 200, 100, 0.9)',
                backgroundColor: 'rgba(255, 200, 100, 0.10)',
                tension: 0.35,
                pointRadius: 0,
                pointHitRadius: 12,
                spanGaps: false,
            },
        ],
    };
}

function _spiegaUmore(pre, post, seriePre, seriePost) {
    const n = seriePre.length + seriePost.length;
    if (n < 3) {
        return 'Non abbiamo letto abbastanza dal volto per tracciare come ti sei sentito/a. Resta davanti alla webcam con buona luce.';
    }

    const vPre  = pre?.valenza_media ?? 0;
    const vPost = post?.valenza_media ?? vPre;
    const d     = vPost - vPre;
    const parti = [];

    if (pre?.arco_emotivo === 'migioramento') {
        parti.push('Durante la meditazione il volto ha mostrato un andamento verso stati più aperti.');
    } else if (pre?.arco_emotivo === 'peggioramento') {
        parti.push('Durante la meditazione il volto ha attraversato momenti più chiusi o pensierosi: può succedere quando emergono emozioni da elaborare.');
    }

    if (Math.abs(d) < 0.08) {
        parti.push('Dall\'inizio alla fine il tono emotivo è rimasto abbastanza stabile.');
    } else if (d > 0) {
        parti.push('Rispetto all\'inizio, ora sembri uscire con un umore più leggero e disponibile.');
    } else {
        parti.push('Rispetto all\'inizio, ora sembri un po\' più chiuso/a o pensieroso/a: non è un fallimento, a volte la meditazione porta in superficie cose difficili.');
    }

    if (seriePost.length > 2 && Math.abs(vPost - vPre) >= 0.08) {
        parti.push(vPost > vPre
            ? 'Anche nel momento dopo, il volto resta su un registro un po\' più sereno.'
            : 'Nel momento dopo la riflessione il volto resta ancora su un registro più introspettivo.');
    }

    return parti.join(' ');
}

function _spiegaEnergia(pre, post) {
    const n = (pre?.n_campioni || 0) + (post?.n_campioni || 0);
    if (n < 3) {
        return 'Non abbiamo abbastanza dati per descrivere come è cambiata la tua tensione nel tempo.';
    }

    const aPre  = pre?.arousal_medio ?? 0;
    const aPost = post?.arousal_medio ?? aPre;
    const d     = aPost - aPre;
    const parti = [];

    parti.push(`All\'inizio eri ${_energiaInParole(aPre).toLowerCase()}.`);

    if (Math.abs(d) < 0.08) {
        parti.push('Il livello di attivazione nel corpo è rimasto più o meno lo stesso per tutta la sessione.');
    } else if (d < -0.08) {
        parti.push('Col passare dei minuti sembri esserti sciolto/a: meno tensione, più rilassamento.');
    } else {
        parti.push('Col passare dei minuti il corpo è risultato più vigile o più in allerta, come dopo uno sforzo di attenzione.');
    }

    if (post?.n_campioni >= 3) {
        parti.push(`Dopo la riflessione risulti ${_energiaInParole(aPost).toLowerCase()}.`);
    }

    return parti.join(' ');
}

function _testiRisultati(pre, post, seriePre, seriePost) {
    const preV  = seriePre?.valenza  || [];
    const postV = seriePost?.valenza || [];
    return {
        spiegaUmore:   _spiegaUmore(pre, post, preV, postV),
        spiegaEnergia: _spiegaEnergia(pre, post),
    };
}

function _opzioniGrafico(tooltipFn) {
    return {
        responsive: true,
        maintainAspectRatio: false,
        interaction: { mode: 'index', intersect: false },
        plugins: {
            legend: {
                display: true,
                labels: { color: 'rgba(255,255,255,0.55)', boxWidth: 14, font: { size: 11 } },
            },
            tooltip: {
                callbacks: {
                    label: ctx => {
                        const v = ctx.parsed.y;
                        return v == null ? null : tooltipFn(v);
                    },
                },
            },
        },
        scales: {
            x: {
                ticks: { color: 'rgba(255,255,255,0.45)', font: { size: 10 }, maxRotation: 0 },
                grid: { color: 'rgba(255,255,255,0.06)' },
            },
            y: {
                ticks: { display: false },
                grid: { color: 'rgba(255,255,255,0.06)' },
            },
        },
    };
}

function _creaGraficiSuCanvas(canvasV, canvasA, seriePre, seriePost) {
    const preV  = seriePre?.valenza  || [];
    const postV = seriePost?.valenza || [];
    const preA  = seriePre?.arousal  || [];
    const postA = seriePost?.arousal || [];

    const baseV = _datiDueFasi(preV, postV);
    const baseA = _datiDueFasi(preA, postA);

    Chart.defaults.color = 'rgba(255,255,255,0.45)';

    const optsV = _opzioniGrafico(_umoreInParole);
    const optsA = _opzioniGrafico(_energiaInParole);

    const chartV = new Chart(canvasV, {
        type: 'line',
        data: { labels: baseV.labels, datasets: baseV.datasets(preV, postV) },
        options: {
            ...optsV,
            scales: {
                ...optsV.scales,
                y: { ...optsV.scales.y, min: -1, max: 1 },
            },
        },
    });

    const chartA = new Chart(canvasA, {
        type: 'line',
        data: { labels: baseA.labels, datasets: baseA.datasets(preA, postA) },
        options: {
            ...optsA,
            scales: {
                ...optsA.scales,
                y: { ...optsA.scales.y, min: 0, max: 1 },
            },
        },
    });

    return { chartV, chartA };
}

function mostraRisultati(pre, post, analisi, seriePre, seriePost) {
    if (_chartV) { _chartV.destroy(); _chartV = null; }
    if (_chartA) { _chartA.destroy(); _chartA = null; }

    const charts = _creaGraficiSuCanvas(
        document.getElementById('grafico-valence'),
        document.getElementById('grafico-arousal'),
        seriePre, seriePost,
    );
    _chartV = charts.chartV;
    _chartA = charts.chartA;

    const testi = _testiRisultati(pre, post, seriePre, seriePost);
    document.getElementById('spiega-valence').textContent = testi.spiegaUmore;
    document.getElementById('spiega-arousal').textContent = testi.spiegaEnergia;

    if (analisi?.interpretazione) {
        document.getElementById('risultati-testo').textContent = analisi.interpretazione;
        document.getElementById('risultati-analisi').style.display = 'block';
    } else {
        document.getElementById('risultati-analisi').style.display = 'none';
    }
}

function _distruggiGraficiCalendario() {
    for (const c of _calCharts) {
        try { c.destroy(); } catch (_) {}
    }
    _calCharts = [];
}

function _htmlRisultatoSessione(s, sid) {
    const testi = (s.spiegazione_umore && s.spiegazione_energia)
        ? { spiegaUmore: s.spiegazione_umore, spiegaEnergia: s.spiegazione_energia }
        : _testiRisultati(
            s.emozioni_pre, s.emozioni_post,
            s.serie_pre || { valenza: [], arousal: [] },
            s.serie_post || { valenza: [], arousal: [] },
        );
    const haSerie = (s.serie_pre?.valenza?.length || 0) + (s.serie_post?.valenza?.length || 0) >= 3;
    const dur = s.durata_minuti || '—';

    return `<div class="cal-sessione-item" data-sid="${sid}">
      <strong>${dur} minuti</strong>
      ${s.racconto ? `<div class="cal-racconto">"${s.racconto.slice(0, 100)}${s.racconto.length > 100 ? '…' : ''}"</div>` : ''}
      ${s.riflessione_post ? `<div class="cal-racconto" style="font-style:normal;opacity:0.85">Dopo: "${s.riflessione_post.slice(0, 100)}${s.riflessione_post.length > 100 ? '…' : ''}"</div>` : ''}
      ${haSerie ? `
        <div class="grafico-wrap">
          <h4>Come ti sei sentito/a</h4>
          <canvas id="cal-v-${sid}" height="90"></canvas>
          <p class="grafico-spiegazione">${testi.spiegaUmore}</p>
        </div>
        <div class="grafico-wrap">
          <h4>Quanto eri attivo/a o in tensione</h4>
          <canvas id="cal-a-${sid}" height="90"></canvas>
          <p class="grafico-spiegazione">${testi.spiegaEnergia}</p>
        </div>` : `
        <p class="grafico-spiegazione">${testi.spiegaUmore}</p>
        <p class="grafico-spiegazione">${testi.spiegaEnergia}</p>`}
      ${s.analisi_claude?.interpretazione ? `
        <div class="cal-sintesi">
          <strong>In sintesi</strong>
          ${s.analisi_claude.interpretazione}
        </div>` : ''}
    </div>`;
}

function _renderGraficiCalendario(sessioni) {
    for (const s of sessioni) {
        const sid = s.id || 'x';
        const n = (s.serie_pre?.valenza?.length || 0) + (s.serie_post?.valenza?.length || 0);
        if (n < 3) continue;
        const cv = document.getElementById(`cal-v-${sid}`);
        const ca = document.getElementById(`cal-a-${sid}`);
        if (!cv || !ca) continue;
        const { chartV, chartA } = _creaGraficiSuCanvas(
            cv, ca, s.serie_pre || { valenza: [], arousal: [] }, s.serie_post || { valenza: [], arousal: [] },
        );
        _calCharts.push(chartV, chartA);
    }
}

document.getElementById('btn-chiudi-risultati').addEventListener('click', () => {
    document.getElementById('panel-risultati').classList.remove('visibile');
    if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ tipo: 'risultati_visti' }));
    }
});
document.getElementById('btn-calendario-apri').addEventListener('click', () => {
    document.getElementById('panel-risultati').classList.remove('visibile');
    apriCalendario();
});

// ------------------------------------------------------------------ Calendario
async function apriCalendario() {
    if (_utenteCorrente) {
        try { _calSessioni = await caricaSessioniCalendario(_utenteCorrente.uid); }
        catch (_) { _calSessioni = {}; }
    }
    renderCalendario();
    document.getElementById('modal-calendario').classList.add('visibile');
}

function renderCalendario() {
    const anno = _calMese.getFullYear();
    const mese = _calMese.getMonth();
    document.getElementById('cal-titolo-mese').textContent =
        new Date(anno, mese, 1).toLocaleDateString('it-IT', { month: 'long', year: 'numeric' });

    const grid  = document.getElementById('cal-grid');
    grid.innerHTML = '';

    const primoGiorno  = (new Date(anno, mese, 1).getDay() + 6) % 7; // lun=0
    const ultimoGiorno = new Date(anno, mese + 1, 0).getDate();
    const oggiStr      = new Date().toISOString().split('T')[0];

    for (let i = 0; i < primoGiorno; i++) {
        grid.appendChild(document.createElement('div')).className = 'cal-cell';
    }
    for (let g = 1; g <= ultimoGiorno; g++) {
        const data = `${anno}-${String(mese + 1).padStart(2,'0')}-${String(g).padStart(2,'0')}`;
        const cell = document.createElement('div');
        cell.className = 'cal-cell';
        cell.textContent = g;
        if (data === oggiStr) cell.classList.add('oggi');
        if (_calSessioni[data]) {
            cell.classList.add('ha-sessione');
            cell.title = `${_calSessioni[data].length} sessione/i`;
            cell.addEventListener('click', () => mostraDettaglioGiorno(data, cell));
        }
        grid.appendChild(cell);
    }
    document.getElementById('cal-dettaglio').innerHTML = '';
    _distruggiGraficiCalendario();
}

function mostraDettaglioGiorno(data, cell) {
    document.querySelectorAll('.cal-cell.selezionato').forEach(c => c.classList.remove('selezionato'));
    cell.classList.add('selezionato');

    _distruggiGraficiCalendario();

    const sessioni = _calSessioni[data] || [];
    const div = document.getElementById('cal-dettaglio');
    const fmt = new Date(data + 'T12:00:00').toLocaleDateString('it-IT',
        { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' });

    if (!sessioni.length) {
        div.innerHTML = `<div style="color:rgba(255,255,255,0.55); font-size:0.75rem; margin-bottom:0.75rem; letter-spacing:0.06em; text-transform:uppercase">${fmt}</div>
            <p>Nessuna sessione registrata per questo giorno.</p>`;
        return;
    }

    div.innerHTML = `<div style="color:rgba(255,255,255,0.55); font-size:0.75rem; margin-bottom:0.75rem; letter-spacing:0.06em; text-transform:uppercase">${fmt}</div>` +
        sessioni.map(s => _htmlRisultatoSessione(s, s.id || `s${Math.random().toString(36).slice(2, 8)}`)).join('');

    _renderGraficiCalendario(sessioni);
}

document.getElementById('cal-prec').addEventListener('click', () => {
    _calMese = new Date(_calMese.getFullYear(), _calMese.getMonth() - 1, 1);
    renderCalendario();
});
document.getElementById('cal-succ').addEventListener('click', () => {
    _calMese = new Date(_calMese.getFullYear(), _calMese.getMonth() + 1, 1);
    renderCalendario();
});
document.getElementById('btn-chiudi-calendario').addEventListener('click', () => {
    _distruggiGraficiCalendario();
    document.getElementById('modal-calendario').classList.remove('visibile');
});

// ------------------------------------------------------------------ Helper: Web Speech API
function _initVoice(btnMic, textarea, statoEl, onFine) {
    if (!btnMic || !textarea) return;
    const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SR) { btnMic.style.display = 'none'; return; }

    const rec = new SR();
    rec.lang = 'en-US';
    rec.continuous = true;
    rec.interimResults = true;
    let base = '';

    rec.onresult = ev => {
        let interim = '';
        for (let i = ev.resultIndex; i < ev.results.length; i++) {
            if (ev.results[i].isFinal) base += ev.results[i][0].transcript;
            else interim = ev.results[i][0].transcript;
        }
        textarea.value = base + interim;
    };
    rec.onend = () => {
        btnMic.classList.remove('rec');
        if (statoEl) statoEl.textContent = 'pronto';
        onFine?.();
    };
    rec.onerror = () => {
        btnMic.classList.remove('rec');
        if (statoEl) statoEl.textContent = 'errore microfono';
    };

    btnMic.addEventListener('click', () => {
        if (btnMic.classList.contains('rec')) {
            rec.stop();
        } else {
            base = textarea.value;
            try {
                rec.start();
                btnMic.classList.add('rec');
                if (statoEl) statoEl.textContent = 'ascolto…';
            } catch (_) {}
        }
    });
}
