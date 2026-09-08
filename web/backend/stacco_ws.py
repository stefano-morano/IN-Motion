"""
StaccoWS — web version of stacco.Stacco.

Instead of acting on Python audio, it sends an event to the browser which
handles the fades and synthesizes the bell with the Web Audio API.

Injected into sys.modules['stacco'] before esperienza.py can import the
original module (which would require sounddevice).
"""


class StaccoWS:
    def __init__(self, sorgenti, sr=44100, attenuazione=0.3,
                 discesa=2.2, respiro=1.4, ritorno=2.2):
        # Take the queue from the first MusicaWS source
        self._coda = None
        for s in sorgenti:
            c = getattr(s, "_coda", None)
            if c is not None:
                self._coda = c
                break
        self.attenuazione = attenuazione
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
        # The browser handles timing internally
        pass

    def annulla(self, ora=None):
        if self._coda is not None:
            self._coda.put({"tipo": "stacco_annulla"})
