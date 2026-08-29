"""
IN-Motion Web — backend FastAPI/WebSocket.

Il browser si collega su /ws, manda il racconto come primo messaggio,
e poi ad ogni fotogramma manda i punti del viso. Qui gira la macchina
a stati di esperienza.py e i comandi vengono rispediti al browser.

Avvio:
    cd web/backend
    pip install -r requirements.txt
    uvicorn server:app --reload
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

# Carica .env dalla root del progetto (due livelli sopra backend/)
_ENV_PATH = Path(__file__).resolve().parent.parent.parent / '.env'
load_dotenv(_ENV_PATH)

import anthropic
from fastapi import Body, FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

# ------------------------------------------------------------------ percorsi
BACKEND = Path(__file__).resolve().parent
WEB = BACKEND.parent
VISUALS = WEB.parent / "visuals"
FRONTEND = WEB / "frontend"
LIBRERIA = VISUALS / "musica_libreria"

# ------------------------------------------------------------------ inietta stub PRIMA di importare esperienza.py
# esperienza.py fa `import musica` e `import stacco`: li sostituiamo
# con versioni web che accodano eventi JSON invece di usare sounddevice.
from musica_ws import MusicaWS, SAMPLE_RATE as _SR  # noqa: E402
from stacco_ws import StaccoWS                       # noqa: E402

_musica_stub = types.ModuleType("musica")
_musica_stub.SAMPLE_RATE = _SR
_musica_stub.Music = MusicaWS
sys.modules["musica"] = _musica_stub

_stacco_stub = types.ModuleType("stacco")
_stacco_stub.Stacco = StaccoWS
sys.modules["stacco"] = _stacco_stub

# Porta i moduli dei visuals nel path (esperienza, testi, occhi, mandala, …)
sys.path.insert(0, str(VISUALS))

import esperienza as _exp_mod  # noqa: E402

from scena_ws import ScenaWS      # noqa: E402
from ascolto_ws import AscoltoWS  # noqa: E402

# ------------------------------------------------------------------ app
app = FastAPI()

# CORS: permette al browser di chiamare /analisi (stesso host, ma necessario
# per localhost durante lo sviluppo)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["POST"],
    allow_headers=["*"],
)

app.mount("/musica", StaticFiles(directory=str(LIBRERIA)), name="musica")


# ------------------------------------------------------------------ analisi emotiva
_ANTHROPIC = anthropic.Anthropic()   # legge ANTHROPIC_API_KEY dall'env

_PROMPT_ANALISI = """\
Sei un esperto di psicologia delle emozioni e comunicazione non verbale.

Profilo dell'utente:
- Nome: {nome}
- Età: {eta} anni
- Sesso: {sesso}
- Obiettivo di meditazione: {obiettivo}

Durante l'esperienza ({durata} min) l'utente ha raccontato:
"{racconto}"

Il riconoscimento facciale in tempo reale ha misurato:
- Valenza media: {valenza:.2f}  (-1 = negativa, +1 = positiva)
- Arousal medio: {arousal:.2f}  (0 = calmo, 1 = attivato)
- Sorriso autentico Duchenne: {duchenne:.2f}
- Tensione sopraccigliare: {brow:.2f}
- Arco emotivo: {arco}  (come è cambiata la valenza nel tempo)
- Campioni rilevati: {n_campioni}

Tieni conto del profilo e dell'obiettivo dichiarato per personalizzare l'analisi.
Considera sfumature come ironia, rabbia repressa, tristezza mascherata, ambivalenza.

