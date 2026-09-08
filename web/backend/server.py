"""
IN-Motion Web — FastAPI/WebSocket backend.

The browser connects on /ws, sends the story as the first message,
then each frame sends face points. The esperienza.py state machine
runs here and commands are sent back to the browser.

Start:
    cd web/backend
    pip install -r requirements.txt
    uvicorn "server:app" --reload
"""
import asyncio
import json
import os
import queue
import sys
import threading
import time
import types
from pathlib import Path

from dotenv import load_dotenv

# Load .env from the project root (two levels above backend/)
_ENV_PATH = Path(__file__).resolve().parent.parent.parent / '.env'
load_dotenv(_ENV_PATH)

import anthropic
from fastapi import Body, FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

# ------------------------------------------------------------------ paths
BACKEND = Path(__file__).resolve().parent
WEB = BACKEND.parent
VISUALS = WEB.parent / "visuals"
FRONTEND = WEB / "frontend"
LIBRERIA = VISUALS / "musica_libreria"
ASSETS = WEB / "assets"

# ------------------------------------------------------------------ inject stubs BEFORE importing esperienza.py
# esperienza.py does `import musica`, `import stacco` and `import voce`: we
# replace them with web versions that queue JSON events for the browser
# instead of using sounddevice.
#
# THE ORDER OF THESE LINES IS PART OF THE MECHANISM, not style. VoceWS is no
# longer an empty stub: it INHERITS from the real Voce, to reuse cache, voice
# selection and durations. So it must be imported in a precise window —
#   after  visuals/ is on the path (otherwise `import voce` finds nothing)
#   after  the musica stub exists (voce.py does `import musica` at the top)
#   before the name "voce" is taken by the stub (otherwise VoceWS
#          would inherit from itself)
# Moving any of these lines breaks startup, and the error does not say why.
from musica_ws import MusicaWS, SAMPLE_RATE as _SR  # noqa: E402
from stacco_ws import StaccoWS                       # noqa: E402

_musica_stub = types.ModuleType("musica")
_musica_stub.SAMPLE_RATE = _SR
_musica_stub.Music = MusicaWS
sys.modules["musica"] = _musica_stub

_stacco_stub = types.ModuleType("stacco")
_stacco_stub.Stacco = StaccoWS
sys.modules["stacco"] = _stacco_stub

# Put visuals modules on the path (esperienza, testi, occhi, mandala, voce…)
sys.path.insert(0, str(VISUALS))

# now, and not earlier: here `import voce` finds the real one
from voce_ws import VoceWS                           # noqa: E402

_voce_stub = types.ModuleType("voce")
_voce_stub.Voce = VoceWS
sys.modules["voce"] = _voce_stub

# esperienza.py does `import scena` at top level; that module talks to
# TouchDesigner via python-osc. On the web we never need OSC — stub scena
# with ScenaWS before importing esperienza so Windows/macOS/Linux web installs
# do not require pythonosc.
from scena_ws import ScenaWS                         # noqa: E402
_scena_stub = types.ModuleType("scena")
_scena_stub.Scena = ScenaWS
_scena_stub.TEMPO_DI_PREPARAZIONE = ScenaWS.TEMPO_DI_PREPARAZIONE
sys.modules["scena"] = _scena_stub

import esperienza as _exp_mod  # noqa: E402

from ascolto_ws import AscoltoWS  # noqa: E402

# ------------------------------------------------------------------ app
app = FastAPI()

# CORS: let the browser call /analisi (same host, but needed
# for localhost during development)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["POST"],
    allow_headers=["*"],
)

app.mount("/musica", StaticFiles(directory=str(LIBRERIA)), name="musica")
app.mount("/assets", StaticFiles(directory=str(ASSETS)), name="assets")


# ------------------------------------------------------------------ emotion analysis
_ANTHROPIC = anthropic.Anthropic()   # reads ANTHROPIC_API_KEY from env

