"""
voce.py
-------
La voce che legge le scritte: una guida che accompagna le particelle.

Sta al testo come musica.py sta alla scena: e' una SORGENTE AUDIO, non un
narratore che comanda. La macchina a stati le dice "di' questa frase" e lei
risponde in un istante — quanto durera' — senza mai fermare il ciclo. Se
aspettasse la rete, per tutto quel tempo la webcam sarebbe cieca.

TRE REGOLE, e sono le stesse del resto del progetto.

1. NIENTE SI SINTETIZZA MENTRE L'OPERA GIRA. Una chiamata a ElevenLabs costa
   uno o due secondi: dentro l'esperienza sarebbe un buco. Percio' ogni clip
   nasce PRIMA — le scritte fisse con prepara_voce.py (o in sottofondo
   all'avvio, dietro al nero), le frasi personalizzate nello stesso thread
   che le ha appena generate, mentre a schermo scorre "preparo la tua
   meditazione". Al momento di parlare c'e' solo un file da leggere.

2. LA CACHE E' IL PROGETTO, NON UN'OTTIMIZZAZIONE. Le scritte fisse sono
   sempre le stesse: sintetizzarle ad ogni sessione brucerebbe i crediti del
   piano gratuito in una giornata di prove, e legherebbe l'installazione alla
   rete proprio nel momento in cui apre il sipario. Si sintetizzano una volta
   e restano su disco (voce_cache/). Con la cache piena una sessione costa
   solo le tre frasi personali.

3. IL SILENZIO E' UN RIPIEGO LEGITTIMO. Senza chiave, senza rete, senza
   libreria, l'esperienza va avanti muta esattamente come va avanti con le
   frasi di riserva quando Claude non risponde. Non si solleva mai
   un'eccezione da qui.

IL FLUSSO SI APRE UNA VOLTA SOLA, come il tappeto e il microfono: aprire un
flusso mentre un altro suona fa riconfigurare la scheda audio e si sente come
un click. Quando non c'e' niente da dire, il callback riempie di silenzio.

MENTRE LA VOCE PARLA LA MUSICA SI FA DA PARTE. Non e' lo stacco (quello
annuncia un passaggio di stato, qui si fa spazio a delle parole) e non deve
litigarci: usa un moltiplicatore SUO su ogni sorgente — attenua_per_voce() —
quindi voce e stacco possono capitare insieme e ognuno dei due arriva dove
voleva.
"""

import hashlib
import io
import json
import os
import threading
import wave

import numpy as np

import musica as modulo_musica

SAMPLE_RATE = modulo_musica.SAMPLE_RATE
CARTELLA = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(CARTELLA, "voce_cache")
SCELTA = os.path.join(CARTELLA, "voce_scelta.json")

# ---------- da dove viene la voce ----------
# Due fornitori, la stessa interfaccia. Si sceglie con VOCE_MOTORE, e lasciando
# la variabile vuota si prende il primo che risulta configurato — ElevenLabs
# per primo, perche' e' quello su cui il pezzo e' stato montato.
#
#   VOCE_MOTORE=elevenlabs   piu' caldo e piu' espressivo, 44.1 kHz. Ma le voci
#                            italiane stanno solo nella libreria pubblica, che
#                            il piano gratuito non puo' usare via API: gratis
#                            si parla italiano con l'accento inglese.
#   VOCE_MOTORE=polly        voci ITALIANE native (Beatrice, Bianca) e una
#                            quota gratuita mille volte piu' larga, ma audio a
#                            24 kHz e una lettura un po' meno respirata.
#
# Chi cambia motore non cambia nient'altro: la cache tiene conto di chi parla,
# quindi le clip dei due convivono e si torna indietro senza ripagare nulla.
MOTORE = os.environ.get("VOCE_MOTORE", "").strip().lower()

# ---------- la lingua dell'opera ----------
# L'inglese non e' una traduzione: e' la lingua in cui il pezzo si mostra, e
# la ragione per cui la voce e' un problema risolto invece che un problema
# aperto. Le voci di serie di ElevenLabs sono NATIVE inglesi — le migliori
# che abbia, comprese nel piano gratuito — mentre in italiano le native
# stanno solo nella libreria pubblica, che il piano gratuito non usa via API.
# Scegliere l'inglese ha tolto di mezzo l'accento, l'abbonamento e la
# dipendenza da un fornitore a pagamento, tutti insieme.
#
# Per tornare all'italiano: questa costante, LINGUA in ascolto.py, le scritte
# in esperienza.py e il prompt in testi.py. Tutto il resto e' indifferente.
LINGUA = os.environ.get("VOCE_LINGUA", "en").strip().lower()

# ---------- chi parla ----------
# La voce vera si sceglie con  python3 voci.py  , che la scrive in
# voce_scelta.json. Questi sono solo i ripieghi: i nomi vengono cercati fra le
# voci disponibili e si prende la prima che c'e'. Charlie (male, EN) e' la
# guida attuale; le altre restano come fallback se non e' sull'account.
NOMI_PREFERITI = {
    "en": ("Charlie", "George", "Will", "Daniel", "Brian", "Adam"),
    "it": ("Charlie", "George", "Will", "Adam", "Antoni"),
}.get(LINGUA, ("Charlie", "George", "Will"))