Rispondi SOLO con un oggetto JSON valido, senza testo aggiuntivo:
{{
  "emozione_primaria": "nome emozione principale",
  "sfumature": ["eventuale sfumatura 1", "eventuale sfumatura 2"],
  "intensita": 0.0,
  "interpretazione": "analisi breve in 2-3 frasi personalizzata per {nome}"
}}
"""

@app.post("/analisi")
async def analisi_emozioni(body: dict = Body(...)):
    """Riceve dati facciali + racconto + profilo, chiama Claude, restituisce analisi emotiva."""
    racconto  = (body.get("racconto") or "")[:500]
    emozioni  = body.get("emozioni") or {}
    durata    = body.get("durata_minuti", 0)
    profilo   = body.get("profilo") or {}

    prompt = _PROMPT_ANALISI.format(
        nome        = profilo.get("nome", "utente"),
        eta         = profilo.get("eta", "?"),
        sesso       = profilo.get("sesso", "non specificato"),
        obiettivo   = profilo.get("obiettivo", "(non specificato)")[:300],
        racconto    = racconto or "(non fornito)",
        durata      = durata,
        valenza     = emozioni.get("valenza_media",   0.0),
        arousal     = emozioni.get("arousal_medio",   0.0),
        duchenne    = emozioni.get("sorriso_genuino", 0.0),
        brow        = emozioni.get("tensione_brow",   0.0),
        arco        = emozioni.get("arco_emotivo",    "sconosciuto"),
        n_campioni  = emozioni.get("n_campioni",       0),
    )

    try:
        risposta = _ANTHROPIC.messages.create(
            model="claude-opus-4-5",
            max_tokens=400,
            messages=[{"role": "user", "content": prompt}],
        )
        testo = risposta.content[0].text.strip()
        # Estrai il JSON dalla risposta
        import re
        match = re.search(r'\{.*\}', testo, re.DOTALL)
        analisi = json.loads(match.group()) if match else {"interpretazione": testo}
    except Exception as e:
        print(f"analisi: errore Claude ({e})")
        analisi = {"interpretazione": "", "errore": str(e)}

    return JSONResponse({"analisi": analisi, "emozioni": emozioni})


@app.get("/firebase-config")
async def firebase_config():
    """Espone la configurazione Firebase letta dal .env al frontend."""
    return JSONResponse({
        "apiKey":            os.getenv("FIREBASE_API_KEY", ""),
        "authDomain":        os.getenv("FIREBASE_AUTH_DOMAIN", ""),
        "projectId":         os.getenv("FIREBASE_PROJECT_ID", ""),
        "storageBucket":     os.getenv("FIREBASE_STORAGE_BUCKET", ""),
        "messagingSenderId": os.getenv("FIREBASE_MESSAGING_SENDER_ID", ""),
        "appId":             os.getenv("FIREBASE_APP_ID", ""),
    })


@app.get("/")
async def root():
    return FileResponse(str(FRONTEND / "index.html"))

@app.get("/{path:path}")
async def static(path: str):
    target = FRONTEND / path
    if target.exists() and target.is_file():
        return FileResponse(str(target))
    return FileResponse(str(FRONTEND / "index.html"))

# ------------------------------------------------------------------ helpers
RACCONTO_DEFAULT = "oggi mi sento agitato e non riesco a fermare i pensieri"


class _Punto:
    """Wrapper leggero per rendere le coordinate [[x,y,z]] compatibili
    con i moduli occhi.py e movimento.py che si aspettano .x .y .z."""
    __slots__ = ("x", "y", "z")

    def __init__(self, xyz):
        self.x = float(xyz[0])
        self.y = float(xyz[1])
        self.z = float(xyz[2])


def _adatta_punti(lista):
    if not lista:
        return None
    return [_Punto(p) for p in lista]


class _Sessione:
    """Stato condiviso fra il thread dell'esperienza e il loop WebSocket."""

    def __init__(self):
        self._punti = None
        self._lock = threading.Lock()
        self._audio: queue.SimpleQueue = queue.SimpleQueue()

    def set_punti(self, raw):
        with self._lock:
            self._punti = raw

    def get_punti(self):
        with self._lock:
            return self._punti

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
    stato = _Sessione()

    scena = ScenaWS(coda)
    musica = MusicaWS(coda, "principale")
    tappeto = MusicaWS(coda, "tappeto")
    ascolto = AscoltoWS(coda, stato)

    # 1. Aspetta il racconto dal browser (timeout 60s)
    await ws.send_json({"tipo": "pronto"})
    racconto = RACCONTO_DEFAULT
    profilo_utente: dict = {}
    try:
        msg = await asyncio.wait_for(ws.receive_json(), timeout=60.0)
        if msg.get("tipo") == "racconto":
            racconto       = msg.get("testo") or RACCONTO_DEFAULT
            profilo_utente = msg.get("profilo") or {}
    except Exception as exc:
        print(f"racconto: errore/timeout ({exc}), uso default")

    # Arricchisce il testo con il contesto del profilo per una meditazione più personalizzata
    if profilo_utente:
        nome      = profilo_utente.get("nome", "")
        obiettivo = profilo_utente.get("obiettivo", "")
        if obiettivo:
            racconto = f"{racconto}\n[Profilo: {nome}, obiettivo: {obiettivo}]"

    print(f'racconto: "{racconto[:120]}"')

    # 2. Avvia il ciclo dell'esperienza in un thread separato
    #    (esperienza.py è sincrona: non gira in asyncio)
    stop_ev = threading.Event()

    def _loop():
        try:
            esp = _exp_mod.Esperienza(
                scena, racconto, ascolto, musica=musica, tappeto=tappeto
            )
            esp.avvia(time.time())
            while not esp.finita and not stop_ev.is_set():
                punti = _adatta_punti(stato.get_punti())
                esp.aggiorna(time.time(), punti)
                time.sleep(1 / 30)
        except Exception as exc:
            import traceback
            print(f"esperienza: {exc}")
            traceback.print_exc()

    threading.Thread(target=_loop, daemon=True).start()

    # 3. Pump WebSocket: svuota la coda in uscita, ricevi i messaggi in entrata
    try:
        while True:
            # Manda tutti gli eventi pendenti al browser
            while True:
                try:
                    await ws.send_json(coda.get_nowait())
                except queue.Empty:
                    break

            # Aspetta il prossimo messaggio (breve timeout per non bloccare)
            try:
                raw = await asyncio.wait_for(ws.receive(), timeout=0.020)
            except asyncio.TimeoutError:
                continue

            if raw["type"] == "websocket.disconnect":
                break
            if raw["type"] != "websocket.receive":
                continue

            if raw.get("bytes"):
                # Audio grezzo da MediaRecorder (WebM/Opus)
                stato.aggiungi_audio(raw["bytes"])
            elif raw.get("text"):
                try:
                    dati = json.loads(raw["text"])
                    if dati.get("tipo") == "frame":
                        stato.set_punti(dati.get("punti"))
                except (json.JSONDecodeError, Exception):
                    pass

    except WebSocketDisconnect:
        pass
    finally:
        stop_ev.set()
