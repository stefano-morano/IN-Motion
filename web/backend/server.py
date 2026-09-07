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
ASSETS = WEB / "assets"

# ------------------------------------------------------------------ inietta stub PRIMA di importare esperienza.py
# esperienza.py fa `import musica`, `import stacco` e `import voce`: li
# sostituiamo con versioni web che accodano eventi JSON per il browser invece
# di usare sounddevice.
#
# L'ORDINE DI QUESTE RIGHE E' PARTE DEL MECCANISMO, non stile. VoceWS non e'
# piu' uno stub vuoto: EREDITA dalla Voce vera, per riusarne cache, scelta
# della voce e durate. Quindi va importato in una finestra precisa —
#   dopo   che visuals/ e' nel path (senza, `import voce` non trova niente)
#   dopo   che lo stub di musica c'e' (voce.py fa `import musica` in testa)
#   prima  che il nome "voce" sia preso dallo stub (altrimenti VoceWS
#          erediterebbe da se stessa)
# Spostare una di queste righe rompe l'avvio, e l'errore non dice perche'.
from musica_ws import MusicaWS, SAMPLE_RATE as _SR  # noqa: E402
from stacco_ws import StaccoWS                       # noqa: E402

_musica_stub = types.ModuleType("musica")
_musica_stub.SAMPLE_RATE = _SR
_musica_stub.Music = MusicaWS
sys.modules["musica"] = _musica_stub

_stacco_stub = types.ModuleType("stacco")
_stacco_stub.Stacco = StaccoWS
sys.modules["stacco"] = _stacco_stub

# Porta i moduli dei visuals nel path (esperienza, testi, occhi, mandala, voce…)
sys.path.insert(0, str(VISUALS))

# adesso, e non prima: qui dentro `import voce` trova quella vera
from voce_ws import VoceWS                           # noqa: E402

_voce_stub = types.ModuleType("voce")
_voce_stub.Voce = VoceWS
sys.modules["voce"] = _voce_stub

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
app.mount("/assets", StaticFiles(directory=str(ASSETS)), name="assets")


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
    racconto      = (body.get("racconto") or "")[:500]
    riflessione   = (body.get("riflessione") or "")[:400]
    emozioni      = body.get("emozioni") or {}
    emozioni_post = body.get("emozioni_post") or {}
    durata        = body.get("durata_minuti", 0)
    profilo       = body.get("profilo") or {}

    # Arricchisce il prompt se c'è anche la riflessione post
    contesto_post = ""
    if riflessione:
        vPost = emozioni_post.get("valenza_media", None)
        aPost = emozioni_post.get("arousal_medio", None)
        contesto_post = f"""
Dopo la meditazione l'utente ha riflettuto:
"{riflessione}"
Dati facciali post-meditazione:
- Valenza: {vPost:.2f if vPost is not None else 'n/d'}
- Arousal: {aPost:.2f if aPost is not None else 'n/d'}
"""

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
    ) + contesto_post

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


@app.get("/voce/{nome}")
def voce_clip(nome: str):
    """Una clip della guida vocale, dalla cache condivisa con la versione
    desktop (visuals/voce_cache/).

    Il nome e' l'impronta che la calcola: sha1 di firma + testo parlato,
    quindi non e' indovinabile e non ci si puo' arrivare da fuori. Lo si
    ricontrolla comunque — un nome che contenga separatori di percorso
    uscirebbe dalla cartella, ed e' il tipo di buco che non si lascia aperto
    solo perche' il server gira in locale."""
    if not nome.endswith(".wav") or "/" in nome or "\\" in nome or ".." in nome:
        return JSONResponse({"errore": "nome non valido"}, status_code=400)
    percorso = (VISUALS / "voce_cache" / nome).resolve()
    if not percorso.is_file() or (VISUALS / "voce_cache").resolve() not in percorso.parents:
        return JSONResponse({"errore": "clip non trovata"}, status_code=404)
    return FileResponse(str(percorso), media_type="audio/wav")