# Le due italiane di Polly. Beatrice esiste solo col motore generative, Bianca
# anche con neural e standard: mettere Beatrice per prima significa chiedere
# sempre il meglio, e ripiegare da sole quando la region non ce l'ha.
POLLY_PREFERITE = {
    "en": ("Danielle", "Ruth", "Joanna", "Salli"),
    "it": ("Beatrice", "Bianca", "Carla"),
}.get(LINGUA, ("Danielle",))
POLLY_LINGUA = {"en": "en-US", "it": "it-IT"}.get(LINGUA, "en-US")

# In ordine di qualita'. Il primo che la voce supporta nella region scelta
# vince: generative e' il motore nuovo e suona molto meglio, ma non e' acceso
# ovunque, e scoprirlo con un errore in faccia sarebbe inutilmente ostile.
POLLY_MOTORI = ("generative", "neural", "standard")

# La region conta davvero: le voci generative non esistono dappertutto. Se
# quella configurata non le ha, si scende a neural e lo si dice.
POLLY_REGIONE = (os.environ.get("VOCE_POLLY_REGIONE")
                 or os.environ.get("AWS_REGION")
                 or os.environ.get("AWS_DEFAULT_REGION")
                 or "eu-central-1")

# eleven_multilingual_v2 e' la scelta giusta QUI: parla italiano, costa un
# credito per carattere, ed essendo tutto pre-sintetizzato la latenza — l'unico
# campo in cui i modelli "flash" vincono — non conta nulla. Si cambia con
# ELEVENLABS_MODEL senza toccare il codice.
MODELLO = os.environ.get("ELEVENLABS_MODEL", "eleven_multilingual_v2")

# --- ElevenLabs ---
# Il PCM a 44.1 kHz e' riservato al piano Pro: chiederlo da un piano gratuito
# fa fallire la richiesta. L'MP3 invece lo danno a tutti, e soundfile lo legge
# senza ffmpeg. Se soundfile non c'e', si ripiega sul PCM a 16 kHz — brutto ma
# aperto a chiunque — e si ricampiona qui.
FORMATO_MP3 = "mp3_44100_128"
FORMATO_PCM = "pcm_16000"
PCM_SR = 16000

# Come deve suonare.
#
# VELOCITA 0.70 e' molto sotto il parlato normale, ed e' voluto: queste frasi
# non si ascoltano, si seguono. Chi le sente ha gli occhi chiusi e non ha
# nessun appiglio visivo — alla velocita' di una conversazione le parole
# arriverebbero prima che ci sia il tempo di posarle.
#
# STABILITA alta (0.88) tiene la guida calma e coerente fra una clip e
# l'altra. Con Charlie (timbro piuttosto brillante) abbassa anche i picchi
# "squillanti" dell'interpretazione.
#
# STILE resta a zero: e' l'enfasi interpretativa, e qui e' esattamente cio'
# che non si vuole. SOMIGLIANZA un po' sotto 0.80 ammorbidisce il timbro
# senza perdere la voce. SPEAKER_BOOST spento: altrimenti ElevenLabs spinge
# le medie-alte e la guida suona troppo in avanti / acuta in cuffia.
STABILITA = 0.88
SOMIGLIANZA = 0.70
STILE = 0.0
VELOCITA = 0.70
SPEAKER_BOOST = False

# --- Polly ---
# Polly non ha una manopola "velocita'": si chiede in SSML, con <prosody>. Ma
# il motore generative l'SSML non lo accetta, quindi li' la frase va detta al
# suo passo naturale — che per fortuna e' gia' posato. Sugli altri due motori
# si rallenta come su ElevenLabs.
POLLY_VELOCITA = "90%"
POLLY_FORMATO = "mp3"
POLLY_SR = "24000"       # il massimo che Polly da' in mp3
POLLY_SR_PCM = "16000"   # il ripiego senza soundfile: pcm, mono, crudo

VOLUME = 0.78        # guida presente ma non aggressiva in cuffia

# Silenzio da togliere in testa e in coda alla clip. Il modello lascia sempre
# un po' d'aria intorno alle parole, e sommata alla permanenza della scritta
# diventerebbe un vuoto.
SOGLIA_SILENZIO = 0.01
DISSOLVENZA = 0.015  # 15 ms in entrata e in uscita: senza, si sente lo scatto

# ---------- da scritta a parlato ----------
# Due modi diversi in cui le scritte rinunciano agli accenti, e due rimedi:
# 1. le parole scritte senza accento (CIO, GIA, PIU): l'accento non si puo'
#    indovinare, va saputo.
ACCENTI = {
    "cio": "ciò", "gia": "già", "piu": "più", "perche": "perché",
    "puo": "può", "cosi": "così", "sara": "sarà", "cioe": "cioè",
    "pero": "però", "citta": "città", "verita": "verità",
    "liberta": "libertà", "meta": "metà",
}
# 2. le parole scritte con l'apostrofo al posto dell'accento (E', GIA', PIU'):
#    li' la regola c'e' ed e' sempre la stessa — l'ultima vocale prende
#    l'accento grave. Vale anche per le parole che nessuno ha ancora scritto.
GRAVI = {"a": "à", "e": "è", "i": "ì", "o": "ò", "u": "ù"}


