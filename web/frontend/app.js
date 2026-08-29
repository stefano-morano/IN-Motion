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
         caricaProfilo, salvaProfilo } from './firebase.js';

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

const WS_URL = `ws://${location.host}/ws`;
const stato = document.getElementById('stato');
const ui    = document.getElementById('ui');

// ------------------------------------------------------------------ audio
class AudioManager {
    constructor() {
        this.ctx = null;
        this._sorgenti = {
            principale: { node: null, gainVol: null, gainAtt: null, volume: 0 },
            tappeto:    { node: null, gainVol: null, gainAtt: null, volume: 0 },
        };
        this._cache = new Map();
        this._recorder = null;
        this._audioChunks = [];
        this._onAudioReady = null;
    }

    async _ensure() {
        if (!this.ctx) {
            this.ctx = new AudioContext({ sampleRate: 44100 });
            this._masterGain = this.ctx.createGain();
            this._masterGain.connect(this.ctx.destination);
        }
        if (this.ctx.state === 'suspended') await this.ctx.resume();
    }

    async _carica(url) {
        if (this._cache.has(url)) return this._cache.get(url);
        const r   = await fetch(url);
        const arr = await r.arrayBuffer();
        const buf = await this.ctx.decodeAudioData(arr);
        this._cache.set(url, buf);
        return buf;
    }