_PROMPT_ANALISI = """\
You are an expert in emotion psychology and nonverbal communication.

User profile:
- Name: {nome}
- Age: {eta}
- Gender: {sesso}
- Meditation goal: {obiettivo}

During the experience ({durata} min) the user shared:
"{racconto}"

Real-time facial recognition measured:
- Mean valence: {valenza:.2f}  (-1 = negative, +1 = positive)
- Mean arousal: {arousal:.2f}  (0 = calm, 1 = activated)
- Authentic Duchenne smile: {duchenne:.2f}
- Brow tension: {brow:.2f}
- Emotional arc: {arco}  (how valence changed over time)
- Samples collected: {n_campioni}

Take the profile and stated goal into account to personalize the analysis.
Consider nuances such as irony, suppressed anger, masked sadness, ambivalence.

Reply ONLY with a valid JSON object, no extra text:
{{
  "emozione_primaria": "main emotion name",
  "sfumature": ["optional nuance 1", "optional nuance 2"],
  "intensita": 0.0,
  "interpretazione": "brief analysis in 2-3 sentences personalized for {nome}"
}}
"""

@app.post("/analisi")
async def analisi_emozioni(body: dict = Body(...)):
    """Receive facial data + story + profile, call Claude, return emotion analysis."""
    racconto      = (body.get("racconto") or "")[:500]
    riflessione   = (body.get("riflessione") or "")[:400]
    emozioni      = body.get("emozioni") or {}
    emozioni_post = body.get("emozioni_post") or {}
    durata        = body.get("durata_minuti", 0)
    profilo       = body.get("profilo") or {}

    # Enrich the prompt if there is also a post reflection
    contesto_post = ""
    if riflessione:
        vPost = emozioni_post.get("valenza_media", None)
        aPost = emozioni_post.get("arousal_medio", None)
        contesto_post = f"""
After meditation the user reflected:
"{riflessione}"
Post-meditation facial data:
- Valence: {vPost:.2f if vPost is not None else 'n/a'}
- Arousal: {aPost:.2f if aPost is not None else 'n/a'}
"""

    prompt = _PROMPT_ANALISI.format(
        nome        = profilo.get("nome", "user"),
        eta         = profilo.get("eta", "?"),
        sesso       = profilo.get("sesso", "unspecified"),
        obiettivo   = profilo.get("obiettivo", "(unspecified)")[:300],
        racconto    = racconto or "(not provided)",
        durata      = durata,
        valenza     = emozioni.get("valenza_media",   0.0),
        arousal     = emozioni.get("arousal_medio",   0.0),
        duchenne    = emozioni.get("sorriso_genuino", 0.0),
        brow        = emozioni.get("tensione_brow",   0.0),
        arco        = emozioni.get("arco_emotivo",    "unknown"),
        n_campioni  = emozioni.get("n_campioni",       0),
    ) + contesto_post

    try:
        risposta = _ANTHROPIC.messages.create(
            model="claude-opus-4-5",
            max_tokens=400,
            messages=[{"role": "user", "content": prompt}],
        )
        testo = risposta.content[0].text.strip()
        # Extract JSON from the response
        import re
        match = re.search(r'\{.*\}', testo, re.DOTALL)
        analisi = json.loads(match.group()) if match else {"interpretazione": testo}
    except Exception as e:
        print(f"analisi: errore Claude ({e})")
        analisi = {"interpretazione": "", "errore": str(e)}

    return JSONResponse({"analisi": analisi, "emozioni": emozioni})


@app.get("/firebase-config")
async def firebase_config():
    """Expose the Firebase config read from .env to the frontend."""
    return JSONResponse({
        "apiKey":            os.getenv("FIREBASE_API_KEY", ""),
        "authDomain":        os.getenv("FIREBASE_AUTH_DOMAIN", ""),
        "projectId":         os.getenv("FIREBASE_PROJECT_ID", ""),
        "storageBucket":     os.getenv("FIREBASE_STORAGE_BUCKET", ""),
        "messagingSenderId": os.getenv("FIREBASE_MESSAGING_SENDER_ID", ""),
        "appId":             os.getenv("FIREBASE_APP_ID", ""),
    })


@app.get("/voce/{nome}")
def voice_clip(nome: str):
    """A spoken-guide clip, from the cache shared with the desktop
    version (visuals/voce_cache/).

    The name is the fingerprint that computes it: sha1 of signature + spoken
    text, so it is not guessable and cannot be reached from outside. Still
    re-checked — a name containing path separators would escape the folder,
    and that is the kind of hole you do not leave open just because the
    server runs locally."""
    if not nome.endswith(".wav") or "/" in nome or "\\" in nome or ".." in nome:
        return JSONResponse({"errore": "nome non valido"}, status_code=400)
    percorso = (VISUALS / "voce_cache" / nome).resolve()
    if not percorso.is_file() or (VISUALS / "voce_cache").resolve() not in percorso.parents:
        return JSONResponse({"errore": "clip non trovata"}, status_code=404)
    return FileResponse(str(percorso), media_type="audio/wav")


