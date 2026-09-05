"""
VoceWS — stub web della guida vocale.

L'esperienza desktop usa voce.py (ElevenLabs/Polly + sounddevice). Sul browser
la TTS non e' ancora collegata: questo stub espone la stessa API minima cosi'
esperienza.py non si blocca in attesa della voce e non apre flussi audio locali.
"""

import threading


class VoceWS:
    def __init__(self, sorgenti_da_abbassare=(), volume=0.75, attenuazione=0.35, sr=None):
        self.sorgenti = tuple(sorgenti_da_abbassare)
        self.volume = volume
        self.attenuazione = attenuazione
        self.sr = sr

    @property
    def disponibile(self):
        return False

    def apri(self):
        return True

    def pronta(self, testo):
        return True

    def durata(self, testo):
        # 0 → esperienza ricade sui tempi LEGGIBILE (niente attesa TTS)
        return 0.0

    def prepara(self, testi, silenzioso=False):
        return 0

    def prepara_in_sottofondo(self, testi):
        finito = threading.Event()
        finito.set()
        return finito

    def di(self, testo):
        return 0.0

    def zittisci(self):
        pass

    def aggiorna(self, ora=None):
        pass

    def stop(self):
        pass
