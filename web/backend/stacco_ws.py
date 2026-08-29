"""
StaccoWS — versione web di stacco.Stacco.

Invece di agire sull'audio Python, manda un evento al browser che
gestisce i fade e sintetizza la campanella con Web Audio API.

Viene iniettato in sys.modules['stacco'] prima che esperienza.py
possa importare il modulo originale (che richiederebbe sounddevice).
"""


class StaccoWS:
    def __init__(self, sorgenti, sr=44100,
                 discesa=2.2, respiro=1.4, ritorno=2.2):
        # Prende la coda dalla prima sorgente MusicaWS
        self._coda = None
        for s in sorgenti:
            c = getattr(s, "_coda", None)
            if c is not None:
                self._coda = c
                break
        self._discesa = discesa
        self._respiro = respiro
        self._ritorno = ritorno

    def avvia(self, ora, chiusura=True):
        if self._coda is not None:
            self._coda.put({
                "tipo": "stacco",
                "chiusura": bool(chiusura),
                "discesa": self._discesa,
                "respiro": self._respiro,
                "ritorno": self._ritorno,
            })

    def aggiorna(self, ora):
        # Il browser gestisce i tempi internamente
        pass

    def annulla(self, ora=None):
        if self._coda is not None:
            self._coda.put({"tipo": "stacco_annulla"})