def _accenta(parola: str) -> str:
    """Rimette gli accenti che la scritta ha dovuto lasciare per strada.

    Serve SOLO all'italiano, ed e' per questo che si spegne da sola quando la
    lingua e' un'altra: in inglese un apostrofo finale e' un possessivo
    ("PARENTS'"), non un accento mancante, e trasformarlo sarebbe un danno.
    Resta qui, invece di essere cancellata, perche' la scelta della lingua e'
    di chi allestisce e puo' cambiare: quello che va perso tornando indietro
    non e' il codice, e' il ragionamento che c'e' dentro."""
    if LINGUA != "it":
        return parola
    if parola.endswith("'") and len(parola) > 1:
        radice = parola[:-1]
        if radice[-1] in GRAVI:
            return radice[:-1] + GRAVI[radice[-1]]
        parola = radice
    return ACCENTI.get(parola, parola)


def _parlato(testo: str) -> str:
    """La stessa frase, ma come va detta invece che come va disegnata.

    Le scritte sono tutte in MAIUSCOLO perche' cosi' si disegnano a particelle.
    Dette com'e' scritte una sintesi le urlerebbe: qui si rimettono in
    minuscolo, si chiudono con un punto — senza, la frase resta sospesa come
    se dovesse continuare — e in italiano si restituiscono anche gli accenti
    che la scritta aveva dovuto perdere."""
    testo = testo.strip()
    if not testo:
        return ""
    parole = [_accenta(p.lower()) for p in testo.split(" ")]
    if LINGUA == "en":
        # l'unica maiuscola che l'inglese tiene in mezzo alla frase: "i" e le
        # sue contrazioni. Una sintesi le direbbe giuste comunque, ma la frase
        # scritta minuscola finisce anche nei log e nei nomi dei campioni
        parole = [p[0].upper() + p[1:] if p == "i" or p.startswith("i'") else p
                  for p in parole]
    frase = " ".join(parole)
    frase = frase[:1].upper() + frase[1:]
    # senza un punto finale la sintesi lascia la frase sospesa, come se
    # dovesse continuare: qui invece ogni scritta e' chiusa in se'
    if frase[-1] not in ".?!:,":
        frase += "."
    return frase


def _spiega(errore) -> str:
    """Un errore dell'API in una riga leggibile.

    Il messaggio che arriva dal client comincia con tutte le intestazioni HTTP
    e il vero motivo finisce fuori schermo: qui si tiene solo il codice, che
    e' l'unica cosa che dice da che parte andare a cercare."""
    codice = getattr(errore, "status_code", None)
    corpo = getattr(errore, "body", None)
    dettaglio = corpo.get("detail") if isinstance(corpo, dict) else None
    if isinstance(dettaglio, dict):
        stato = dettaglio.get("status") or dettaglio.get("code")
    else:
        stato = None

    # ElevenLabs often answers quota_exceeded with HTTP 401 (not 429). Check
    # the body first so we do not blame the API key.
    if stato == "quota_exceeded":
        return ("quota esaurita: crediti ElevenLabs finiti per questo mese "
                "(piano free ~10k caratteri). Aspetta il rinnovo o fai upgrade")
    # Il caso piu' insidioso, e non e' raro: la chiave e' giusta ma e' stata
    # creata "ristretta" e non ha gli scope accesi. Risponde 401 come una
    # chiave sbagliata, e si passa mezz'ora a rigenerarne di nuove — tutte
    # ugualmente ristrette.
    if stato == "missing_permissions":
        return ("alla chiave mancano dei permessi — su elevenlabs.io → API Keys "
                "→ Edit accendi 'Text to Speech' e 'Voices'")
    if codice == 401:
        return "chiave rifiutata (401): controlla ELEVENLABS_API_KEY"
    if codice == 429:
        return "quota esaurita (429): crediti finiti per questo mese"
    # Vale la pena dirlo per esteso: il piano gratuito TIENE le voci della
    # libreria pubblica nell'account e le mostra, ma non le fa sintetizzare.
    # Si scopre solo qui, dopo averne aggiunta una.
    if codice == 402:
        return ("il piano gratuito non puo' usare via API le voci della "
                "libreria pubblica: scegline una di serie, o passa al piano "
                "Starter")
    if isinstance(dettaglio, dict) and dettaglio.get("message"):
        return f"{codice}: {dettaglio['message'][:90]}"
    if codice:
        return f"ElevenLabs ha risposto {codice}"
    return str(errore).splitlines()[0][:100]


def _spiega_aws(errore) -> str:
    """Un errore di AWS in una riga leggibile.

    boto3 e' preciso ma prolisso, e i suoi codici non dicono nulla a chi non
    li conosce: 'UnrecognizedClientException' vuol dire semplicemente che la
    chiave e' sbagliata. Qui si traduce, e per ognuno si dice cosa fare."""
    nome = type(errore).__name__
    if "NoCredentials" in nome or "NoRegion" in nome:
        return ("credenziali AWS assenti: servono AWS_ACCESS_KEY_ID e "
                "AWS_SECRET_ACCESS_KEY, o un  aws configure  gia' fatto")
    risposta = getattr(errore, "response", None)
    codice = ""
    messaggio = ""
    if isinstance(risposta, dict):
        dettaglio = risposta.get("Error") or {}
        codice = dettaglio.get("Code", "")
        messaggio = dettaglio.get("Message", "")
    if codice in ("UnrecognizedClientException", "InvalidSignatureException",
                  "InvalidClientTokenId"):
        return "chiave AWS non riconosciuta: controlla ID e secret"
    if codice == "AccessDeniedException" or "AccessDenied" in codice:
        return ("all'utente AWS manca il permesso su Polly: assegnagli la "
                "policy AmazonPollyReadOnlyAccess")
    if "EndpointConnection" in nome:
        return f"AWS non raggiungibile nella region {POLLY_REGIONE}"
    if codice:
        return f"{codice}: {messaggio[:90]}"
    return str(errore).splitlines()[0][:110]


