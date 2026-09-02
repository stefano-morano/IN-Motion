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
        self._caricata = False

    def _put(self, evento: dict):
        self._coda.put(evento)

    # ---------------------------------------------------------------- interfaccia musica.Music
    def play(self, emozione, fade=0.0, volume=1.0, morbido=False):
        self._caricata = True
        self._put({
            "tipo": "musica", "sorgente": self._nome, "azione": "play",
            "emozione": emozione, "fade": float(fade),
            "volume": float(volume), "morbido": bool(morbido),
        })

    # ------------------------------------------------- carica / parti
    # In Python il caricamento (lettura del wav, ricampionamento, filtro) ferma
    # il programma per oltre un secondo, quindi e' separato dalla partenza: si
    # carica a sipario chiuso e si fa partire al momento giusto. Nel browser
    # costa meno, ma la separazione va mantenuta lo stesso — a deciderla e'
    # esperienza.py, che e' condiviso fra le due versioni.
    def carica(self, emozione, loop=True, morbido=False):
        """Prepara la traccia senza farla partire: resta muta e pronta."""
        self._caricata = True
        self._put({
            "tipo": "musica", "sorgente": self._nome, "azione": "carica",
            "emozione": emozione, "loop": bool(loop), "morbido": bool(morbido),
        })
        return emozione

    def parti(self, fade=3.0, volume=1.0, curva=1.0):
        """Fa salire il volume della traccia gia' caricata.

        'curva' > 1 rende la salita lenta all'inizio e rapida alla fine: serve
        a farla coincidere con la dissolvenza visiva, che per come funziona
        l'occhio non puo' essere lineare."""
        self._put({
            "tipo": "musica", "sorgente": self._nome, "azione": "parti",
            "fade": float(fade), "volume": float(volume), "curva": float(curva),
        })

    @property
    def pronta(self):
        """True se una traccia e' gia' stata chiesta e aspetta solo di partire."""
        return self._caricata

    def apri(self):
        # Il browser non ha bisogno di pre-aprire il flusso audio
        pass

    def volume(self, v, fade=0.0, curva=1.0):
        self._put({
            "tipo": "musica", "sorgente": self._nome, "azione": "volume",
            "volume": float(v), "fade": float(fade), "curva": float(curva),
        })

    def fade_out(self, durata):
        self._put({
            "tipo": "musica", "sorgente": self._nome,
            "azione": "fade_out", "durata": float(durata),
        })

    def ferma(self):
        self._caricata = False
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
