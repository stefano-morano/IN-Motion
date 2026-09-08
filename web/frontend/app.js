/**
 * app.js — browser-side orchestrator.
 *
 * Connects WebSocket, MediaPipe face tracking, Web Audio API
 * and the Three.js renderer in a single animation loop.
 */

import { FaceLandmarker, FilesetResolver }
    from 'https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@0.10.14/vision_bundle.mjs';
import { ParticleRenderer } from './renderer/particelle.js';
import { ParticleLogic } from './renderer/logica.js';
import { sampleText }      from './renderer/testo_canvas.js';
import { EmotionAnalyzer } from './renderer/emozioni.js';
import { loginGoogle, logout, onAuth, saveSession, initialize,
         loginEmail, registerEmail, resetPassword,
         loadProfile, saveProfile,
         saveDailySession, loadCalendarSessions } from './firebase.js';

// ------------------------------------------------------------------ global state
let ws;
let renderer;
let logica;
let faceLandmarker;
let video;
let landmarks    = null;
let blendshapes  = null;                       // MediaPipe face blend shapes
let _currentUser = null;
let _startTime        = null;
let _sessionText  = '';
let _userProfile  = null;                    // profile data (name, age, goal…)
const _analyzer = new EmotionAnalyzer();

// Data for charts and history
let _emotionPre    = null;   // facial report pre-meditation
let _seriesPre       = { valenza: [], arousal: [] };
let _seriesPost      = { valenza: [], arousal: [] };
let _sessionDuration = 0;
let _analyzerPost = null; // analyzer for the post phase
let _postPhaseActive    = false;  // true during the post reflection
let _calSessions    = {};     // { 'YYYY-MM-DD': [{...}] } for the calendar
let _calMonth        = new Date();
let _calCharts      = [];       // Chart.js instances in calendar detail
let _sessionStarted = false;
let _pendingStart    = false;
let _postShown     = false;
let _experienceDone = false;
let _wsGeneration   = 0;   // bumps on intentional restart so stale onclose is ignored
let _inReflection    = false;
let _reflectionDone = false;

const WS_URL = `ws://${location.host}/ws`;
const statusEl = document.getElementById('status');
const ui    = document.getElementById('ui');

// ------------------------------------------------------------------ audio
// ------------------------------------------------------------------ the bed
// Aligned with visuals/musica.py. The music engine would generate a version
// like this directly (lower polyphony and rhythmic intensity are enough), but
// here the library is already rendered: we work on the audio.
const RALLENTAMENTO = 0.40;
const TAGLIO_ALTE = 2600.0;

