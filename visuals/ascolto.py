"""
L'ascolto: registra la voce mentre l'utente ha gli occhi chiusi e la trascrive.

La trascrizione avviene IN LOCALE, con Whisper. L'audio non lascia mai questo
computer: esce solo il testo, e solo verso Claude. E' la stessa scelta fatta
per il volto — a TouchDesigner arrivano coordinate, mai il video.

Come per tutto il resto, niente qui blocca il ciclo principale: la
registrazione gira per conto suo e la trascrizione in un thread separato,
cosi' la webcam continua e le particelle si muovono anche durante l'attesa.
"""

import threading

import numpy as np
import sounddevice as sd
from faster_whisper import WhisperModel

FREQUENZA = 16000        # Whisper lavora a 16 kHz
LINGUA = "en"   # la lingua dell'opera: chi partecipa racconta in inglese

# "small" e' un buon compromesso per l'italiano. "base" e' piu' veloce ma
# sbaglia di piu' sui nomi e sulle frasi smozzicate; "medium" e' piu' preciso
# ma aggiunge secondi di attesa proprio nel momento piu' delicato.
DIMENSIONE_MODELLO = "small"

DURATA_MINIMA = 0.7      # sotto questa soglia non c'e' niente da trascrivere

# Un blocco generoso da' respiro alla scheda audio: mentre Whisper trascrive
# la CPU e' satura, e con blocchi piccoli il flusso resta a secco — che si
# sente come un crepitio.
BLOCCO = 2048


class Ascolto:
    """Registra a comando e trascrive quando gli si dice di smettere."""

    def __init__(self, dimensione=DIMENSIONE_MODELLO):
        print(f"ascolto: carico il modello Whisper '{dimensione}'...")
        # int8 su CPU: molto piu' veloce e, per il parlato normale,
        # indistinguibile in qualita'
        self.modello = WhisperModel(dimensione, device="cpu", compute_type="int8")
        print("ascolto: modello pronto")

        self._pezzi = []
        self._stream = None
        self._testo = None
        self.attivo = False

    # ---------- registrazione ----------

    def apri(self):
        """Apre il microfono, se non lo e' gia'.

        Il flusso resta aperto per TUTTA la sessione, anche quando non stiamo
        registrando: aprirlo e chiuderlo mentre la musica suona fa
        riconfigurare la scheda audio, e si sente come un click. Quello che si
        accende e si spegne e' solo un interruttore: il callback gira sempre,
        ma tiene i campioni soltanto quando serve."""
        if self._stream is not None:
            return True

        def raccogli(dati, fotogrammi, tempo, stato):
            if self.attivo:
                self._pezzi.append(dati.copy())

        try:
            self._stream = sd.InputStream(
                samplerate=FREQUENZA, channels=1, dtype="float32",
                blocksize=BLOCCO, latency="high", callback=raccogli
            )
            self._stream.start()
            return True
        except Exception as errore:
            print(f"ascolto: microfono non disponibile ({errore})")
            self._stream = None
            return False

    def inizia(self):
        """Comincia a tenere i campioni. Non solleva eccezioni: se il microfono
        non e' disponibile lo dice e il sistema prosegue senza."""
        self._pezzi = []
        self._testo = None
        if not self.apri():
            self.attivo = False
            self._testo = ""
            return
        self.attivo = True
        print("ascolto: registro")

    def ferma(self):
        """Chiude la registrazione e avvia la trascrizione in background."""
        if not self.attivo:
            return
        self.attivo = False      # il flusso resta aperto: chiuderlo farebbe click

        audio = (
            np.concatenate(self._pezzi).flatten()
            if self._pezzi
            else np.zeros(0, dtype="float32")
        )
        secondi = len(audio) / FREQUENZA
        print(f"ascolto: registrati {secondi:.1f}s, trascrivo...")
        threading.Thread(target=self._trascrivi, args=(audio,), daemon=True).start()

    # ---------- trascrizione ----------

    def _trascrivi(self, audio):
        if len(audio) < FREQUENZA * DURATA_MINIMA:
            self._testo = ""
            return
        try:
            # vad_filter scarta i silenzi: meno audio da elaborare, quindi
            # meno attesa, e nessuna frase inventata sul rumore di fondo
            segmenti, _ = self.modello.transcribe(
                audio, language=LINGUA, vad_filter=True
            )
            self._testo = " ".join(s.text.strip() for s in segmenti).strip()
        except Exception as errore:
            print(f"ascolto: trascrizione fallita ({errore})")
            self._testo = ""

    def chiudi(self):
        """Chiude il microfono. Da chiamare una volta sola, a fine sessione."""
        if self._stream is None:
            return
        try:
            self._stream.stop()
            self._stream.close()
        except Exception:
            pass
        self._stream = None

    def risultato(self):
        """Il testo trascritto, oppure None se sta ancora lavorando."""
        return self._testo
