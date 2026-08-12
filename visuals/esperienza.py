"""
L'esperienza: decide cosa mostrare e quando.

E' scritta come macchina a stati e NON aspetta mai. Ad ogni giro del ciclo
principale le si chiede "e adesso?" e lei risponde in un istante. E' la
differenza che permette al sistema di reagire agli occhi: se dormisse, non
potrebbe accorgersi di nulla.

Il filo:
    saluto   -> benvenuto a schermo
    invito   -> "chiudi gli occhi e parlami", finche' non li chiude
    ascolto  -> occhi chiusi, l'utente parla; a schermo il suo volto
    attesa   -> ha riaperto gli occhi: si genera, a schermo "preparo..."
    danza    -> volto, frase, volto, frase, concetto, chiusura

La chiamata a Claude gira in un thread separato: mentre si aspetta la
risposta la webcam continua e le particelle si muovono.
"""

import threading

import occhi as modulo_occhi
import scena as modulo_scena
import testi

# ---------- scritte sempre uguali ----------
SALUTO = "BENVENUTO"
INVITO = "CHIUDI GLI OCCHI E PARLAMI"
ATTESA = "PREPARO LA TUA MEDITAZIONE"
CHIUSURA = ["BUONA MEDITAZIONE", "CHIUDI GLI OCCHI"]

# ---------- tempi (secondi) ----------
DURATA_SALUTO = 4.0
MIN_ASCOLTO = 3.0          # sotto questa durata l'ascolto non puo' finire
MAX_ATTESA_GESTO = 90.0    # se il gesto non arriva mai, si prosegue lo stesso
ATTESA_MINIMA = 3.0        # l'attesa non lampeggia mai: dura almeno cosi'
TRANSIZIONE = 4.0
PERMANENZA_VOLTO = 3.0
PERMANENZA_FRASE = 5.0
PERMANENZA_CONCETTO = 6.0
PERMANENZA_CHIUSURA = 4.0


class Esperienza:
    def __init__(self, scena: modulo_scena.Scena, racconto: str):
        self.scena = scena
        self.racconto = racconto
        self.occhi = modulo_occhi.Rilevatore()

        self.stato = None
        self.t_stato = 0.0
        self.finita = False

        self._ultimo_stato_occhi = None
        self._materiale = None
        self._t_pronto = None

        self.copione = []
        self.indice = 0

    # ---------- avvio ----------

    def avvia(self, ora):
        self.scena.prepara([SALUTO, INVITO, ATTESA] + CHIUSURA)
        self._vai("saluto", ora)
        self.scena.mostra("testo", SALUTO, transizione=3.0)

    # ---------- il ciclo lo chiama ad ogni fotogramma ----------

    def aggiorna(self, ora, punti=None):
        if self.finita:
            return

        stato_occhi = self.occhi.aggiorna(punti, ora)
        if stato_occhi != self._ultimo_stato_occhi:
            print(f"occhi: {stato_occhi}")
            self._ultimo_stato_occhi = stato_occhi

        trascorso = ora - self.t_stato

        if self.stato == "saluto":
            if trascorso >= DURATA_SALUTO:
                self._vai("invito", ora)
                self.scena.mostra("testo", INVITO, transizione=3.0)

        elif self.stato == "invito":
            # si passa oltre quando chiude gli occhi (o dopo molto tempo,
            # per non lasciare il sistema bloccato durante una presentazione)
            if stato_occhi == "chiusi" or trascorso >= MAX_ATTESA_GESTO:
                self._vai("ascolto", ora)
                self.scena.mostra("volto", transizione=TRANSIZIONE)
                print("ascolto: sto ascoltando (il microfono arrivera' dopo)")

        elif self.stato == "ascolto":
            pronto_a_finire = trascorso >= MIN_ASCOLTO
            if (stato_occhi == "aperti" and pronto_a_finire) or trascorso >= MAX_ATTESA_GESTO:
                self._vai("attesa", ora)
                self.scena.mostra("testo", ATTESA, transizione=2.5)
                self._genera_in_background()

        elif self.stato == "attesa":
            if self._materiale is not None and self._t_pronto is None:
                self._prepara_scritte_generate()
                self._t_pronto = ora
            pronto = self._t_pronto is not None
            td_pronto = pronto and (ora - self._t_pronto) >= modulo_scena.TEMPO_DI_PREPARAZIONE
            if pronto and td_pronto and trascorso >= ATTESA_MINIMA:
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