class AudioManager {
    constructor() {
        this.ctx = null;
        this._masterVolume = 1;
        this._muted = false;
        this._sorgenti = {
            // Three gains per source, not one: they multiply together and
            // answer three different questions.
            //   gainVol   how loud in this scene?               (state machine)
            //   gainAtt   how much to duck for the bell?        (stacco)
            //   gainVoce  how much to duck because someone speaks? (voice)
            // With a single number they would overwrite each other: stacco
            // would bring back up music that voice wanted low.
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

    async _loadAudio(url) {
        if (this._cache.has(url)) return this._cache.get(url);
        const r   = await fetch(url);
        const arr = await r.arrayBuffer();
        const buf = await this.ctx.decodeAudioData(arr);
        this._cache.set(url, buf);
        return buf;
    }

    /**
     * How many attacks per second a track has.
     *
     * An audio descriptor, the gateway of visuals/musica.py: the signal is
     * split into 20 ms windows, each window's energy is measured, and energy
     * JUMPS that exceed a fraction of the mean are counted. A jump is a note
     * coming in.
     */
    _attackDensity(buf) {
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
     * Among the four quadrant variations, the one with the FEWEST attacks.
     *
     * Under the text the quietest must sit, not a random one: among the four
     * the difference is more than double. Chosen once and remembered, because
     * the bed loads at startup and does not change again.
     */
    async _sparserTrack(emozione) {
        if (this._rade?.has(emozione)) return this._rade.get(emozione);
        if (!this._rade) this._rade = new Map();
        let scelta = null, minimo = Infinity;
        for (let i = 0; i < 4; i++) {
            const url = `/musica/${emozione}/${emozione}_${String(i).padStart(2, '0')}.wav`;
            try {
                const buf = await this._loadAudio(url);
                const d = this._attackDensity(buf);
                if (d < minimo) { minimo = d; scelta = buf; }
            } catch (_) { /* missing variation: skip */ }
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
                    ? await this._sparserTrack(emozione)
                    : await this._loadAudio(`/musica/${emozione}/${emozione}_`
                        + Math.floor(Math.random() * 4).toString().padStart(2, '0') + '.wav');
                s.gainVol  = this.ctx.createGain();
                s.gainAtt  = this.ctx.createGain();
                s.gainVoce = this.ctx.createGain();
                s.gainVol.gain.value = 0;
                s.gainAtt.gain.value = 1;
                // if voice is already speaking, the source that enters now
                // enters already ducked instead of covering it
                s.gainVoce.gain.value = this._voceInCorso ? this._voceAtt : 1;
                s.gainVol.connect(s.gainAtt).connect(s.gainVoce).connect(this._masterGain);
                s.node = this.ctx.createBufferSource();
                s.node.buffer = buf;
                s.node.loop = true;
                if (morbido) {
                    // The bed's voice: lower, sparser, with slower attacks.
                    // Not a time-stretch — speed and pitch drop TOGETHER, and
                    // that is exactly what is needed: in one operation notes
                    // go lower, attacks thin out in time and transients lengthen.
                    s.node.playbackRate.value = RALLENTAMENTO;
                    // Then the highs are softened, where the hammer click
                    // lives: without that, notes strike instead of entering.
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
     * The guide reads a phrase. The clip arrives already synthesized from the
     * backend cache — the same one the desktop version uses.
     */
    async voce(msg) {
        await this._ensure();
        this.silence();
        this._voceAtt = msg.attenuazione ?? 0.35;
        try {
            const buf = await this._loadAudio(msg.url);
            const g = this.ctx.createGain();
            g.gain.value = msg.volume ?? 0.75;
            const n = this.ctx.createBufferSource();
            n.buffer = buf;
            n.connect(g).connect(this._masterGain);
            n.onended = () => { if (this._voceNode === n) this._unduckAfterVoice(); };
            this._voceNode = n;
            this._voceInCorso = true;
            this._duckForVoice(this._voceAtt, 0.25);
            n.start();
        } catch (e) {
            console.warn('voce:', e);
            this._unduckAfterVoice();
        }
    }

    /** Cut the clip in progress: done before opening the microphone. */
    silence() {
        if (this._voceNode) {
            try { this._voceNode.stop(); } catch (_) {}
            this._voceNode = null;
        }
        this._unduckAfterVoice();
    }

    _unduckAfterVoice() {
        this._voceNode = null;
        this._voceInCorso = false;
        this._duckForVoice(1, 0.5);
    }

    _duckForVoice(valore, tempo) {
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
        // Duck both sources, play the bell, bring them back up
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
        // Synthesized bell
        this._campana(chiusura, discesa);
    }

    cancelCutaway() {
        for (const nome of ['principale', 'tappeto']) {
            const s = this._sorgenti[nome];
            if (!s.gainAtt || !this.ctx) continue;
            const t = this.ctx.currentTime;
            s.gainAtt.gain.cancelScheduledValues(t);
            s.gainAtt.gain.setValueAtTime(s.gainAtt.gain.value, t);
            s.gainAtt.gain.linearRampToValueAtTime(1, t + 0.3);
        }
    }

    // Same partials as visuals/campanella.py: ratio, weight, and how many
    // seconds until it fades. The ratios are those of a singing bowl — NOT
    // integer multiples, and that irregularity is what the ear recognizes as
    // "struck" rather than "played". High partials die first, so the sound
    // starts bright and turns dark as it fades: if they all faded together
    // you would hear an organ chord.
    static get PARZIALI() {
        return [[1.00, 1.00, 3.20], [2.71, 0.55, 1.80],
                [5.18, 0.28, 1.00], [8.35, 0.12, 0.55]];
    }

    _campana(chiusura, ritardo = 2.2) {
        if (!this.ctx) return;
        // Fundamental frequency: the low one for closing, a fifth above for
        // opening. The perfect fifth is the most consonant interval after
        // the octave: it does not clash with any bed key.
        const freq = chiusura ? 220 : 330;
        const BATTIMENTO = 0.9;   // Hz offset between the two halves of each partial
        const ATTACCO = 0.012;    // without a soft rise you would hear a click
        const t0 = this.ctx.currentTime + ritardo;

        for (const [mult, peso, decadimento] of AudioManager.PARZIALI) {
            // A bowl is never perfectly symmetrical, so each vibration mode
            // splits into two nearly identical frequencies: the two waves go
            // in phase then out of phase, and volume swells. That breath is
            // what makes the sound feel alive instead of printed.
            const battito = BATTIMENTO * mult;
            for (const scarto of [-battito / 2, battito / 2]) {
                const osc  = this.ctx.createOscillator();
                const gain = this.ctx.createGain();
                osc.type = 'sine';
                osc.frequency.value = freq * mult + scarto;
                const picco = peso * 0.06 / 2;   // two oscillators per partial
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

    // ---- microphone recording ----
    async openMic() {
        if (this._micStream) return;
        try {
            this._micStream = await navigator.mediaDevices.getUserMedia({ audio: true });
        } catch (e) {
            console.warn('microphone unavailable:', e);
        }
    }

    async startRecording() {
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
                if (!this._audioChunks.length) {
                    console.warn('recording: no audio chunks');
                    return;
                }
                const blob = new Blob(this._audioChunks, { type: this._recorder?.mimeType || 'audio/webm' });
                blob.arrayBuffer().then(buf => {
                    if (ws && ws.readyState === WebSocket.OPEN) {
                        ws.send(buf);
                    }
                });
            };
            // timeslice so Safari/Chrome flush chunks before stop
            this._recorder.start(1000);
        } catch (e) {
            console.warn('microphone unavailable:', e);
        }
    }

    stopRecording() {
        if (this._recorder && this._recorder.state !== 'inactive') {
            try { this._recorder.requestData(); } catch (_) {}
            this._recorder.stop();
        }
    }
}

const audio = new AudioManager();

// Live transcription during listening (eyes closed)
let _listenRec     = null;
let _listenActive  = false;
let _listenBase    = '';
let _listenReason  = null;   // 'racconto' | 'riflessione'

function _startVisualListening() {
    if (_listenActive) return;
    _listenActive = true;
    _listenBase   = '';
    const testoEl  = document.getElementById('session-text-body');
    if (testoEl) testoEl.textContent = '';
    document.getElementById('session-text')?.classList.add('visible');

    const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SR) return;

    _listenRec = new SR();
    _listenRec.lang = 'en-US';
    _listenRec.continuous = true;
    _listenRec.interimResults = true;
    _listenRec.onresult = ev => {
        let interim = '';
        for (let i = ev.resultIndex; i < ev.results.length; i++) {
            if (ev.results[i].isFinal) _listenBase += ev.results[i][0].transcript;
            else interim = ev.results[i][0].transcript;
        }
        if (testoEl) testoEl.textContent = (_listenBase + interim).trim();
    };
    _listenRec.onend = () => {
        if (_listenActive) {
            try { _listenRec?.start(); } catch (_) {}
        }
    };
    _listenRec.onerror = () => { /* Whisper fa da backup */ };

    try { _listenRec.start(); } catch (_) {}
}

function _stopVisualListening() {
    _listenActive = false;
    if (_listenRec) {
        try { _listenRec.stop(); } catch (_) {}
        _listenRec = null;
    }
    return document.getElementById('session-text-body')?.textContent?.trim() || '';
}

async function _beginListening() {
    if (_listenActive) return;
    _startVisualListening();
    try { await audio.openMic(); } catch (_) {}
    try { await audio.startRecording(); } catch (e) {
        console.warn('registrazione audio:', e);
    }
}

function _sendStart() {
    if (!ws || ws.readyState !== WebSocket.OPEN) return;
    ws.send(JSON.stringify({
        tipo:    'inizia',
        profilo: _userProfile || {},
    }));
}

function _showEndReflectionBtn() {
    const el = document.getElementById('ui-reflection');
    if (!el) return;
    el.classList.remove('hidden');
    el.classList.add('visible');
}

function _hideEndReflectionBtn() {
    const el = document.getElementById('ui-reflection');
    if (!el) return;
    el.classList.remove('visible');
    el.classList.add('hidden');
}

/** Resolve when the guide clip is no longer playing (or after a short timeout). */
function _waitForGuideVoice(maxMs = 20000) {
    const t0 = performance.now();
    return new Promise(resolve => {
        const tick = () => {
            if (!audio._voceInCorso || performance.now() - t0 > maxMs) {
                resolve();
                return;
            }
            setTimeout(tick, 80);
        };
        tick();
    });
}

function _openInExperienceReflection() {
    if (_inReflection) return;
    _inReflection = true;
    _reflectionDone = false;
    _postShown = true;
    _listenReason = 'riflessione';

    _sessionDuration = Math.round((Date.now() - _startTime) / 1000 / 60);
    _seriesPre       = _analyzer.series();
    _emotionPre    = _analyzer.report();
    _analyzer.stop();
    _startTime = null;

    _analyzerPost = new EmotionAnalyzer();
    _analyzerPost.start();
    _postPhaseActive = true;

    statusEl.textContent = 'how do you feel now?';
    _showEndReflectionBtn();
}

async function _finishReflection() {
    if (!_inReflection || _reflectionDone) return;
    _reflectionDone = true;
    _hideEndReflectionBtn();
    const testo = _stopVisualListening();
    _listenReason = null;
    audio.stopRecording();
    await _completeSession(testo);
}

function _hideExperienceOverlay() {
    document.getElementById('panel-results')?.classList.remove('visible');
    _hideEndReflectionBtn();
    _inReflection = false;
    _reflectionDone = false;
    _listenReason = null;
}

// ------------------------------------------------------------------ WebSocket
function connect() {
    if (ws && (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING)) {
        return;
    }
    statusEl.textContent = 'connecting...';
    ws = new WebSocket(WS_URL);

    const gen = _wsGeneration;
    ws.onopen = () => {
        if (gen !== _wsGeneration) return;
        statusEl.textContent = 'connected';
        if (_pendingStart) {
            _sendStart();
            _pendingStart = false;
        }
    };

    ws.onmessage = async (ev) => {
        if (gen !== _wsGeneration) return;
        // Audio messages arrive as Blob/ArrayBuffer, not JSON
        if (typeof ev.data !== 'string') return;

        let msg;
        try { msg = JSON.parse(ev.data); }
        catch (e) { console.warn('ws: messaggio non-JSON ignorato'); return; }

        const { tipo } = msg;
        console.log('ws ←', tipo, msg.scena || msg.azione || '');

        if (tipo === 'pronto') {
            if (!_sessionStarted) {
                _resetEntryUi();
                ui.classList.remove('hidden');
            }
            statusEl.textContent = 'ready';

        } else if (!_sessionStarted) {
            return;

        } else if (tipo === 'prepara') {
            const t0 = performance.now();
            logica.prepareTexts(msg.frasi, (frase, n) => sampleText(frase, n));
            console.log(`prepara: ${msg.frasi.length} scritte in ${(performance.now()-t0).toFixed(0)}ms`);

        } else if (tipo === 'prepara_mandala') {
            logica.prepareMandala(msg.petali, msg.anelli, msg.tonalita, msg.seed, msg.emozione);

        } else if (tipo === 'tinta') {
            // personal tint exists from now on; how much is visible is told by
            // tinta_forza, which arrives phase by phase
            logica.tinta(msg.tonalita, msg.emozione);

        } else if (tipo === 'tinta_forza') {
            logica.tintaForza(msg.valore, msg.durata);

        } else if (tipo === 'vai_a') {
            logica.goTo(msg.scena, msg.testo, msg.durata);
            // Light up the screen on the first visual event (if still dark)
            if (renderer && renderer._t_accendi === null && renderer._post) {
                renderer.lightsUp(3.0, performance.now() / 1000);
            }

        } else if (tipo === 'azzera') {
            logica.reset();

        } else if (tipo === 'buio') {
            renderer.lightsOut();

        } else if (tipo === 'accendi') {
            renderer.lightsUp(msg.durata, performance.now() / 1000);

        } else if (tipo === 'musica') {
            await audio.handle(msg);

        } else if (tipo === 'voce') {
            if (msg.azione === 'di') await audio.voce(msg);
            else audio.silence();

        } else if (tipo === 'stacco') {
            audio.stacco(msg.chiusura, msg.discesa, msg.respiro, msg.ritorno);

        } else if (tipo === 'stacco_annulla') {
            audio.cancelCutaway();

        } else if (tipo === 'ascolto') {
            if (msg.azione === 'apri') {
                await audio.openMic();
            } else if (msg.azione === 'inizia' || msg.azione === 'start') {
                if (!_inReflection) _listenReason = 'racconto';
                // Wait until ElevenLabs finishes so guide + mic don't overlap
                await _waitForGuideVoice();
                await _beginListening();
            } else if (msg.azione === 'ferma' || msg.azione === 'stop') {
                const motivo = _listenReason || 'racconto';
                const testo  = _stopVisualListening();
                _listenReason = null;
                audio.stopRecording();
                if (motivo === 'riflessione') {
                    if (!_reflectionDone) {
                        _reflectionDone = true;
                        _hideEndReflectionBtn();
                        await _completeSession(testo);
                    }
                } else {
                    _sessionText = testo;
                    if (testo && ws?.readyState === WebSocket.OPEN) {
                        ws.send(JSON.stringify({
                            tipo:    'racconto',
                            testo,
                            profilo: _userProfile || {},
                        }));
                    }
                }
            }

        } else if (tipo === 'ui') {
            if (msg.fase === 'riflessione' && msg.azione === 'apri') {
                // Only open the Done UI — mic starts later on ascolto/inizia,
                // after the guide finishes speaking.
                _openInExperienceReflection();
            } else if (msg.fase === 'nascondi') {
                _hideExperienceOverlay();
            }

        } else if (tipo === 'fine') {
            _hideExperienceOverlay();
            _experienceDone = true;
            statusEl.textContent = 'see you soon';
        }
    };

    ws.onclose = () => {
        if (gen !== _wsGeneration) return;
        statusEl.textContent = 'disconnected';
        if (_sessionStarted && !_experienceDone) {
            setTimeout(() => {
                if (gen === _wsGeneration) connect();
            }, 2000);
        }
    };
    ws.onerror = () => {
        if (gen === _wsGeneration) ws.close();
    };
}

// ------------------------------------------------------------------ face tracking
async function initFaceTracking() {
    statusEl.textContent = 'loading MediaPipe...';
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
        outputFaceBlendshapes: true,   // enable the 52 blend shapes for emotion analysis
    });

    // Webcam (hidden: preview unused, coordinates needed)
    video = document.getElementById('video');
    try {
        const stream = await navigator.mediaDevices.getUserMedia({ video: true, audio: false });
        video.srcObject = stream;
        await new Promise(res => { video.onloadedmetadata = res; });
        await video.play();
    } catch (e) {
        console.warn('webcam non disponibile:', e);
    }
    statusEl.textContent = 'ready';
}

// ------------------------------------------------------------------ loop
let _lastSend = 0;
const SEND_INTERVAL = 1 / 30; // 30fps to the server

function loop(timestamp) {
    requestAnimationFrame(loop);
    const ora = timestamp / 1000;

    // Update face landmarks
    if (faceLandmarker && video && video.readyState >= 2) {
        try {
            const res = faceLandmarker.detectForVideo(video, timestamp);
            if (res.faceLandmarks.length > 0) {
                landmarks = res.faceLandmarks[0];
                // Save blend shapes for emotion analysis + eye blink
                let blink = null;
                if (res.faceBlendshapes?.length > 0) {
                    blendshapes = res.faceBlendshapes[0].categories;
                    if (_startTime)      _analyzer.update(blendshapes);
                    if (_postPhaseActive)  _analyzerPost?.update(blendshapes);
                    let L = 0, R = 0;
                    for (const b of blendshapes) {
                        if (b.categoryName === 'eyeBlinkLeft')  L = b.score;
                        if (b.categoryName === 'eyeBlinkRight') R = b.score;
                    }
                    blink = (L + R) / 2;
                }
                // Send to server ~30fps
                if (ws && ws.readyState === WebSocket.OPEN && ora - _lastSend > SEND_INTERVAL) {
                    _lastSend = ora;
                    const msg = {
                        tipo: 'frame',
                        punti: landmarks.map(p => [p.x, p.y, p.z]),
                    };
                    if (blink != null) msg.blink = blink;
                    ws.send(JSON.stringify(msg));
                }
            }
        } catch (_) {}
    }

    // Update particle logic and draw
    if (logica && renderer) {
        const { posizioni, colori, background } = logica.update(landmarks, ora);
        renderer.update(posizioni, colori);
        renderer.setBackground(background);
        renderer.render(ora);
    }
}

// ------------------------------------------------------------------ startup
async function init() {
    const canvas = document.getElementById('canvas');

    renderer = new ParticleRenderer(canvas);
    logica   = new ParticleLogic();
    await logica.init();

    await initFaceTracking();
    _showEntryUi();

    requestAnimationFrame(loop);
}

function _showEntryUi() {
    _resetEntryUi();
    ui.classList.remove('hidden');
    statusEl.textContent = 'ready';
}

// ------------------------------------------------------------------ Firebase auth
const loginOverlay   = document.getElementById('login-overlay');
const profileOverlay = document.getElementById('profile-overlay');
const ctrlItemProfile = document.getElementById('ctrl-item-profile');
const userName     = document.getElementById('user-name');
const userAvatar   = document.getElementById('user-avatar');
const userAvatarFallback = document.getElementById('user-avatar-fallback');
const loginError    = document.getElementById('login-error');
const loginOk        = document.getElementById('login-ok');
const userFlyout   = document.getElementById('user-flyout');
const volumeFlyout   = document.getElementById('volume-flyout');

// Initialize Firebase (config from server) then register the auth listener
const _firebaseConfigured = await initialize();

onAuth(async utente => {
    _currentUser = utente;
    if (utente) {
        // Hide login overlay
        loginOverlay.classList.add('hidden');
        userName.textContent = utente.displayName || utente.email || '';
        if (utente.photoURL) {
            userAvatar.src = utente.photoURL;
            userAvatar.style.display = 'block';
            if (userAvatarFallback) userAvatarFallback.style.display = 'none';
        } else {
            userAvatar.style.display = 'none';
            if (userAvatarFallback) userAvatarFallback.style.display = 'block';
        }
        ctrlItemProfile?.classList.add('visible');

        // Check whether the profile already exists on Firestore (first login?)
        try { _userProfile = await loadProfile(utente.uid); }
        catch (_) { _userProfile = null; }

        if (!_userProfile) {
            // First login: show the profile form
            profileOverlay?.classList.add('visible');
        } else {
            // Profile already exists: continue
            profileOverlay?.classList.remove('visible');
            if (!renderer) init();
        }
    } else {
        // Not logged in
        profileOverlay?.classList.remove('visible');
        if (_firebaseConfigured) {
            loginOverlay.classList.remove('hidden');
            ctrlItemProfile?.classList.remove('visible');
        } else {
            // Firebase not configured: skip login and start directly
            loginOverlay.classList.add('hidden');
            if (!renderer) init();
        }
    }
});

document.getElementById('btn-google').addEventListener('click', async () => {
    if (loginError) loginError.textContent = '';
    if (loginOk)     loginOk.textContent     = '';
    // Unlock AudioContext during the login user gesture
    try { await audio._ensure(); } catch (_) {}
    try {
        await loginGoogle();
    } catch (e) {
        console.warn('login error:', e);
        loginError.textContent = _errorMessage(e);
    }
});

document.getElementById('btn-logout').addEventListener('click', async () => {
    await logout();
});

// ------------------------------------------------------------------ email/password form
let _authMode   = 'sign-in';   // 'sign-in' | 'sign-up'

// Tab switch
document.querySelectorAll('.login-tab').forEach(tab => {
    tab.addEventListener('click', () => {
        _authMode = tab.dataset.tab;
        document.querySelectorAll('.login-tab').forEach(t => t.classList.remove('active'));
        tab.classList.add('active');
        const isReg = _authMode === 'sign-up';
        document.getElementById('auth-confirm').style.display = isReg ? 'block' : 'none';
        document.getElementById('link-reset').style.display    = isReg ? 'none'  : 'block';
        document.getElementById('btn-submit-auth').textContent = isReg ? 'Sign up' : 'Sign in';
        loginError.textContent = '';
        loginOk.textContent = '';
    });
});

// Submit (Sign in or Sign up)
document.getElementById('btn-submit-auth').addEventListener('click', async () => {
    loginError.textContent = '';
    loginOk.textContent = '';
    const email    = document.getElementById('auth-email').value.trim();
    const password = document.getElementById('auth-password').value;
    const conferma = document.getElementById('auth-confirm').value;

    if (!email || !password) { loginError.textContent = 'Enter email and password.'; return; }

    // Unlock AudioContext during the login user gesture
    try { await audio._ensure(); } catch (_) {}

    try {
        if (_authMode === 'sign-up') {
            if (password !== conferma) { loginError.textContent = 'Passwords do not match.'; return; }
            if (password.length < 6)   { loginError.textContent = 'Password must be at least 6 characters.'; return; }
            await registerEmail(email, password);
        } else {
            await loginEmail(email, password);
        }
    } catch (e) {
        loginError.textContent = _errorMessage(e);
    }
});

// Forgot password
document.getElementById('link-reset').addEventListener('click', async () => {
    loginError.textContent = '';
    loginOk.textContent = '';
    const email = document.getElementById('auth-email').value.trim();
    if (!email) { loginError.textContent = 'Enter your email above.'; return; }
    try {
        await resetPassword(email);
        loginOk.textContent = 'Recovery email sent. Check your inbox.';
    } catch (e) {
        loginError.textContent = _errorMessage(e);
    }
});

// Submit with Enter in the fields
['auth-email','auth-password','auth-confirm'].forEach(id => {
    document.getElementById(id)?.addEventListener('keydown', e => {
        if (e.key === 'Enter') document.getElementById('btn-submit-auth')?.click();
    });
});

/** Map Firebase error codes to readable messages. */
function _errorMessage(e) {
    const m = { 'auth/invalid-email': 'Invalid email.',
                'auth/user-not-found': 'No account with this email.',
                'auth/wrong-password': 'Wrong password.',
                'auth/email-already-in-use': 'Email already registered.',
                'auth/weak-password': 'Password too weak (min. 6 characters).',
                'auth/too-many-requests': 'Too many attempts. Try again later.',
                'auth/popup-closed-by-user': '' };
    return m[e.code] || e.message || 'Unknown error.';
}

// ------------------------------------------------------------------ profile form (first login)
let _selectedGender = '';

document.querySelectorAll('.gender-btn').forEach(btn => {
    btn.addEventListener('click', () => {
        document.querySelectorAll('.gender-btn').forEach(b => b.classList.remove('selected'));
        btn.classList.add('selected');
        _selectedGender = btn.dataset.val;
    });
});

document.getElementById('btn-profile-save').addEventListener('click', async () => {
    const profileError = document.getElementById('profile-error');
    profileError.textContent = '';

    const nome      = document.getElementById('profile-first-name').value.trim();
    const cognome   = document.getElementById('profile-last-name').value.trim();
    const eta       = parseInt(document.getElementById('profile-age').value, 10);
    const obiettivo = document.getElementById('profile-goal').value.trim();

    if (!nome)                  { profileError.textContent = 'Enter your first name.'; return; }
    if (!_selectedGender)     { profileError.textContent = 'Select your gender.'; return; }
    if (!eta || eta < 10 || eta > 120) { profileError.textContent = 'Enter a valid age.'; return; }
    if (!obiettivo)             { profileError.textContent = 'Tell us what you\'d like to improve.'; return; }

    // Field names kept for Firestore / backend compatibility
    const profile = { nome, cognome, eta, sesso: _selectedGender, obiettivo };

    // Save to Firestore if available
    if (_currentUser) await saveProfile(_currentUser.uid, profile);
    _userProfile = profile;

    // Unlock AudioContext here — the profile click IS the user gesture
    try { await audio._ensure(); } catch (_) {}

    // Hide the form and start the experience
    profileOverlay.classList.remove('visible');
    if (!renderer) init();
});

// ------------------------------------------------------------------ entry UI (Start only)
const uiStep1 = document.getElementById('ui-step1');

function _resetEntryUi() {
    uiStep1?.classList.remove('hidden');
    document.getElementById('ui-restart')?.classList.add('hidden');
    _hideEndReflectionBtn();
    document.getElementById('session-text')?.classList.remove('visible');
    const testoEl = document.getElementById('session-text-body');
    if (testoEl) testoEl.textContent = '';
}

function _showRestartUi() {
    ui.classList.remove('hidden');
    uiStep1?.classList.add('hidden');
    document.getElementById('ui-restart')?.classList.remove('hidden');
}

document.getElementById('start').addEventListener('click', async () => {
    await _beginExperience();
});

document.getElementById('btn-end-reflection')?.addEventListener('click', () => {
    _finishReflection();
});

/** Same path as pressing Start at the beginning of a session. */
async function _beginExperience() {
    _sessionStarted = true;
    _postShown = false;
    _experienceDone = false;
    _inReflection = false;
    _reflectionDone = false;
    _seriesPre  = { valenza: [], arousal: [] };
    _seriesPost = { valenza: [], arousal: [] };
    _sessionText = '';
    _startTime = Date.now();
    _postPhaseActive = false;
    _analyzerPost = null;
    _analyzer.start();
    ui.classList.add('hidden');
    document.getElementById('ui-restart')?.classList.add('hidden');
    uiStep1?.classList.remove('hidden');
    document.getElementById('session-text')?.classList.remove('visible');
    const testoEl = document.getElementById('session-text-body');
    if (testoEl) testoEl.textContent = '';
    statusEl.textContent = 'experience in progress';
    try { await audio._ensure(); } catch (_) {}

    if (ws && ws.readyState === WebSocket.OPEN) {
        _sendStart();
    } else {
        _pendingStart = true;
        connect();
    }
}

/**
 * Close the charts panel and start a new session from the same point as Start.
 * Tears down the old WebSocket so the backend experience thread stops cleanly.
 */
async function _restartFromStart() {
    document.getElementById('panel-results')?.classList.remove('visible');
    _hideEndReflectionBtn();
    _stopVisualListening();
    audio.silence();
    audio.stopRecording();
    try { audio._stop('principale'); } catch (_) {}
    try { audio._stop('tappeto'); } catch (_) {}
    _destroyResultCharts();

    // Invalidate the old socket so its onclose cannot auto-reconnect or
    // swallow the new session's start message.
    _experienceDone = true;
    _pendingStart = false;
    _wsGeneration += 1;
    if (ws) {
        try { ws.close(); } catch (_) {}
        ws = null;
    }
    if (logica) logica.reset();
    if (renderer) renderer.lightsOut();

    await new Promise(r => setTimeout(r, 200));
    await _beginExperience();
}

// ------------------------------------------------------------------ Left control flyouts
const ctrlItemProfileEl = document.getElementById('ctrl-item-profile');
const ctrlItemVolumeEl  = document.getElementById('ctrl-item-volume');

function _positionFlyout(btn, flyout) {
    if (!btn || !flyout) return;
    const r = btn.getBoundingClientRect();
    flyout.style.left = `${Math.round(r.right + 7)}px`;
    flyout.style.top  = `${Math.round(r.top + r.height / 2)}px`;
}

function _closeFlyout(...els) {
    for (const el of els) el?.classList.remove('open');
    ctrlItemProfileEl?.classList.remove('open');
    ctrlItemVolumeEl?.classList.remove('open');
}
function _toggleFlyout(el, btn, itemEl, altro = null) {
    if (!el) return false;
    const apri = !el.classList.contains('open');
    if (altro) _closeFlyout(altro);
    el.classList.toggle('open', apri);
    itemEl?.classList.toggle('open', apri);
    if (apri) _positionFlyout(btn, el);
    return apri;
}

const btnProfileToggle = document.getElementById('btn-profile-toggle');
btnProfileToggle?.addEventListener('click', e => {
    e.stopPropagation();
    const open = _toggleFlyout(userFlyout, btnProfileToggle, ctrlItemProfileEl, volumeFlyout);
    btnProfileToggle.setAttribute('aria-expanded', open ? 'true' : 'false');
});

// Volume button + slider
const volumeSlider = document.getElementById('volume-slider');
const btnMute = document.getElementById('btn-mute');

btnMute?.addEventListener('click', async e => {
    e.stopPropagation();
    try { await audio._ensure(); } catch (_) {}
    const open = _toggleFlyout(volumeFlyout, btnMute, ctrlItemVolumeEl, userFlyout);
    btnMute.setAttribute('aria-expanded', open ? 'true' : 'false');
});

window.addEventListener('resize', () => {
    if (userFlyout?.classList.contains('open')) _positionFlyout(btnProfileToggle, userFlyout);
    if (volumeFlyout?.classList.contains('open')) _positionFlyout(btnMute, volumeFlyout);
});

volumeSlider?.addEventListener('input', async () => {
    try { await audio._ensure(); } catch (_) {}
    audio.setMasterVolume(Number(volumeSlider.value) / 100);
    btnMute?.classList.remove('active');
});

btnMute?.addEventListener('dblclick', async e => {
    e.preventDefault();
    e.stopPropagation();
    try { await audio._ensure(); } catch (_) {}
    const muted = audio.toggleMute();
    btnMute.classList.toggle('active', muted);
    btnMute.title = muted ? 'Unmute music (double-click)' : 'Music volume (double-click to mute)';
});

document.addEventListener('click', e => {
    if (e.target.closest('#controls-left')) return;
    _closeFlyout(userFlyout, volumeFlyout);
    btnProfileToggle?.setAttribute('aria-expanded', 'false');
    btnMute?.setAttribute('aria-expanded', 'false');
});

// Info button / modal
const modalInfo = document.getElementById('modal-info');
document.getElementById('btn-info').addEventListener('click', () => {
    _closeFlyout(userFlyout, volumeFlyout);
    modalInfo.classList.add('visible');
});
document.getElementById('modal-close').addEventListener('click', () => {
    modalInfo.classList.remove('visible');
});
modalInfo.addEventListener('click', e => {
    if (e.target === modalInfo) modalInfo.classList.remove('visible');
});

// Calendar from top-right
document.getElementById('btn-calendar-top')?.addEventListener('click', () => {
    _closeFlyout(userFlyout, volumeFlyout);
    openCalendar();
});

// ------------------------------------------------------------------ Post-meditation panel (reflection via particles + voice)

async function _completeSession(riflessione) {
    _hideEndReflectionBtn();
    if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ tipo: 'riflessione_post', testo: riflessione }));
    }