def cerca_voce(elenco, chi):
    """La voce chiamata 'chi', per id o per nome. None se non c'e'.

    Il nome non si confronta per intero: sull'account le voci si chiamano
    "Lily - Velvety, British, Mellow", non "Lily". Il pezzo prima del trattino
    e' il nome vero, il resto e' la descrizione che ElevenLabs ci appiccica —
    e nessuno la digitera' mai."""
    chi = chi.strip().lower()
    for voce in elenco:
        if voce["id"] == chi:
            return voce
    for voce in elenco:
        nome = voce["nome"].lower()
        if nome == chi or nome.split(" - ")[0].strip() == chi:
            return voce
    for voce in elenco:
        if chi in voce["nome"].lower():
            return voce
    return None


def _impronta(testo_parlato: str, firma: str) -> str:
    """Il nome del file in cache.

    La firma la scrive il fornitore e contiene tutto cio' che cambia il suono:
    chi e' il fornitore, quale voce, quale motore, a che velocita'. Cambiando
    una qualunque di queste cose cambia l'impronta, le clip vecchie restano li'
    senza dare fastidio e le nuove si rifanno da sole — e tornando indietro si
    ritrovano quelle di prima, senza ripagarle. Non c'e' niente da svuotare a
    mano, mai."""
    return hashlib.sha1(f"{firma}|{testo_parlato}".encode("utf-8")).hexdigest()[:16]


def _scelta_salvata(motore: str):
    """La voce fissata con 'voci.py scegli', per questo motore.

    Il file tiene una scelta PER FORNITORE: l'id di una voce ElevenLabs non
    vuol dire niente per Polly, e passare da uno all'altro non deve cancellare
    quello che si era gia' deciso sull'altro. Il vecchio formato piatto — un
    solo voice_id, scritto quando il fornitore era uno solo — vale ancora e si
    legge come una scelta di ElevenLabs."""
    if not os.path.exists(SCELTA):
        return None
    try:
        with open(SCELTA) as f:
            dati = json.load(f)
    except Exception:
        return None
    if "voice_id" in dati:                       # formato vecchio, piatto
        dati = {"elevenlabs": dati}
    scelta = dati.get(motore)
    return scelta if isinstance(scelta, dict) and scelta.get("voice_id") else None


def salva_scelta(motore: str, voce_id: str, nome: str):
    """Fissa la voce di un motore senza toccare quella degli altri."""
    dati = {}
    if os.path.exists(SCELTA):
        try:
            with open(SCELTA) as f:
                dati = json.load(f)
            if "voice_id" in dati:
                dati = {"elevenlabs": dati}
        except Exception:
            dati = {}
    dati[motore] = {"voice_id": voce_id, "nome": nome}
    with open(SCELTA, "w") as f:
        json.dump(dati, f, indent=2, ensure_ascii=False)


# ---------- audio ----------

def _rifinisci(dati, sr):
    """Toglie il silenzio davanti e dietro, e smussa i due bordi.

    Il taglio serve ai tempi: la scritta resta a schermo finche' la voce non
    ha finito, e mezzo secondo d'aria registrata diventerebbe mezzo secondo di
    attesa a vuoto. La dissolvenza serve all'orecchio: un'onda tagliata di
    netto fa uno schiocco."""
    if len(dati) == 0:
        return dati
    livello = np.abs(dati).max(axis=1)
    acceso = np.nonzero(livello > max(livello.max() * SOGLIA_SILENZIO, 1e-4))[0]
    if acceso.size:
        margine = int(0.03 * sr)     # un filo d'aria si tiene: respira meglio
        dati = dati[max(0, acceso[0] - margine):acceso[-1] + margine]
    n = int(DISSOLVENZA * sr)
    if n > 0 and len(dati) > 2 * n:
        rampa = np.linspace(0.0, 1.0, n, dtype=np.float32)[:, None]
        dati[:n] *= rampa
        dati[-n:] *= rampa[::-1]
    return dati


def _ricampiona(dati, da, a=SAMPLE_RATE):
    if da == a:
        return dati
    n = int(len(dati) * a / da)
    vecchi = np.arange(len(dati), dtype=np.float64)
    nuovi = np.linspace(0.0, len(dati) - 1, n)
    return np.stack(
        [np.interp(nuovi, vecchi, dati[:, c]) for c in range(dati.shape[1])],
        axis=1).astype(np.float32)


def _salva_wav(percorso, dati, sr=SAMPLE_RATE):
    campioni = np.clip(dati, -1.0, 1.0)
    campioni = (campioni * 32767.0).astype(np.int16)
    tmp = percorso + ".parziale"
    with wave.open(tmp, "wb") as w:
        w.setnchannels(campioni.shape[1])
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(campioni.tobytes())
    # si rinomina solo a file completo: se il programma muore a meta' scrittura
    # non resta in cache una clip troncata che poi suonerebbe mozzata per sempre
    os.replace(tmp, percorso)


