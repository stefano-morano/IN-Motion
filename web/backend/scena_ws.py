"""
ScenaWS — versione web di scena.py.

Invece di mandare messaggi OSC a TouchDesigner, mette eventi JSON
in una coda che il WebSocket handler legge e spedisce al browser.
"""
import queue as _q


class ScenaWS:
    TEMPO_DI_PREPARAZIONE = 0.6  # mantenuto per compatibilità con esperienza.py

    def __init__(self, coda: _q.SimpleQueue):
        self._coda = coda

    # ---------------------------------------------------------------- comandi
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
        """La tinta personale, appena Claude ha risposto.

        Il gemello di scena.py: li' e' un messaggio OSC, qui un evento in coda.
        Il browser per ora lo IGNORA — il renderer JS ha ancora la sua copia
        della logica di colore, dove la tinta arriva solo col mandala. Il
        metodo deve esistere lo stesso, perche' esperienza.py e' condivisa fra
        le due versioni e senza di lui la sessione web muore con un
        AttributeError nell'istante in cui il modello risponde."""
        self._coda.put({
            "tipo": "tinta",
            "tonalita": float(tonalita),
            "emozione": str(emozione or "Q2"),
        })

    def tinta_forza(self, valore, durata=12.0):
        """Quanta tinta personale si vede, da 0 (il blu) a 1, in 'durata'
        secondi. Vedi tinta() per il perche' esiste anche qui."""
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