    _postPhaseActive = false;
    _seriesPost       = _analyzerPost?.series() || { valenza: [], arousal: [] };
    const emozionePost = _analyzerPost?.report() || {};
    _analyzerPost?.stop();

    document.getElementById('session-text')?.classList.remove('visible');

    // Call Claude with pre+post data
    const payload = {
        racconto:      _sessionText.slice(0, 400),
        riflessione:   riflessione.slice(0, 400),
        durata_minuti: _sessionDuration,
        emozioni:      _emotionPre || {},
        emozioni_post: emozionePost,
        profilo:       _userProfile || {},
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

    // Save to Firestore (series + plain-language copy for the calendar)
    const testiRisultato = _resultsCopy(_emotionPre, emozionePost, _seriesPre, _seriesPost);
    const datiSessione = {
        racconto:            _sessionText,
        riflessione_post:    riflessione,
        durata_minuti:       _sessionDuration,
        emozioni_pre:        _emotionPre || {},
        emozioni_post:       emozionePost,
        serie_pre:           _seriesPre,
        serie_post:          _seriesPost,
        spiegazione_umore:   testiRisultato.explainMood,
        spiegazione_energia: testiRisultato.explainEnergy,
        analisi_claude:      analisi,
        completata:          _sessionDuration >= 2,
    };

    if (_currentUser) {
        const id = await saveDailySession(_currentUser.uid, datiSessione);
        const today = new Date().toISOString().split('T')[0];
        if (!_calSessions[today]) _calSessions[today] = [];
        _calSessions[today].unshift({ id: id || `local-${Date.now()}`, ...datiSessione, data_giorno: today });
    }

    // Show the results panel with the charts
    showResults(_emotionPre || {}, emozionePost, analisi, _seriesPre, _seriesPost);
    document.getElementById('panel-results').classList.add('visible');
}

// ------------------------------------------------------------------ Chart.js charts
let _resultCharts = [];

function _mean(arr) {
    if (!arr?.length) return null;
    return arr.reduce((s, v) => s + v, 0) / arr.length;
}

function _fmt(v, digits = 2) {
    if (v == null || Number.isNaN(v)) return '—';
    return Number(v).toFixed(digits);
}

/** Running centroid (cumulative mean) of paired valence/arousal samples. */
function _centroidPath(vals, arous) {
    const n = Math.min(vals?.length || 0, arous?.length || 0);
    const path = [];
    let sumV = 0, sumA = 0;
    for (let i = 0; i < n; i++) {
        sumV += vals[i];
        sumA += arous[i];
        path.push({ x: sumV / (i + 1), y: sumA / (i + 1) });
    }
    return path;
}

function _phaseCentroid(vals, arous) {
    const v = _mean(vals);
    const a = _mean(arous);
    if (v == null || a == null) return null;
    return { x: v, y: a };
}

function _timeLabels(n) {
    if (n <= 0) return [];
    return Array.from({ length: n }, (_, i) => {
        if (i === 0) return '0s';
        if (i === n - 1 || i % Math.max(1, Math.floor(n / 4)) === 0) return `${i}s`;
        return '';
    });
}

function _lineChartOptions(yMin, yMax, yTickFn) {
    return {
        responsive: true,
        maintainAspectRatio: false,
        animation: false,
        interaction: { mode: 'index', intersect: false },
        plugins: {
            legend: { display: false },
            tooltip: {
                callbacks: {
                    title: items => {
                        const i = items[0]?.dataIndex;
                        return i == null ? '' : `t = ${i}s`;
                    },
                    label: ctx => {
                        const v = ctx.parsed.y;
                        return v == null ? null : yTickFn(v);
                    },
                },
            },
        },
        scales: {
            x: {
                ticks: { color: 'rgba(255,255,255,0.4)', font: { size: 9 }, maxRotation: 0, autoSkip: false },
                grid: { color: 'rgba(255,255,255,0.05)' },
            },
            y: {
                min: yMin,
                max: yMax,
                ticks: {
                    color: 'rgba(255,255,255,0.45)',
                    font: { size: 9 },
                    callback: v => yTickFn(v),
                },
                grid: { color: 'rgba(255,255,255,0.06)' },
            },
        },
    };
}

function _makeLineChart(canvas, values, color, fill, yMin, yMax, yTickFn) {
    const data = values || [];
    return new Chart(canvas, {
        type: 'line',
        data: {
            labels: _timeLabels(data.length),
            datasets: [{
                data,
                borderColor: color,
                backgroundColor: fill,
                fill: true,
                tension: 0.3,
                pointRadius: data.length <= 40 ? 2 : 0,
                pointHitRadius: 10,
                borderWidth: 1.5,
            }],
        },
        options: _lineChartOptions(yMin, yMax, yTickFn),
    });
}

function _makeCentroidChart(canvas, seriePre, seriePost) {
    const preV  = seriePre?.valenza  || [];
    const preA  = seriePre?.arousal  || [];
    const postV = seriePost?.valenza || [];
    const postA = seriePost?.arousal || [];

    const pathPre  = _centroidPath(preV, preA);
    const pathPost = _centroidPath(postV, postA);
    const cPre  = _phaseCentroid(preV, preA);
    const cPost = _phaseCentroid(postV, postA);

    const datasets = [];
    if (pathPre.length) {
        datasets.push({
            label: 'During (running mean)',
            data: pathPre,
            showLine: true,
            borderColor: 'rgba(120, 220, 160, 0.85)',
            backgroundColor: 'rgba(120, 220, 160, 0.85)',
            pointRadius: 0,
            borderWidth: 1.5,
            tension: 0.2,
        });
    }
    if (pathPost.length) {
        datasets.push({
            label: 'After (running mean)',
            data: pathPost,
            showLine: true,
            borderColor: 'rgba(255, 200, 100, 0.85)',
            backgroundColor: 'rgba(255, 200, 100, 0.85)',
            pointRadius: 0,
            borderWidth: 1.5,
            tension: 0.2,
        });
    }
    if (cPre) {
        datasets.push({
            label: 'Mean during',
            data: [cPre],
            showLine: false,
            pointRadius: 7,
            pointHoverRadius: 8,
            backgroundColor: 'rgba(120, 220, 160, 1)',
            borderColor: '#fff',
            borderWidth: 1.5,
        });
    }
    if (cPost) {
        datasets.push({
            label: 'Mean after',
            data: [cPost],
            showLine: false,
            pointRadius: 7,
            pointHoverRadius: 8,
            backgroundColor: 'rgba(255, 200, 100, 1)',
            borderColor: '#fff',
            borderWidth: 1.5,
        });
    }
    if (cPre && cPost) {
        datasets.push({
            label: 'Shift',
            data: [cPre, cPost],
            showLine: true,
            borderColor: 'rgba(255,255,255,0.45)',
            backgroundColor: 'transparent',
            borderDash: [4, 4],
            pointRadius: 0,
            borderWidth: 1,
        });
    }

    return new Chart(canvas, {
        type: 'scatter',
        data: { datasets },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            animation: false,
            plugins: {
                legend: {
                    display: true,
                    labels: {
                        color: 'rgba(255,255,255,0.55)',
                        boxWidth: 10,
                        font: { size: 10 },
                        filter: item => item.text !== 'Shift',
                    },
                },
                tooltip: {
                    callbacks: {
                        label: ctx => {
                            const p = ctx.raw;
                            if (!p || p.x == null) return null;
                            return `${ctx.dataset.label}: V ${_fmt(p.x)} · A ${_fmt(p.y)}`;
                        },
                    },
                },
            },
            scales: {
                x: {
                    type: 'linear',
                    min: -1,
                    max: 1,
                    title: {
                        display: true,
                        text: 'Valence (− → +)',
                        color: 'rgba(255,255,255,0.45)',
                        font: { size: 10 },
                    },
                    ticks: { color: 'rgba(255,255,255,0.4)', font: { size: 9 } },
                    grid: { color: 'rgba(255,255,255,0.06)' },
                },
                y: {
                    type: 'linear',
                    min: 0,
                    max: 1,
                    title: {
                        display: true,
                        text: 'Arousal (calm → activated)',
                        color: 'rgba(255,255,255,0.45)',
                        font: { size: 10 },
                    },
                    ticks: { color: 'rgba(255,255,255,0.4)', font: { size: 9 } },
                    grid: { color: 'rgba(255,255,255,0.06)' },
                },
            },
        },
    });
}

