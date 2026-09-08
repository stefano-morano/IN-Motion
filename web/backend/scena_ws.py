"""
ScenaWS — web version of scena.py.

Instead of sending OSC messages to TouchDesigner, it puts JSON events
on a queue that the WebSocket handler reads and sends to the browser.
"""
import queue as _q


class ScenaWS:
    TEMPO_DI_PREPARAZIONE = 0.6  # kept for compatibility with esperienza.py

    def __init__(self, coda: _q.SimpleQueue):
        self._coda = coda

    # ---------------------------------------------------------------- commands
    def prepara(self, frasi):
        frasi = [f for f in (frasi or []) if f]
        if frasi:
            self._coda.put({"tipo": "prepara", "frasi": frasi})

    def prepara_mandala(self, petali, anelli, tonalita, seed, emozione="Q2"):
        self._coda.put({
            "tipo": "prepara_mandala",
            "petali": int(petali),
            "anelli": int(anelli),
            "tonalita": float(tonalita),
            "seed": int(seed),
            "emozione": str(emozione or "Q2"),
        })

    def tinta(self, tonalita, emozione="Q2"):
        """The personal tint, as soon as Claude has answered.

        Twin of scena.py: there it is an OSC message, here a queued event.
        The browser currently IGNORES it — the JS renderer still has its own
        copy of the color logic, where the tint arrives only with the mandala.
        The method must exist anyway, because esperienza.py is shared between
        both versions and without it the web session dies with an
        AttributeError the instant the model responds."""
        self._coda.put({
            "tipo": "tinta",
            "tonalita": float(tonalita),
            "emozione": str(emozione or "Q2"),
        })

    def tinta_forza(self, valore, durata=12.0):
        """How much personal tint is visible, from 0 (the blue) to 1, over
        'durata' seconds. See tinta() for why this exists here too."""
        self._coda.put({
            "tipo": "tinta_forza",
            "valore": float(valore),
            "durata": float(durata),
        })

    def polvere(self, transizione=0.0):
        self._coda.put({"tipo": "vai_a", "scena": "polvere",
                        "testo": "", "durata": float(transizione)})

    def volto(self, transizione=4.0):
        self._coda.put({"tipo": "vai_a", "scena": "volto",
                        "testo": "", "durata": float(transizione)})

    def testo(self, frase, transizione=4.0):
        self._coda.put({"tipo": "vai_a", "scena": "testo",
                        "testo": frase, "durata": float(transizione)})

    def dissolvi(self, transizione=0.0):
        self._coda.put({"tipo": "vai_a", "scena": "dissoluzione",
                        "testo": "", "durata": float(transizione)})

    def mostra(self, tipo, contenuto="", transizione=4.0):
        if tipo == "volto":
            self.volto(transizione)
        elif tipo == "dissoluzione":
            self.dissolvi()
        elif tipo == "polvere":
            self.polvere(transizione)
        elif tipo == "mandala":
            self._coda.put({"tipo": "vai_a", "scena": "mandala",
                            "testo": "", "durata": float(transizione)})
        else:
            self.testo(contenuto, transizione)

    def finestra(self, apri=True):
        self._coda.put({"tipo": "finestra", "apri": bool(apri)})

    def buio(self):
        self._coda.put({"tipo": "buio"})

    def accendi(self, durata=4.0):
        self._coda.put({"tipo": "accendi", "durata": float(durata)})

    def azzera(self):
        self._coda.put({"tipo": "azzera"})

    def ui_riflessione_apri(self):
        self._coda.put({"tipo": "ui", "fase": "riflessione", "azione": "apri"})

    def ui_nascondi(self):
        self._coda.put({"tipo": "ui", "fase": "nascondi"})