# ---------- i fornitori ----------
# Due classi con la stessa faccia: attivo, motivo, voce_id, voce_nome, firma,
# voci(), sintetizza(). Sopra di loro non c'e' un solo 'if': la classe Voce non
# sa da dove arrivi l'audio, e la cache neanche. Aggiungerne un terzo domani
# vuol dire scrivere una classe e una riga in _crea_fornitore().


class _ElevenLabs:
    """Parla con ElevenLabs. Costruito una volta, riusato per tutte le clip.

    Se manca qualcosa — libreria, chiave, rete — non protesta: si dichiara
    non disponibile e da quel momento tutto il resto lavora in silenzio."""

    nome_motore = "elevenlabs"

    def __init__(self):
        self.attivo = False
        self.motivo = ""
        self.errore = ""        # cosa ha risposto ElevenLabs, se ha risposto male
        self.voce_id = None
        self.voce_nome = None
        # Copia locale delle manopole: la costante in cima al file e' il
        # valore di partenza, non una gabbia. Un attrezzo puo' cambiarle su
        # QUESTA istanza per far sentire due velocita' a confronto, e siccome
        # entrano nella firma le due versioni finiscono in due file diversi
        # invece di sovrascriversi.
        self.velocita = VELOCITA
        self.stabilita = STABILITA
        self._client = None
        self._formato = FORMATO_MP3
        self._leggi = None
        self._prepara()

    @property
    def firma(self):
        """Tutto cio' che cambia il suono di questo fornitore.

        NON ha il prefisso 'elevenlabs' apposta: e' la stessa firma che usava
        il codice quando il fornitore era uno solo, e cambiarla renderebbe
        irraggiungibili le clip gia' pagate. Polly si distingue da se',
        perche' le sue voci si chiamano 'Beatrice', non con un id esadecimale."""
        return (f"{self.voce_id}|{MODELLO}|{self.velocita}|{self.stabilita}"
                f"|{SOMIGLIANZA}|{STILE}|boost={int(SPEAKER_BOOST)}")

    def _prepara(self):
        chiave = os.environ.get("ELEVENLABS_API_KEY", "").strip()
        if not chiave:
            self.motivo = "ELEVENLABS_API_KEY non impostata"
            return
        try:
            from elevenlabs.client import ElevenLabs
        except Exception:
            self.motivo = "manca la libreria elevenlabs (pip3 install elevenlabs)"
            return

        # Come si legge l'audio che torna indietro decide anche COSA chiedere:
        # con soundfile si prende l'MP3 a 44.1 kHz (il PCM a quella frequenza
        # e' riservato al piano Pro), senza si ripiega sul PCM a 16 kHz, che
        # e' crudo e non ha bisogno di nessun decoder.
        try:
            import soundfile
            self._leggi = self._leggi_mp3
            self._formato = FORMATO_MP3
        except Exception:
            self._leggi = self._leggi_pcm
            self._formato = FORMATO_PCM

        try:
            self._client = ElevenLabs(api_key=chiave)
        except Exception as errore:
            self.motivo = f"client non costruito ({errore})"
            return

        self.voce_id, self.voce_nome = self._scegli_voce()
        if not self.voce_id:
            # quasi sempre e' la chiave sbagliata o ristretta, non un account
            # vuoto: il messaggio deve dire quello che e' successo davvero,
            # altrimenti si va a cercare il problema dalla parte opposta
            self.motivo = (self.errore or "nessuna voce sull'account")
            return

        self.attivo = True

    def _voice_settings(self):
        """Le impostazioni di lettura, costruite al momento della sintesi.

        Al momento e non una volta per tutte: cosi' cambiare self.velocita'
        ha effetto davvero, invece di restare un numero che nessuno guarda
        piu'. Costa una allocazione per clip, cioe' niente."""
        try:
            from elevenlabs import VoiceSettings
            return VoiceSettings(
                stability=self.stabilita, similarity_boost=SOMIGLIANZA,
                style=STILE, use_speaker_boost=SPEAKER_BOOST,
                speed=self.velocita,
            )
        except Exception:
            return None   # si usano quelle di serie della voce

    # ---- la voce ----

    def _scegli_voce(self):
        """L'id di chi legge. Prima la scelta salvata, poi i nomi preferiti,
        poi la prima voce che c'e': si parla comunque."""
        forzata = os.environ.get("ELEVENLABS_VOICE_ID", "").strip()
        if forzata:
            return forzata, os.environ.get("ELEVENLABS_VOICE_NOME", forzata)

        salvata = _scelta_salvata(self.nome_motore)
        if salvata:
            return salvata["voice_id"], salvata.get("nome", "?")

        elenco = self.voci()
        if not elenco:
            return None, None
        for nome in NOMI_PREFERITI:
            trovata = cerca_voce(elenco, nome)
            if trovata:
                return trovata["id"], trovata["nome"]
        return elenco[0]["id"], elenco[0]["nome"]

    def voci(self):
        """Le voci dell'account, come dizionari semplici. [] se non si riesce."""
        try:
            risposta = self._client.voices.search(page_size=100)
            grezze = getattr(risposta, "voices", risposta)
        except Exception as errore:
            self.errore = _spiega(errore)
            try:
                grezze = self._client.voices.get_all().voices
            except Exception:
                return []
            self.errore = ""
        fuori = []
        for v in grezze:
            etichette = getattr(v, "labels", None) or {}
            fuori.append({
                "id": getattr(v, "voice_id", None),
                "nome": getattr(v, "name", "?") or "?",
                "genere": etichette.get("gender", ""),
                "eta": etichette.get("age", ""),
                "accento": etichette.get("accent", ""),
                "descrizione": etichette.get("description", "")
                               or (getattr(v, "description", "") or ""),
            })
        return [v for v in fuori if v["id"]]

    # ---- la sintesi ----

    def _leggi_mp3(self, grezzo):
        import soundfile
        dati, sr = soundfile.read(io.BytesIO(grezzo), dtype="float32",
                                  always_2d=True)
        return dati, sr

    def _leggi_pcm(self, grezzo):
        dati = np.frombuffer(grezzo, dtype=np.int16).astype(np.float32) / 32768.0
        return dati.reshape(-1, 1), PCM_SR

    def sintetizza(self, testo_parlato):
        """I campioni della frase detta, gia' pronti per il flusso. None se
        non si e' potuto."""
        try:
            pezzi = self._client.text_to_speech.convert(
                voice_id=self.voce_id,
                model_id=MODELLO,
                text=testo_parlato,
                output_format=self._formato,
                voice_settings=self._voice_settings(),
            )
            grezzo = b"".join(pezzi) if not isinstance(pezzi, (bytes, bytearray)) else pezzi
            dati, sr = self._leggi(grezzo)
        except Exception as errore:
            print(f"[voce] sintesi fallita — {_spiega(errore)}")
            return None
        return _sistema(dati, sr)