function _moodInWords(v) {
    if (v > 0.3)  return 'Open, light mood';
    if (v > 0.1)  return 'Slightly positive mood';
    if (v < -0.3) return 'Closed or thoughtful mood';
    if (v < -0.1) return 'Slightly low mood';
    return 'Neutral mood';
}

function _energyInWords(a) {
    if (a > 0.65) return 'Very active or tense';
    if (a > 0.4)  return 'Alert, with some energy';
    if (a < 0.2)  return 'Relaxed and quiet';
    if (a < 0.35) return 'Fairly calm';
    return 'Balance of calm and attention';
}

function _explainMood(pre, post, seriePre, seriePost) {
    const n = (seriePre?.length || 0) + (seriePost?.length || 0);
    if (n < 3) {
        return 'We didn\'t get enough from your face to track how you felt. Stay in front of the webcam with good lighting.';
    }

    const vPre  = pre?.valenza_media ?? _mean(seriePre) ?? 0;
    const vPost = post?.valenza_media ?? _mean(seriePost) ?? vPre;
    const d     = vPost - vPre;
    const parti = [];

    if (pre?.arco_emotivo === 'miglioramento') {
        parti.push('During meditation, your face tended toward more open states.');
    } else if (pre?.arco_emotivo === 'peggioramento') {
        parti.push('During meditation, your face moved through more closed or thoughtful moments: that can happen when emotions surface to be processed.');
    }

    if (Math.abs(d) < 0.08) {
        parti.push('From start to finish, your emotional tone stayed fairly stable.');
    } else if (d > 0) {
        parti.push('Compared with the start, you seem to leave with a lighter, more open mood.');
    } else {
        parti.push('Compared with the start, you seem a bit more closed or thoughtful: that is not a failure; meditation sometimes brings up hard things.');
    }

    if ((seriePost?.length || 0) > 2 && Math.abs(vPost - vPre) >= 0.08) {
        parti.push(vPost > vPre
            ? 'Afterward, your face still reads a bit more serene.'
            : 'After reflection, your face still reads more introspective.');
    }

    return parti.join(' ') || `${_moodInWords(vPre)}.`;
}

