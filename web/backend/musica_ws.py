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
        self._emozione = None
        self._morbido = False
        self._pronta = False

    def _put(self, evento: dict):
        self._coda.put(evento)

    # ---------------------------------------------------------------- interfaccia musica.Music
    def carica(self, emozione, loop=True, morbido=False):
        self._emozione = emozione
        # 'morbido' va RICORDATO, non solo ricevuto: il tappeto si carica qui e
        # parte con parti(), che di morbido non sa niente. Restando False in
        # parti(), il tappeto suonava la traccia Q4 cosi' com'e' — e sotto le
        # scritte c'era piu' movimento di quanto dovesse.
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
        # Il browser non ha bisogno di pre-aprire il flusso audio
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

    # Chiamato da StaccoWS: moltiplicatore di volume (0 = silenzio, 1 = normale)
    def attenua(self, val, fade=0.0):
        self._put({
            "tipo": "musica", "sorgente": self._nome, "azione": "attenua",
            "val": float(val), "fade": float(fade),
        })

    # Chiamato da stacco.Stacco (versione originale) — non raggiunto con StaccoWS
    def suona_campione(self, dati):
        pass