class _Polly:
    """Parla con Amazon Polly.

    Perche' vale la pena averlo accanto a ElevenLabs: **le voci italiane sono
    di serie**. Beatrice e Bianca sono madrelingua, e non c'e' nessuna
    libreria a pagamento di mezzo. Su un pezzo dove la voce arriva quando la
    persona ha gli occhi chiusi — cioe' quando e' l'unico canale rimasto —
    l'accento non e' un dettaglio estetico.

    E la quota gratuita e' di un altro ordine di grandezza: un milione di
    caratteri al mese col motore neural, contro i diecimila di ElevenLabs.
    Questo pezzo ne consuma settecento una volta e un centinaio a sessione.

    Il prezzo da pagare e' la resa: 24 kHz invece di 44.1, e una lettura un po'
    meno respirata. Si sceglie a orecchio, non a tabella — per questo ci sono
    tutti e due."""

    nome_motore = "polly"

    def __init__(self):
        self.attivo = False
        self.motivo = ""
        self.errore = ""
        self.voce_id = None
        self.voce_nome = None
        self.motore = None       # generative / neural / standard
        self.velocita = POLLY_VELOCITA
        self.regione = POLLY_REGIONE
        self._client = None
        self._formato = POLLY_FORMATO
        self._sr = POLLY_SR
        self._prepara()

    @property
    def firma(self):
        return f"polly|{self.voce_id}|{self.motore}|{self.velocita}"

    def _prepara(self):
        try:
            import boto3
        except Exception:
            self.motivo = "manca la libreria boto3 (pip3 install boto3)"
            return
        try:
            import soundfile          # noqa: F401
        except Exception:
            # senza decoder si chiede il PCM crudo, che Polly da' solo mono e
            # al massimo a 16 kHz: si sente, ma si sente qualcosa
            self._formato, self._sr = "pcm", POLLY_SR_PCM

        try:
            self._client = boto3.client("polly", region_name=self.regione)
        except Exception as errore:
            self.motivo = f"client non costruito ({errore})"
            return

        elenco = self.voci()
        if not elenco:
            self.motivo = (self.errore
                           or f"nessuna voce italiana nella region {self.regione}")
            return

        scelta = self._scegli_voce(elenco)
        if not scelta:
            self.motivo = "nessuna voce utilizzabile"
            return
        self.voce_id = scelta["id"]
        self.voce_nome = scelta["nome"]
        self.motore = self._miglior_motore(scelta)
        self.attivo = True

    # ---- la voce ----

    def _scegli_voce(self, elenco):
        forzata = os.environ.get("VOCE_POLLY", "").strip()
        if forzata:
            return cerca_voce(elenco, forzata)
        salvata = _scelta_salvata(self.nome_motore)
        if salvata:
            trovata = cerca_voce(elenco, salvata["voice_id"])
            if trovata:
                return trovata
        for nome in POLLY_PREFERITE:
            trovata = cerca_voce(elenco, nome)
            if trovata:
                return trovata
        return elenco[0]

    def _miglior_motore(self, voce):
        """Il motore migliore che QUESTA voce ha in QUESTA region.

        Non si chiede 'generative' e basta: le voci generative non esistono in
        tutte le region, e chiederle dove non ci sono darebbe un errore in
        faccia al primo avvio invece di una voce un po' meno bella. Si scende
        da soli, dicendolo."""
        disponibili = voce.get("motori") or ("standard",)
        for motore in POLLY_MOTORI:
            if motore in disponibili:
                if motore != POLLY_MOTORI[0]:
                    print(f"voce: {motore} invece di {POLLY_MOTORI[0]} "
                          f"({voce['nome']} non ce l'ha su {self.regione})")
                return motore
        return list(disponibili)[0]

    def voci(self):
        """Le voci italiane della region, nella stessa forma di ElevenLabs.

        Polly non dichiara l'eta': si lascia vuota invece di inventarla, e chi
        elenca mostrera' tutte le femminili invece di tre. Meglio una colonna
        vuota che una etichetta finta."""
        try:
            risposta = self._client.describe_voices(LanguageCode=POLLY_LINGUA)
        except Exception as errore:
            self.errore = _spiega_aws(errore)
            return []
        fuori = []
        for v in risposta.get("Voices", []):
            motori = tuple(v.get("SupportedEngines") or ())
            fuori.append({
                "id": v.get("Id"),
                "nome": v.get("Id"),
                "genere": (v.get("Gender") or "").lower(),
                "eta": "",
                "accento": "italiano",
                "descrizione": ", ".join(motori),
                "motori": motori,
            })
        return [v for v in fuori if v["id"]]

    # ---- la sintesi ----

    def sintetizza(self, testo_parlato):
        testo, tipo = self._da_dire(testo_parlato)
        try:
            risposta = self._client.synthesize_speech(
                Text=testo, TextType=tipo, VoiceId=self.voce_id,
                Engine=self.motore, LanguageCode=POLLY_LINGUA,
                OutputFormat=self._formato, SampleRate=self._sr,
            )
            grezzo = risposta["AudioStream"].read()
        except Exception as errore:
            print(f"[voce] sintesi fallita — {_spiega_aws(errore)}")
            return None

        if self._formato == "pcm":
            dati = np.frombuffer(grezzo, dtype=np.int16).astype(np.float32) / 32768.0
            dati, sr = dati.reshape(-1, 1), int(self._sr)
        else:
            import soundfile
            dati, sr = soundfile.read(io.BytesIO(grezzo), dtype="float32",
                                      always_2d=True)
        return _sistema(dati, sr)

    def _da_dire(self, testo_parlato):
        """Il testo e il suo tipo. Con SSML si rallenta, senza no.

        Il motore generative l'SSML non lo accetta: chiederglielo farebbe
        fallire ogni singola frase. Li' si dice il testo com'e' — e il suo
        passo naturale e' gia' abbastanza posato."""
        if self.motore == "generative":
            return testo_parlato, "text"
        parlato = (testo_parlato.replace("&", "e").replace("<", "").replace(">", ""))
        return (f'<speak><prosody rate="{self.velocita}">{parlato}</prosody></speak>',
                "ssml")