function _explainEnergy(pre, post, seriePre, seriePost) {
    const n = (pre?.n_campioni || 0) + (post?.n_campioni || 0)
        || ((seriePre?.length || 0) + (seriePost?.length || 0));
    if (n < 3) {
        return 'We don\'t have enough data to describe how your tension changed over time.';
    }

    const aPre  = pre?.arousal_medio ?? _mean(seriePre) ?? 0;
    const aPost = post?.arousal_medio ?? _mean(seriePost) ?? aPre;
    const d     = aPost - aPre;
    const parti = [];

    parti.push(`At the start you were ${_energyInWords(aPre).toLowerCase()}.`);

    if (Math.abs(d) < 0.08) {
        parti.push('Your body\'s activation level stayed roughly the same throughout the session.');
    } else if (d < -0.08) {
        parti.push('Over the minutes you seem to have loosened up: less tension, more relaxation.');
    } else {
        parti.push('Over the minutes your body became more alert, as after focused attention.');
    }

    if ((post?.n_campioni || seriePost?.length || 0) >= 3) {
        parti.push(`After reflection you come across as ${_energyInWords(aPost).toLowerCase()}.`);
    }

    return parti.join(' ');
}

function _resultsCopy(pre, post, seriePre, seriePost) {
    const preV  = seriePre?.valenza  || [];
    const postV = seriePost?.valenza || [];
    const preA  = seriePre?.arousal  || [];
    const postA = seriePost?.arousal || [];
    return {
        explainMood:   _explainMood(pre, post, preV, postV),
        explainEnergy: _explainEnergy(pre, post, preA, postA),
    };
}