@app.get("/mandala/ultimo")
def latest_mandala():
    """The mandala from the session that just ended, to take away.

    The file already exists: _salva_immagine() in esperienza.py writes it in a
    thread as soon as parameters are decided, and since esperienza.py is shared
    it does so here too. Only the way to fetch it was missing — on screen the
    mandala is 13,664 moving particles; this is the same drawing with 260,000
    still particles, at 2400x2400.

    Serve the most recent: the app is local and one session at a time,
    so the most recent is the one from whoever just finished.
    """
    cartella = VISUALS / "mandala"
    if not cartella.is_dir():
        return JSONResponse({"errore": "nessun mandala"}, status_code=404)
    file = sorted(cartella.glob("mandala_*.png"), key=lambda f: f.stat().st_mtime)
    if not file:
        return JSONResponse({"errore": "nessun mandala"}, status_code=404)
    ultimo = file[-1]
    return FileResponse(str(ultimo), media_type="image/png", filename=ultimo.name)


# Frontend files are served with NO CACHE, and that is not laziness.
#
# The browser caches ES modules aggressively and does not revalidate them
# even when you change the page address. Edit a file and reload and you end
# up with half new modules and half old — and if a new one imports something
# the old copy does not have yet, the import fails, app.js NEVER starts, and
# no error appears on screen: you only see an interface where buttons do
# nothing. That symptom looks nothing like the cause, and it already cost
# an evening.
#
# There is no bandwidth to save here: the server is on the same machine.
_SENZA_CACHE = {"Cache-Control": "no-store, must-revalidate"}


@app.get("/")
async def root():
    return FileResponse(str(FRONTEND / "index.html"), headers=_SENZA_CACHE)

@app.get("/{path:path}")
async def static(path: str):
    target = FRONTEND / path
    if target.exists() and target.is_file():
        return FileResponse(str(target), headers=_SENZA_CACHE)
    return FileResponse(str(FRONTEND / "index.html"), headers=_SENZA_CACHE)

# ------------------------------------------------------------------ helpers
RACCONTO_DEFAULT = "today mi sento agitato e non riesco a fermare i pensieri"


def _enrich_story(racconto: str, profilo: dict) -> str:
    if not profilo:
        return racconto
    nome = profilo.get("nome", "")
    obiettivo = profilo.get("obiettivo", "")
    if obiettivo:
        return f"{racconto}\n[Profile: {nome}, goal: {obiettivo}]"
    return racconto


class _Point:
    """Light wrapper so [[x,y,z]] coordinates are compatible
    with occhi.py and movimento.py modules that expect .x .y .z."""
    __slots__ = ("x", "y", "z")

    def __init__(self, xyz):
        self.x = float(xyz[0])
        self.y = float(xyz[1])
        self.z = float(xyz[2])


def _adapt_points(lista):
    if not lista:
        return None
    return [_Point(p) for p in lista]


class _Session:
    """Shared state between the experience thread and the WebSocket loop."""

    def __init__(self):
        self._punti = None
        self._blink = None
        self._lock = threading.Lock()
        self._audio: queue.SimpleQueue = queue.SimpleQueue()
        self.riflessione_inviata = threading.Event()
        self.risultati_visti = threading.Event()

    def set_punti(self, raw, blink=None):
        with self._lock:
            self._punti = raw
            if blink is not None:
                try:
                    self._blink = float(blink)
                except (TypeError, ValueError):
                    pass

    def get_punti(self):
        with self._lock:
            return self._punti

    def get_blink(self):
        with self._lock:
            return self._blink

    def aggiungi_audio(self, dati: bytes):
        self._audio.put(dati)

    def consuma_audio(self):
        try:
            return self._audio.get_nowait()
        except queue.Empty:
            return None

    def svuota_audio(self):
        while True:
            try:
                self._audio.get_nowait()
            except queue.Empty:
                break