def _sistema(dati, sr):
    """Da quello che torna dal fornitore a una clip pronta per il flusso:
    stereo, alla frequenza del progetto, senza silenzio intorno."""
    if dati.shape[1] == 1:
        dati = np.repeat(dati, 2, axis=1)
    dati = _ricampiona(np.ascontiguousarray(dati, dtype=np.float32), sr)
    return _rifinisci(dati, SAMPLE_RATE)


def _crea_fornitore():
    """Il fornitore da usare. VOCE_MOTORE decide; senza, vince il primo che
    risulta configurato.

    L'ordine non e' casuale: ElevenLabs per primo perche' e' quello su cui il
    pezzo e' stato montato, e chi ha gia' una cache piena non deve trovarsi
    una voce diversa solo perche' un giorno ha installato boto3."""
    fabbriche = {"elevenlabs": _ElevenLabs, "polly": _Polly}
    if MOTORE in fabbriche:
        return fabbriche[MOTORE]()
    if MOTORE:
        finto = _ElevenLabs.__new__(_ElevenLabs)
        finto.attivo, finto.voce_id, finto.voce_nome = False, None, None
        finto.motivo = (f"VOCE_MOTORE='{MOTORE}' non esiste: "
                        f"usa {' o '.join(fabbriche)}")
        return finto

    primo = None
    for fabbrica in fabbriche.values():
        fornitore = fabbrica()
        if fornitore.attivo:
            return fornitore
        primo = primo or fornitore
    return primo


# ---------- la sorgente ----------