function _destroyResultCharts() {
    for (const c of _resultCharts) {
        try { c.destroy(); } catch (_) {}
    }
    _resultCharts = [];
}

function _createChartsOnCanvas(ids, seriePre, seriePost) {
    const preV  = seriePre?.valenza  || [];
    const preA  = seriePre?.arousal  || [];
    const postV = seriePost?.valenza || [];
    const postA = seriePost?.arousal || [];

    Chart.defaults.color = 'rgba(255,255,255,0.45)';

    const tickV = v => Number(v).toFixed(1);
    const tickA = v => Number(v).toFixed(1);
    const charts = [];

    if (ids.vPre)  charts.push(_makeLineChart(ids.vPre,  preV,  'rgba(120, 220, 160, 0.95)', 'rgba(120, 220, 160, 0.12)', -1, 1, tickV));
    if (ids.aPre)  charts.push(_makeLineChart(ids.aPre,  preA,  'rgba(120, 180, 255, 0.95)', 'rgba(120, 180, 255, 0.12)',  0, 1, tickA));
    if (ids.vPost) charts.push(_makeLineChart(ids.vPost, postV, 'rgba(255, 200, 100, 0.95)', 'rgba(255, 200, 100, 0.12)', -1, 1, tickV));
    if (ids.aPost) charts.push(_makeLineChart(ids.aPost, postA, 'rgba(255, 160, 120, 0.95)', 'rgba(255, 160, 120, 0.12)',  0, 1, tickA));
    if (ids.centroid) charts.push(_makeCentroidChart(ids.centroid, seriePre, seriePost));

    return charts;
}

