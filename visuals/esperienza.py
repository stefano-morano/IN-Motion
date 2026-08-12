"""
L'esperienza: decide cosa mostrare e quando.

E' scritta come macchina a stati e NON aspetta mai. Ad ogni giro del ciclo
principale le si chiede "e adesso?" e lei risponde in un istante. E' la
differenza che permette al sistema di reagire: se dormisse, non potrebbe
accorgersi di nulla — ne' degli occhi che si chiudono, ne' della voce.

La chiamata a Claude gira in un thread separato per lo stesso motivo: mentre
si aspetta la risposta, la webcam continua a girare e le particelle a muoversi.
"""

import threading

import scena as modulo_scena
import testi

# ---------- scritte sempre uguali ----------
INVITO = "ESPRIMITI"
ATTESA = "PREPARO LA TUA MEDITAZIONE"
CHIUSURA = ["BUONA MEDITAZIONE", "CHIUDI GLI OCCHI"]

# ---------- tempi (secondi) ----------
DURATA_INVITO = 5.0        # quanto resta a schermo l'invito iniziale
ATTESA_MINIMA = 3.0        # l'attesa non lampeggia mai: dura almeno cosi'
TRANSIZIONE = 4.0          # quanto dura il passaggio da una forma all'altra
PERMANENZA_VOLTO = 3.0
PERMANENZA_FRASE = 5.0
PERMANENZA_CONCETTO = 6.0
PERMANENZA_CHIUSURA = 4.0


class Esperienza:
    def __init__(self, scena: modulo_scena.Scena, racconto: str):
        self.scena = scena
        self.racconto = racconto

        self.stato = None
        self.t_stato = 0.0
        self.finita = False

        self._materiale = None      # riempito dal thread di generazione
        self._t_pronto = None       # quando le scritte generate sono state preparate

        self.copione = []           # (tipo, contenuto, transizione, permanenza)
        self.indice = 0

    # ---------- avvio ----------

    def avvia(self, ora):
        self.scena.prepara([INVITO, ATTESA] + CHIUSURA)
        self._vai("invito", ora)
        self.scena.mostra("testo", INVITO, transizione=3.0)

    # ---------- il ciclo lo chiama ad ogni fotogramma ----------

    def aggiorna(self, ora):
        if self.finita:
            return
        trascorso = ora - self.t_stato

        if self.stato == "invito":
            if trascorso >= DURATA_INVITO:
                self._vai("attesa", ora)
                self.scena.mostra("testo", ATTESA, transizione=2.5)
                self._genera_in_background()

        elif self.stato == "attesa":
            if self._materiale is not None and self._t_pronto is None:
                # la risposta e' arrivata: preparo le scritte e aspetto che TD
                # le abbia disegnate prima di mostrarle
                self._prepara_scritte_generate()
                self._t_pronto = ora
            pronto = self._t_pronto is not None
            passato_abbastanza = trascorso >= ATTESA_MINIMA
            td_pronto = pronto and (ora - self._t_pronto) >= modulo_scena.TEMPO_DI_PREPARAZIONE
            if pronto and passato_abbastanza and td_pronto:
                self._costruisci_copione()
                self._vai("danza", ora)
                self._mostra_scena_corrente()

        elif self.stato == "danza":
            _, _, transizione, permanenza = self.copione[self.indice]
            if trascorso >= transizione + permanenza:
                self.indice += 1
                if self.indice >= len(self.copione):
                    self.stato = "fine"
                    self.finita = True
                    print("esperienza: conclusa")
                else:
                    self.t_stato = ora
                    self._mostra_scena_corrente()

    # ---------- interno ----------

    def _vai(self, stato, ora):
        self.stato = stato
        self.t_stato = ora

    def _genera_in_background(self):
        """La chiamata a Claude vive in un thread suo: cosi' la scritta di
        attesa continua a fluttuare e la webcam a girare mentre si aspetta."""
        def lavoro():
            self._materiale = testi.genera(self.racconto)

        print("esperienza: genero le frasi...")
        threading.Thread(target=lavoro, daemon=True).start()

    def _prepara_scritte_generate(self):
        m = self._materiale
        print(f"  frase 1:  {m['frase_1']}")
        print(f"  frase 2:  {m['frase_2']}")
        print(f"  concetto: {m['concetto']}")
        if m["segnale_disagio"]:
            print("  (segnalata una possibile sofferenza seria)")
        self.scena.prepara([m["frase_1"], m["frase_2"], m["concetto"]])

    def _costruisci_copione(self):
        m = self._materiale
        self.copione = [
            ("volto", "", TRANSIZIONE, PERMANENZA_VOLTO),
            ("testo", m["frase_1"], TRANSIZIONE, PERMANENZA_FRASE),
            ("volto", "", TRANSIZIONE, PERMANENZA_VOLTO),
            ("testo", m["frase_2"], TRANSIZIONE, PERMANENZA_FRASE),
            ("testo", m["concetto"], 5.0, PERMANENZA_CONCETTO),
        ]
        for scritta in CHIUSURA:
            self.copione.append(("testo", scritta, TRANSIZIONE, PERMANENZA_CHIUSURA))
        self.copione.append(("volto", "", 5.0, 2.0))
        self.indice = 0

    def _mostra_scena_corrente(self):
        tipo, contenuto, transizione, _ = self.copione[self.indice]
        self.scena.mostra(tipo, contenuto, transizione)
