"""
AscoltoWS — versione web di ascolto.Ascolto.

Il browser cattura l'audio con MediaRecorder e lo manda come messaggio
binario WebSocket quando la registrazione finisce. Qui lo riceviamo,
lo salviamo in un file temporaneo e lo trascriviamo con Whisper.

Il modello Whisper viene caricato una volta sola al lancio del server
(in un thread separato per non rallentare l'avvio).
"""
import os
import queue
import tempfile
import threading
import time

# Pre-carica il modello al lancio, non alla prima sessione
_MODELLO = None
_MODELLO_LOCK = threading.Lock()


def _carica_modello():
    global _MODELLO
    print("ascolto: carico Whisper 'small'...")
    try:
        from faster_whisper import WhisperModel
        with _MODELLO_LOCK:
            _MODELLO = WhisperModel("small", device="cpu", compute_type="int8")
        print("ascolto: modello pronto")
    except Exception as e:
        print(f"ascolto: Whisper non disponibile ({e})")


threading.Thread(target=_carica_modello, daemon=True).start()


class AscoltoWS:
    """Duck-type compatibile con ascolto.Ascolto."""

    def __init__(self, coda_out: queue.SimpleQueue, stato_sessione):
        self._coda_out = coda_out
        self._stato = stato_sessione
        self._testo = None
        self.attivo = False

    # ---------------------------------------------------------------- API
    def apri(self):
        """Dice al browser di tenere pronto il microfono."""
        self._coda_out.put({"tipo": "ascolto", "azione": "apri"})

    def inizia(self):
        """Dice al browser di cominciare a registrare."""
        self.attivo = True
        self._testo = None
        self._stato.svuota_audio()
        self._coda_out.put({"tipo": "ascolto", "azione": "inizia"})

    def ferma(self):
        """Dice al browser di fermarsi e mandare l'audio. Avvia la trascrizione."""
        if not self.attivo:
            return
        self.attivo = False
        self._coda_out.put({"tipo": "ascolto", "azione": "ferma"})
        threading.Thread(target=self._attendi_e_trascrivi, daemon=True).start()

    def risultato(self):
        """Restituisce il testo trascritto, o None se ancora in lavorazione."""
        return self._testo

    def chiudi(self):
        pass

    # ---------------------------------------------------------------- interno
    def _attendi_e_trascrivi(self):
        """Aspetta l'audio dal browser, poi trascrive."""
        t0 = time.time()
        while time.time() - t0 < 20.0:
            dati = self._stato.consuma_audio()
            if dati is not None:
                self._trascrivi(dati)
                return
            time.sleep(0.1)
        print("ascolto: nessun audio ricevuto entro 20s, uso racconto di riserva")
        self._testo = ""

    def _trascrivi(self, dati_bytes: bytes):
        with _MODELLO_LOCK:
            modello = _MODELLO

        if modello is None:
            print("ascolto: modello non disponibile, trascrizione saltata")
            self._testo = ""
            return

        percorso = None
        try:
            # Il browser manda WebM/Opus da MediaRecorder
            with tempfile.NamedTemporaryFile(suffix=".webm", delete=False) as f:
                f.write(dati_bytes)
                percorso = f.name

            segmenti, _ = modello.transcribe(
                percorso, language="en", vad_filter=True
            )
            self._testo = " ".join(s.text.strip() for s in segmenti).strip()
            print(f'ascolto: "{self._testo}"')
        except Exception as e:
            print(f"ascolto: errore trascrizione ({e})")
            self._testo = ""
        finally:
            if percorso:
                try:
                    os.unlink(percorso)
                except OSError:
                    pass
