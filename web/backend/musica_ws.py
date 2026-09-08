"""
MusicaWS — web version of musica.Music.

Queues JSON commands. The browser receives them and uses the Web Audio API
to play .wav files from the pre-generated library.
"""
import queue as _q

SAMPLE_RATE = 44100  # used by esperienza.py to build stacco


class MusicaWS:
    def __init__(self, coda: _q.SimpleQueue, nome: str):
        self._coda = coda
        self._nome = nome
        self._emozione = None
        self._morbido = False
        self._pronta = False

    def _put(self, evento: dict):
        self._coda.put(evento)

    # ---------------------------------------------------------------- musica.Music interface
    def carica(self, emozione, loop=True, morbido=False):
        self._emozione = emozione
        # 'morbido' must be REMEMBERED, not only received: the bed loads here and
        # starts with parti(), which knows nothing about soft mode. Leaving it
        # False in parti() made the bed play the Q4 track as-is — and under the
        # text there was more movement than there should have been.
        self._morbido = bool(morbido)
        self._pronta = True

    def parti(self, fade=3.0, volume=1.0, curva=1.0):
        if not self._emozione:
            return
        self._put({
            "tipo": "musica", "sorgente": self._nome, "azione": "play",
            "emozione": self._emozione, "fade": float(fade),
            "volume": float(volume), "morbido": self._morbido,
            "curva": float(curva),
        })

    def play(self, emozione, fade=0.0, volume=1.0, morbido=False, loop=True):
        self.carica(emozione, loop=loop, morbido=morbido)
        self._put({
            "tipo": "musica", "sorgente": self._nome, "azione": "play",
            "emozione": emozione, "fade": float(fade),
            "volume": float(volume), "morbido": bool(morbido),
        })

    def apri(self):
        # The browser does not need to pre-open the audio stream
        pass

    @property
    def pronta(self):
        return self._pronta

    def volume(self, v, fade=0.0, curva=1.0):
        self._put({
            "tipo": "musica", "sorgente": self._nome, "azione": "volume",
            "volume": float(v), "fade": float(fade),
            "curva": float(curva),
        })

    def fade_out(self, durata):
        self._put({
            "tipo": "musica", "sorgente": self._nome,
            "azione": "fade_out", "durata": float(durata),
        })

    def ferma(self):
        self._put({"tipo": "musica", "sorgente": self._nome, "azione": "ferma"})

    def stop(self):
        self.ferma()

    # Called by StaccoWS: volume multiplier (0 = silence, 1 = normal)
    def attenua(self, val, fade=0.0):
        self._put({
            "tipo": "musica", "sorgente": self._nome, "azione": "attenua",
            "val": float(val), "fade": float(fade),
        })

    # Called by stacco.Stacco (original version) — not reached with StaccoWS
    def suona_campione(self, dati):
        pass