class Voce:
    """La guida che legge. Una clip alla volta, in coda, senza mai bloccare."""

    def __init__(self, sorgenti_da_abbassare=(), volume=VOLUME,
                 attenuazione=0.35, sr=SAMPLE_RATE):
        self.sr = sr
        self.volume = volume
        self.attenuazione = attenuazione
        self.sorgenti = tuple(sorgenti_da_abbassare)

        self._fornitore = None
        self._stream = None
        self._coda = []
        self._clip = None
        self._pos = 0
        self._lock = threading.Lock()
        self._abbassate = False
        self._in_corso = set()      # frasi che qualcuno sta gia' sintetizzando
        self._cache_lock = threading.Lock()
        os.makedirs(CACHE, exist_ok=True)

    # ---- avvio ----

    @property
    def fornitore(self):
        """Costruito alla prima richiesta: cosi' chi prova l'esperienza senza
        voce non paga nemmeno l'import della libreria."""
        if self._fornitore is None:
            self._fornitore = _crea_fornitore()
            f = self._fornitore
            if f.attivo:
                dettaglio = getattr(f, "motore", None) or MODELLO
                print(f"voce: {f.voce_nome} ({f.nome_motore}, {dettaglio})")
            else:
                print(f"voce: muta — {f.motivo}")
        return self._fornitore

    @property
    def disponibile(self):
        return self.fornitore.attivo

    def apri(self):
        """Apre il flusso, muto. Come per la musica: una volta sola, all'avvio,
        e resta aperto fino alla fine."""
        if self._stream is not None:
            return True
        try:
            import sounddevice as sd
            self._stream = sd.OutputStream(
                samplerate=self.sr, channels=2,
                blocksize=modulo_musica.BLOCCO, latency="high",
                callback=self._callback)
            self._stream.start()
            return True
        except Exception as errore:
            print(f"voce: audio non disponibile ({errore})")
            self._stream = None
            return False

    # ---- la cache ----

    def _percorso(self, testo):
        parlato = _parlato(testo)
        if not parlato:
            return None, None
        firma = self.fornitore.firma if self.fornitore.voce_id else "muta"
        return os.path.join(CACHE, _impronta(parlato, firma) + ".wav"), parlato

    def pronta(self, testo):
        """True se la frase e' gia' su disco e si puo' dire subito."""
        percorso, _ = self._percorso(testo)
        return bool(percorso) and os.path.exists(percorso)

    def durata(self, testo):
        """Quanto dura la frase detta, in secondi. 0 se non c'e' (e quindi
        non si dira'): chi calcola i tempi ricade sulle sue costanti."""
        percorso, _ = self._percorso(testo)
        if not percorso or not os.path.exists(percorso):
            return 0.0
        try:
            with wave.open(percorso, "rb") as w:
                return w.getnframes() / float(w.getframerate())
        except Exception:
            return 0.0

    def prepara(self, testi, silenzioso=False):
        """Sintetizza quello che manca. BLOCCANTE: da chiamare a sipario
        chiuso, o da uno script, o da un thread — mai dal ciclo principale."""
        if not self.disponibile:
            return 0
        fatte = 0
        for testo in testi:
            percorso, parlato = self._percorso(testo)
            if not percorso or os.path.exists(percorso):
                continue
            with self._cache_lock:
                if parlato in self._in_corso:
                    continue
                self._in_corso.add(parlato)
            try:
                dati = self.fornitore.sintetizza(parlato)
                if dati is not None:
                    _salva_wav(percorso, dati)
                    fatte += 1
                    if not silenzioso:
                        print(f'[voce] "{parlato}"')
            finally:
                with self._cache_lock:
                    self._in_corso.discard(parlato)
        return fatte

    def prepara_in_sottofondo(self, testi):
        """Come prepara(), ma senza fermare nessuno. Ritorna l'Event che si
        accende quando ha finito, per chi volesse aspettarlo."""
        finito = threading.Event()

        def lavoro():
            try:
                self.prepara(testi, silenzioso=True)
            finally:
                finito.set()

        threading.Thread(target=lavoro, daemon=True).start()
        return finito

    # ---- parlare ----

    def di(self, testo):
        """Mette la frase in coda e dice quanto durera'. 0 = non la dira'.

        Non sintetizza e non aspetta: se la clip non c'e' resta muta. E' la
        stessa scelta delle frasi di riserva — l'esperienza non si ferma per
        un pezzo che manca."""
        percorso, _ = self._percorso(testo)
        if not percorso or not os.path.exists(percorso):
            return 0.0
        try:
            dati, sr = modulo_musica._load_wav(percorso)
        except Exception:
            return 0.0
        if sr != self.sr:
            dati = _ricampiona(dati, sr, self.sr)
        with self._lock:
            self._coda.append(dati)
        self._abbassa_la_musica()
        return len(dati) / float(self.sr)

    def zittisci(self):
        """Svuota la coda e taglia quello che sta dicendo. Serve se una scena
        salta: una voce che continua a parlare su una scritta che non c'e'
        piu' e' peggio del silenzio."""
        with self._lock:
            self._coda.clear()
            self._clip = None
        self._rialza_la_musica()

    @property
    def parla(self):
        with self._lock:
            return self._clip is not None or bool(self._coda)

    # ---- il ciclo lo chiama ad ogni fotogramma ----

    def aggiorna(self, ora=None):
        """Rimette su la musica quando la voce ha finito. Come lo stacco:
        niente thread, niente attese — un controllo per fotogramma."""
        if self._abbassate and not self.parla:
            self._rialza_la_musica()

    # ---- interno ----

    def _abbassa_la_musica(self):
        if self._abbassate:
            return
        for sorgente in self.sorgenti:
            try:
                sorgente.attenua_per_voce(self.attenuazione, fade=0.5)
            except Exception:
                pass
        self._abbassate = True

    def _rialza_la_musica(self):
        if not self._abbassate:
            return
        for sorgente in self.sorgenti:
            try:
                sorgente.attenua_per_voce(1.0, fade=1.2)
            except Exception:
                pass
        self._abbassate = False

    def _callback(self, outdata, frames, time_info, status):
        with self._lock:
            outdata.fill(0)
            scritti = 0
            while scritti < frames:
                if self._clip is None:
                    if not self._coda:
                        break
                    self._clip, self._pos = self._coda.pop(0), 0
                quanti = min(frames - scritti, len(self._clip) - self._pos)
                outdata[scritti:scritti + quanti] = (
                    self._clip[self._pos:self._pos + quanti] * self.volume)
                self._pos += quanti
                scritti += quanti
                if self._pos >= len(self._clip):
                    self._clip = None
        np.clip(outdata, -1.0, 1.0, out=outdata)

    def stop(self):
        self.zittisci()
        if self._stream is None:
            return
        try:
            self._stream.stop()
            self._stream.close()
        except Exception:
            pass
        self._stream = None