    async handle(msg) {
        const { azione, sorgente: nome, emozione, fade, volume, durata, val } = msg;
        const s = this._sorgenti[nome];
        if (!s) return;

        if (azione === 'play') {
            await this._ensure();
            this._stop(nome);
            const idx = Math.floor(Math.random() * 4).toString().padStart(2, '0');
            const url = `/musica/${emozione}/${emozione}_${idx}.wav`;
            try {
                const buf = await this._carica(url);
                s.gainVol = this.ctx.createGain();
                s.gainAtt = this.ctx.createGain();
                s.gainVol.gain.value = 0;
                s.gainAtt.gain.value = 1;
                s.gainVol.connect(s.gainAtt).connect(this._masterGain);
                s.node = this.ctx.createBufferSource();
                s.node.buffer = buf;
                s.node.loop = true;
                s.node.connect(s.gainVol);
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

    toggleMute() {
        if (!this.ctx || !this._masterGain) return;
        this._muted = !this._muted;
        const t = this.ctx.currentTime;
        this._masterGain.gain.cancelScheduledValues(t);
        this._masterGain.gain.setValueAtTime(this._masterGain.gain.value, t);
        this._masterGain.gain.linearRampToValueAtTime(this._muted ? 0 : 1, t + 0.3);
        return this._muted;
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

    _campana(chiusura, ritardo = 2.2) {
        if (!this.ctx) return;
        // Frequenza fondamentale: la grave per chiusura, una quinta sopra per apertura
        const freq = chiusura ? 220 : 330;
        // Tre parziali non armoniche
        const parziali = [[1.0, 0.7], [2.71, 0.25], [5.18, 0.08]];
        const t0 = this.ctx.currentTime + ritardo;
        for (const [mult, amp] of parziali) {
            const osc = this.ctx.createOscillator();
            const gain = this.ctx.createGain();
            osc.frequency.value = freq * mult;
            osc.type = 'sine';
            gain.gain.setValueAtTime(amp * 0.06, t0);
            gain.gain.exponentialRampToValueAtTime(0.0001, t0 + 3.5);
            osc.connect(gain).connect(this.ctx.destination);
            osc.start(t0);
            osc.stop(t0 + 3.6);
        }
    }

    _stop(nome) {
        const s = this._sorgenti[nome];
        if (s.node) { try { s.node.stop(); } catch (_) {} s.node = null; }
    }

    // ---- registrazione microfono ----
    apriMicrofono() {
        // Solo prepara il permesso, la registrazione parte con inizia()
    }

    async inizia() {
        try {
            const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
            this._audioChunks = [];
            this._recorder = new MediaRecorder(stream, { mimeType: 'audio/webm;codecs=opus' });
            this._recorder.ondataavailable = e => { if (e.data.size > 0) this._audioChunks.push(e.data); };
            this._recorder.onstop = () => {
                const blob = new Blob(this._audioChunks, { type: 'audio/webm' });
                blob.arrayBuffer().then(buf => {
                    if (ws && ws.readyState === WebSocket.OPEN) {
                        ws.send(buf);
                    }
                });
                // Chiude i track del microfono
                stream.getTracks().forEach(t => t.stop());
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

// ------------------------------------------------------------------ WebSocket
function connect() {
    stato.textContent = 'connessione...';
    ws = new WebSocket(WS_URL);

    ws.onopen = () => { stato.textContent = 'connesso'; };

    ws.onmessage = async (ev) => {
        // I messaggi audio arrivano come Blob/ArrayBuffer, non JSON
        if (typeof ev.data !== 'string') return;

        let msg;
        try { msg = JSON.parse(ev.data); }
        catch (e) { console.warn('ws: messaggio non-JSON ignorato'); return; }

        const { tipo } = msg;
        console.log('ws ←', tipo, msg.scena || msg.azione || '');

        if (tipo === 'pronto') {
            // Mostra la UI per inserire il racconto
            ui.classList.remove('nascosto');
            stato.textContent = 'pronto';

        } else if (tipo === 'prepara') {
            // Precalcola le posizioni delle scritte
            const t0 = performance.now();
            logica.prepara_testi(msg.frasi, (frase, n) => campionaTesto(frase, n));
            console.log(`prepara: ${msg.frasi.length} scritte in ${(performance.now()-t0).toFixed(0)}ms`);

        } else if (tipo === 'prepara_mandala') {
            logica.prepara_mandala(msg.petali, msg.anelli, msg.tonalita, msg.seed);

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

        } else if (tipo === 'stacco') {
            audio.stacco(msg.chiusura, msg.discesa, msg.respiro, msg.ritorno);

        } else if (tipo === 'stacco_annulla') {
            audio.staccoAnnulla();

        } else if (tipo === 'ascolto') {
            if (msg.azione === 'apri') {
                audio.apriMicrofono();
            } else if (msg.azione === 'inizia') {
                await audio.inizia();
            } else if (msg.azione === 'ferma') {
                audio.ferma();
            }
        }
    };

    ws.onclose = () => {
        stato.textContent = 'disconnesso';
        // Analisi emotiva + salvataggio Firestore al termine della sessione
        if (_utenteCorrente && _tInizio) {
            const durata = Math.round((Date.now() - _tInizio) / 1000 / 60);
            const reportFacciale = _analizzatore.report();
            _analizzatore.ferma();
            _tInizio = null;

            // Chiama /analisi (Claude interpreta i dati facciali)
            const payload = {
                racconto:       _testoSessione.slice(0, 300),
                durata_minuti:  durata,
                emozioni:       reportFacciale || {},
                profilo:        _profiloUtente || {},   // dati utente per personalizzare
            };
            fetch('/analisi', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload),
            })
            .then(r => r.json())
            .then(({ analisi, emozioni }) => {
                console.log('analisi emotiva:', analisi);
                salvaSessione(_utenteCorrente.uid, {
                    ...payload,
                    emozioni_facciali: emozioni,
                    analisi_claude:    analisi,
                    completata:        durata >= 2,
                });
            })
            .catch(e => {
                console.warn('analisi: errore', e);
                // Salva comunque senza analisi
                salvaSessione(_utenteCorrente.uid, { ...payload, completata: durata >= 2 });
            });
        }
        setTimeout(connect, 2000);
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
                    if (_tInizio) _analizzatore.aggiorna(blendshapes);
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
        const { posizioni, colori } = logica.aggiorna(landmarks, ora);
        renderer.aggiorna(posizioni, colori);
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
    connect();

    requestAnimationFrame(loop);
}

// ------------------------------------------------------------------ Firebase auth
const loginOverlay   = document.getElementById('login-overlay');
const profiloOverlay = document.getElementById('profilo-overlay');
const utenteInfo     = document.getElementById('utente-info');
const utenteNome     = document.getElementById('utente-nome');
const utenteAvatar   = document.getElementById('utente-avatar');
const loginErrore    = document.getElementById('login-errore');
const loginOk        = document.getElementById('login-ok');

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
        }
        utenteInfo.classList.add('visibile');

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
            utenteInfo.classList.remove('visibile');
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

// ------------------------------------------------------------------ UI
document.getElementById('inizia').addEventListener('click', async () => {
    const testo = document.getElementById('racconto').value.trim();
    _testoSessione = testo;
    _tInizio = Date.now();
    _analizzatore.inizia();   // avvia la raccolta blend shapes
    ui.classList.add('nascosto');
    stato.textContent = 'esperienza in corso';
    if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({
            tipo:    'racconto',
            testo,
            profilo: _profiloUtente || {},   // nome, età, sesso, obiettivo → personalizzazione AI
        }));
    }
    try { await audio._ensure(); } catch (_) {}
});

document.getElementById('racconto').addEventListener('keydown', e => {
    if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        document.getElementById('inizia').click();
    }
});

// Pulsante muto
document.getElementById('btn-muto').addEventListener('click', async () => {
    try { await audio._ensure(); } catch (_) {}
    const muted = audio.toggleMute();
    const btn = document.getElementById('btn-muto');
    if (muted) {
        btn.textContent = '🔇 Muto';
        btn.classList.add('attivo');
    } else {
        btn.textContent = '🔊 Musica';
        btn.classList.remove('attivo');
    }
});

// Pulsante info / modal
const modalInfo = document.getElementById('modal-info');
document.getElementById('btn-info').addEventListener('click', () => {
    modalInfo.classList.add('visibile');
});
document.getElementById('modal-chiudi').addEventListener('click', () => {
    modalInfo.classList.remove('visibile');
});
// Chiudi cliccando fuori dal box
modalInfo.addEventListener('click', e => {
    if (e.target === modalInfo) modalInfo.classList.remove('visibile');
});

init();