function showResults(pre, post, analisi, seriePre, seriePost) {
    _destroyResultCharts();

    _resultCharts = _createChartsOnCanvas({
        vPre:     document.getElementById('chart-v-pre'),
        aPre:     document.getElementById('chart-a-pre'),
        vPost:    document.getElementById('chart-v-post'),
        aPost:    document.getElementById('chart-a-post'),
        centroid: document.getElementById('chart-centroid'),
    }, seriePre, seriePost);

    const testi = _resultsCopy(pre, post, seriePre, seriePost);
    const moodEl = document.getElementById('spiega-valence');
    if (moodEl) moodEl.textContent = testi.explainMood;
    const energyEl = document.getElementById('spiega-arousal');
    if (energyEl) energyEl.textContent = testi.explainEnergy;

    if (analisi?.interpretazione) {
        document.getElementById('results-text').textContent = analisi.interpretazione;
        document.getElementById('results-analysis').style.display = 'block';
    } else {
        document.getElementById('results-analysis').style.display = 'none';
    }
}

function _destroyCalendarCharts() {
    for (const c of _calCharts) {
        try { c.destroy(); } catch (_) {}
    }
    _calCharts = [];
}

function _sessionResultHtml(s, sid) {
    const testi = (s.spiegazione_umore && s.spiegazione_energia)
        ? { explainMood: s.spiegazione_umore, explainEnergy: s.spiegazione_energia }
        : _resultsCopy(
            s.emozioni_pre, s.emozioni_post,
            s.serie_pre || { valenza: [], arousal: [] },
            s.serie_post || { valenza: [], arousal: [] },
        );
    const haSerie = (s.serie_pre?.valenza?.length || 0) + (s.serie_post?.valenza?.length || 0) >= 3;
    const dur = s.durata_minuti || '—';

    return `<div class="cal-session-item" data-sid="${sid}">
      <strong>${dur} minutes</strong>
      ${s.racconto ? `<div class="cal-story">"${s.racconto.slice(0, 100)}${s.racconto.length > 100 ? '…' : ''}"</div>` : ''}
      ${s.riflessione_post ? `<div class="cal-story" style="font-style:normal;opacity:0.85">After: "${s.riflessione_post.slice(0, 100)}${s.riflessione_post.length > 100 ? '…' : ''}"</div>` : ''}
      ${haSerie ? `
        <div class="charts-grid">
          <div class="chart-wrap"><h4>Valence · during</h4><canvas id="cal-vp-${sid}" height="90"></canvas></div>
          <div class="chart-wrap"><h4>Arousal · during</h4><canvas id="cal-ap-${sid}" height="90"></canvas></div>
          <div class="chart-wrap"><h4>Valence · after</h4><canvas id="cal-vo-${sid}" height="90"></canvas></div>
          <div class="chart-wrap"><h4>Arousal · after</h4><canvas id="cal-ao-${sid}" height="90"></canvas></div>
          <div class="chart-wrap chart-centroid"><h4>Centroid path</h4><canvas id="cal-c-${sid}" height="140"></canvas></div>
        </div>
        <p class="chart-caption">${testi.explainMood}</p>
        <p class="chart-caption">${testi.explainEnergy}</p>` : `
        <p class="chart-caption">${testi.explainMood}</p>
        <p class="chart-caption">${testi.explainEnergy}</p>`}
      ${s.analisi_claude?.interpretazione ? `
        <div class="cal-summary">
          <strong>In summary</strong>
          ${s.analisi_claude.interpretazione}
        </div>` : ''}
    </div>`;
}

