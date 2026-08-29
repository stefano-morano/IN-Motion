"""
MusicaWS — versione web di musica.Music.

Mette comandi JSON in coda. Il browser li riceve e usa Web Audio API
per suonare i file .wav dalla libreria pre-generata.
"""
import queue as _q

SAMPLE_RATE = 44100  # usato da esperienza.py per costruire stacco


class MusicaWS:
    def __init__(self, coda: _q.SimpleQueue, nome: str):
        self._coda = coda
        self._nome = nome

    def _put(self, evento: dict):
        self._coda.put(evento)

    # ---------------------------------------------------------------- interfaccia musica.Music
    def play(self, emozione, fade=0.0, volume=1.0, morbido=False):
        self._put({
            "tipo": "musica", "sorgente": self._nome, "azione": "play",
            "emozione": emozione, "fade": float(fade),
            "volume": float(volume), "morbido": bool(morbido),
        })

    def apri(self):
        # Il browser non ha bisogno di pre-aprire il flusso audio
        pass

    def volume(self, v, fade=0.0):
        self._put({
            "tipo": "musica", "sorgente": self._nome, "azione": "volume",
            "volume": float(v), "fade": float(fade),
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

    # Chiamato da StaccoWS: moltiplicatore di volume (0 = silenzio, 1 = normale)
    def attenua(self, val, fade=0.0):
        self._put({
            "tipo": "musica", "sorgente": self._nome, "azione": "attenua",
            "val": float(val), "fade": float(fade),
        })

    # Chiamato da stacco.Stacco (versione originale) — non raggiunto con StaccoWS
    def suona_campione(self, dati):
        pass
