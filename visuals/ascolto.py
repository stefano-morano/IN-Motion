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
LINGUA = "it"

# "small" e' un buon compromesso per l'italiano. "base" e' piu' veloce ma
# sbaglia di piu' sui nomi e sulle frasi smozzicate; "medium" e' piu' preciso
# ma aggiunge secondi di attesa proprio nel momento piu' delicato.
DIMENSIONE_MODELLO = "small"

DURATA_MINIMA = 0.7      # sotto questa soglia non c'e' niente da trascrivere


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

    def inizia(self):
        """Comincia a registrare. Non solleva eccezioni: se il microfono non e'
        disponibile lo dice e il sistema prosegue senza."""
        self._pezzi = []
        self._testo = None

        def raccogli(dati, fotogrammi, tempo, stato):
            self._pezzi.append(dati.copy())

        try:
            self._stream = sd.InputStream(
                samplerate=FREQUENZA, channels=1, dtype="float32", callback=raccogli
            )
            self._stream.start()
            self.attivo = True
            print("ascolto: registro")
        except Exception as errore:
            print(f"ascolto: microfono non disponibile ({errore})")
            self._stream = None
            self.attivo = False
            self._testo = ""

    def ferma(self):
        """Chiude la registrazione e avvia la trascrizione in background."""
        if not self.attivo:
            return
        self.attivo = False

        if self._stream is not None:
            self._stream.stop()
            self._stream.close()
            self._stream = None

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

    def risultato(self):
        """Il testo trascritto, oppure None se sta ancora lavorando."""
        return self._testo