function _renderCalendarCharts(sessioni) {
    for (const s of sessioni) {
        const sid = s.id || 'x';
        const n = (s.serie_pre?.valenza?.length || 0) + (s.serie_post?.valenza?.length || 0);
        if (n < 3) continue;
        const ids = {
            vPre:     document.getElementById(`cal-vp-${sid}`),
            aPre:     document.getElementById(`cal-ap-${sid}`),
            vPost:    document.getElementById(`cal-vo-${sid}`),
            aPost:    document.getElementById(`cal-ao-${sid}`),
            centroid: document.getElementById(`cal-c-${sid}`),
        };
        if (!ids.vPre || !ids.centroid) continue;
        const charts = _createChartsOnCanvas(
            ids, s.serie_pre || { valenza: [], arousal: [] }, s.serie_post || { valenza: [], arousal: [] },
        );
        _calCharts.push(...charts);
    }
}

document.getElementById('btn-close-results').addEventListener('click', () => {
    document.getElementById('panel-results').classList.remove('visible');
    _showRestartUi();
    if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ tipo: 'risultati_visti' }));
    }
});
document.getElementById('btn-restart')?.addEventListener('click', () => {
    document.getElementById('ui-restart')?.classList.add('hidden');
    _restartFromStart();
});
document.getElementById('btn-calendar-open').addEventListener('click', () => {
    document.getElementById('panel-results').classList.remove('visible');
    openCalendar();
});

// ------------------------------------------------------------------ Calendar
async function openCalendar() {
    if (_currentUser) {
        try { _calSessions = await loadCalendarSessions(_currentUser.uid); }
        catch (_) { _calSessions = {}; }
    }
    renderCalendar();
    document.getElementById('modal-calendar').classList.add('visible');
}

function renderCalendar() {
    const anno = _calMonth.getFullYear();
    const mese = _calMonth.getMonth();
    document.getElementById('cal-month-title').textContent =
        new Date(anno, mese, 1).toLocaleDateString('en-US', { month: 'long', year: 'numeric' });

    const grid  = document.getElementById('cal-grid');
    grid.innerHTML = '';

    const primoGiorno  = (new Date(anno, mese, 1).getDay() + 6) % 7; // lun=0
    const ultimoGiorno = new Date(anno, mese + 1, 0).getDate();
    const todayStr      = new Date().toISOString().split('T')[0];

    for (let i = 0; i < primoGiorno; i++) {
        grid.appendChild(document.createElement('div')).className = 'cal-cell';
    }
    for (let g = 1; g <= ultimoGiorno; g++) {
        const data = `${anno}-${String(mese + 1).padStart(2,'0')}-${String(g).padStart(2,'0')}`;
        const cell = document.createElement('div');
        cell.className = 'cal-cell';
        cell.textContent = g;
        if (data === todayStr) cell.classList.add('today');
        if (_calSessions[data]) {
            cell.classList.add('has-session');
            cell.title = `${_calSessions[data].length} session(s)`;
            cell.addEventListener('click', () => showDayDetail(data, cell));
        }
        grid.appendChild(cell);
    }
    document.getElementById('cal-detail').innerHTML = '';
    _destroyCalendarCharts();
}

function showDayDetail(data, cell) {
    document.querySelectorAll('.cal-cell.selected').forEach(c => c.classList.remove('selected'));
    cell.classList.add('selected');

    _destroyCalendarCharts();

    const sessioni = _calSessions[data] || [];
    const div = document.getElementById('cal-detail');
    const fmt = new Date(data + 'T12:00:00').toLocaleDateString('en-US',
        { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' });

    if (!sessioni.length) {
        div.innerHTML = `<div style="color:rgba(255,255,255,0.55); font-size:0.75rem; margin-bottom:0.75rem; letter-spacing:0.06em; text-transform:uppercase">${fmt}</div>
            <p>No sessions recorded for this day.</p>`;
        return;
    }

    div.innerHTML = `<div style="color:rgba(255,255,255,0.55); font-size:0.75rem; margin-bottom:0.75rem; letter-spacing:0.06em; text-transform:uppercase">${fmt}</div>` +
        sessioni.map(s => _sessionResultHtml(s, s.id || `s${Math.random().toString(36).slice(2, 8)}`)).join('');

    _renderCalendarCharts(sessioni);
}

document.getElementById('cal-prev').addEventListener('click', () => {
    _calMonth = new Date(_calMonth.getFullYear(), _calMonth.getMonth() - 1, 1);
    renderCalendar();
});
document.getElementById('cal-next').addEventListener('click', () => {
    _calMonth = new Date(_calMonth.getFullYear(), _calMonth.getMonth() + 1, 1);
    renderCalendar();
});
document.getElementById('btn-close-calendar').addEventListener('click', () => {
    _destroyCalendarCharts();
    document.getElementById('modal-calendar').classList.remove('visible');
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
        if (statoEl) statoEl.textContent = 'ready';
        onFine?.();
    };
    rec.onerror = () => {
        btnMic.classList.remove('rec');
        if (statoEl) statoEl.textContent = 'microphone error';
    };

    btnMic.addEventListener('click', () => {
        if (btnMic.classList.contains('rec')) {
            rec.stop();
        } else {
            base = textarea.value;
            try {
                rec.start();
                btnMic.classList.add('rec');
                if (statoEl) statoEl.textContent = 'listening…';
            } catch (_) {}
        }
    });
}