@app.get("/mandala/ultimo")
def mandala_ultimo():
    """Il mandala della sessione appena finita, da portare via.

    Il file esiste gia': _salva_immagine() in esperienza.py lo scrive in un
    thread appena i parametri sono decisi, ed essendo esperienza.py condivisa
    lo fa anche qui. Mancava solo il modo di prenderlo — a schermo il mandala
    e' fatto di 13.664 particelle che si muovono, questo e' lo stesso disegno
    con 260.000 particelle ferme, a 2400x2400.

    Si serve il piu' recente: l'app e' locale e una sessione alla volta,
    quindi il piu' recente e' quello di chi ha appena finito.
    """
    cartella = VISUALS / "mandala"
    if not cartella.is_dir():
        return JSONResponse({"errore": "nessun mandala"}, status_code=404)
    file = sorted(cartella.glob("mandala_*.png"), key=lambda f: f.stat().st_mtime)
    if not file:
        return JSONResponse({"errore": "nessun mandala"}, status_code=404)
    ultimo = file[-1]
    return FileResponse(str(ultimo), media_type="image/png", filename=ultimo.name)


# I file del frontend si servono SENZA CACHE, e non e' pigrizia.
#
# Il browser tiene i moduli ES in cache in modo aggressivo e non li rivalida
# nemmeno cambiando l'indirizzo della pagina. Modificando un file e
# ricaricando si finisce con meta' dei moduli nuovi e meta' vecchi — e se uno
# nuovo importa qualcosa che nella copia vecchia non c'e' ancora, l'import
# fallisce, app.js non parte MAI e a schermo non compare nessun errore: si
# vede solo un'interfaccia in cui i pulsanti non fanno niente. E' un sintomo
# che non somiglia per niente alla causa, ed e' gia' costato una serata.
#
# Qui non c'e' banda da risparmiare: il server e' sulla stessa macchina.
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
RACCONTO_DEFAULT = "oggi mi sento agitato e non riesco a fermare i pensieri"


def _arricchisci_racconto(racconto: str, profilo: dict) -> str:
    if not profilo:
        return racconto
    nome = profilo.get("nome", "")
    obiettivo = profilo.get("obiettivo", "")
    if obiettivo:
        return f"{racconto}\n[Profilo: {nome}, obiettivo: {obiettivo}]"
    return racconto


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
        self.riflessione_inviata = threading.Event()
        self.risultati_visti = threading.Event()

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

    # 1. Pronto, poi aspetta "inizia" o "racconto" (timeout 5 min)
    await ws.send_json({"tipo": "pronto"})
    racconto = ""
    profilo_utente: dict = {}
    try:
        msg = await asyncio.wait_for(ws.receive_json(), timeout=300.0)
        tipo = msg.get("tipo")
        profilo_utente = msg.get("profilo") or {}
        if tipo == "racconto":
            racconto = msg.get("testo") or RACCONTO_DEFAULT
        elif tipo != "inizia":
            print(f"racconto: messaggio inatteso ({tipo!r}), uso default")
            racconto = RACCONTO_DEFAULT
    except Exception as exc:
        print(f"racconto: errore/timeout ({exc}), uso default")
        racconto = RACCONTO_DEFAULT

    racconto = _arricchisci_racconto(racconto, profilo_utente)
    print(f'racconto: "{racconto[:120]}"' if racconto else "racconto: (in attesa dal browser)")

    # 2. Avvia il ciclo dell'esperienza in un thread separato
    stop_ev = threading.Event()
    esp_ref: dict = {"esp": None}

    def _loop():
        try:
            esp = _exp_mod.Esperienza(
                scena, racconto, ascolto, musica=musica, tappeto=tappeto,
                voce=VoceWS(coda, (tappeto, musica)),
                sincronia=stato,
            )
            esp_ref["esp"] = esp
            esp.avvia(time.time())
            while not esp.finita and not stop_ev.is_set():
                punti = _adatta_punti(stato.get_punti())
                esp.aggiorna(time.time(), punti)
                time.sleep(1 / 30)
        except Exception as exc:
            import traceback
            print(f"esperienza: {exc}")
            traceback.print_exc()
        finally:
            coda.put({"tipo": "fine"})

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
                    elif dati.get("tipo") == "racconto":
                        testo = _arricchisci_racconto(
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