# ------------------------------------------------------------------ WebSocket
@app.websocket("/ws")
async def ws_handler(ws: WebSocket):
    await ws.accept()

    coda: queue.SimpleQueue = queue.SimpleQueue()
    stato = _Session()

    scena = ScenaWS(coda)
    musica = MusicaWS(coda, "principale")
    tappeto = MusicaWS(coda, "tappeto")
    ascolto = AscoltoWS(coda, stato)

    # 1. Ready, then wait for "start" or "racconto" (5 min timeout)
    await ws.send_json({"tipo": "pronto"})
    racconto = ""
    profilo_utente: dict = {}
    try:
        msg = await asyncio.wait_for(ws.receive_json(), timeout=300.0)
        tipo = msg.get("tipo")
        profilo_utente = msg.get("profilo") or {}
        if tipo == "racconto":
            racconto = msg.get("testo") or RACCONTO_DEFAULT
        elif tipo not in ("start", "inizia"):
            print(f"racconto: messaggio inatteso ({tipo!r}), uso default")
            racconto = RACCONTO_DEFAULT
    except Exception as exc:
        print(f"racconto: errore/timeout ({exc}), uso default")
        racconto = RACCONTO_DEFAULT

    racconto = _enrich_story(racconto, profilo_utente)
    print(f'racconto: "{racconto[:120]}"' if racconto else "racconto: (in attesa dal browser)")

    # 2. Start the experience loop in a separate thread
    stop_ev = threading.Event()
    esp_ref: dict = {"esp": None}

    def _loop():
        try:
            esp = _exp_mod.Esperienza(
                scena, racconto, ascolto, musica=musica, tappeto=tappeto,
                voce=VoceWS(coda, (tappeto, musica)),
                sincronia=stato,
                nome=(profilo_utente.get("nome") or "").strip() or None,
            )
            esp_ref["esp"] = esp
            # Like visuals/main.py: synthesize fixed lines in the background.
            # With an empty voce_cache, without this the clips do not exist and di() stays mute.
            try:
                esp.prepara_voce()
            except Exception as exc:
                print(f"voce: prepara fallita ({exc}) — si prosegue muti sulle scritte fisse")
            try:
                esp.prepara_tappeto()
            except Exception as exc:
                print(f"tappeto: prepara fallita ({exc})")
            esp.avvia(time.time())
            while not esp.finita and not stop_ev.is_set():
                punti = _adapt_points(stato.get_punti())
                esp.aggiorna(time.time(), punti, blink=stato.get_blink())
                time.sleep(1 / 30)
        except Exception as exc:
            import traceback
            print(f"esperienza: {exc}")
            traceback.print_exc()
        finally:
            coda.put({"tipo": "fine"})

    threading.Thread(target=_loop, daemon=True).start()

    # 3. WebSocket pump: drain the outbound queue, receive inbound messages
    try:
        while True:
            # Send all pending events to the browser
            while True:
                try:
                    await ws.send_json(coda.get_nowait())
                except queue.Empty:
                    break

            # Wait for the next message (short timeout so we do not block)
            try:
                raw = await asyncio.wait_for(ws.receive(), timeout=0.020)
            except asyncio.TimeoutError:
                continue

            if raw["type"] == "websocket.disconnect":
                break
            if raw["type"] != "websocket.receive":
                continue

            if raw.get("bytes"):
                # Raw audio from MediaRecorder (WebM/Opus)
                stato.aggiungi_audio(raw["bytes"])
            elif raw.get("text"):
                try:
                    dati = json.loads(raw["text"])
                    if dati.get("tipo") == "frame":
                        stato.set_punti(dati.get("punti"), blink=dati.get("blink"))
                    elif dati.get("tipo") == "racconto":
                        testo = _enrich_story(
                            dati.get("testo") or RACCONTO_DEFAULT,
                            dati.get("profilo") or profilo_utente,
                        )
                        esp = esp_ref.get("esp")
                        if esp:
                            esp.imposta_racconto(testo)
                            print(f'racconto aggiornato: "{testo[:120]}"')
                    elif dati.get("tipo") == "riflessione_post":
                        stato.riflessione_inviata.set()
                    elif dati.get("tipo") == "risultati_visti":
                        stato.risultati_visti.set()
                except (json.JSONDecodeError, Exception):
                    pass

    except WebSocketDisconnect:
        pass
    finally:
        stop_ev.set()
