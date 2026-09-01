"""
L'esperienza: decide cosa mostrare e quando.

E' scritta come macchina a stati e NON aspetta mai. Ad ogni giro del ciclo
principale le si chiede "e adesso?" e lei risponde in un istante. E' la
differenza che permette al sistema di reagire agli occhi: se dormisse, non
potrebbe accorgersi di nulla.

Il filo:
    saluto              -> benvenuto a schermo, a blocchi
    invito              -> "chiudi gli occhi e parlami", a blocchi, finche' non li chiude
    ascolto             -> occhi chiusi, l'utente parla; a schermo il suo volto
    attesa              -> ha riaperto gli occhi: si genera, a schermo i blocchi d'attesa
    danza               -> volto, frase, volto, frase, concetto, chiusura
    invito_meditazione  -> l'ultima scritta della danza resta, finche' non chiude gli occhi
    meditazione         -> occhi chiusi, si medita; si misura solo QUANTO dura
    preparazione_mandala -> ha riaperto gli occhi: si genera il mandala
    mandala             -> il mandala della sessione, particella per particella

SALUTO, INVITO, ATTESA, CHIUSURA e PREPARAZIONE_MANDALA sono tutte SEQUENZE di
schermate, mostrate una dopo l'altra: aggiungerne o toglierne non richiede
altro. ATTESA e PREPARAZIONE_MANDALA sono le sole che si comportano
diversamente: la loro durata totale non e' nota in anticipo (dipende da
quanto ci mette Claude), quindi i loro blocchi scorrono IN LOOP finche' il
materiale non e' pronto, invece di finire e basta.

Il mandala: Claude ne sceglie il carattere di base (petali, anelli, colore)
dal racconto, nella stessa chiamata che genera le frasi — nessuna chiamata in
piu'. La sua complessita' finale invece cresce con quanto l'utente e' rimasto
in meditazione: piu' tempo, piu' dettaglio. E' un calcolo locale, non serve
richiedere altro al modello: il tempo passato lo sappiamo gia'.

La chiamata a Claude gira in un thread separato: mentre si aspetta la
risposta la webcam continua e le particelle si muovono.
"""

import random
import threading

import mandala as modulo_mandala
import movimento as modulo_movimento
import musica as modulo_musica
import occhi as modulo_occhi
import scena as modulo_scena
import stacco as modulo_stacco
import testi

# ---------- scritte sempre uguali ----------
SALUTO = ["BENVENUTO E GRAZIE PER ESSERE QUI"]
INVITO = ["QUANDO TI SENTI PRONTO", "CHIUDI GLI OCCHI E RACCONTAMI CIO CHE VUOI"]
ATTESA = ["PREPARO LA TUA MEDITAZIONE", "CONCENTRATI SUL TUO RESPIRO"]
CHIUSURA = ["È IL MOMENTO DI MEDITARE", "CHIUDI GLI OCCHI QUANDO TI SENTI PRONTO"]
ATTESA_MANDALA = ["STO DISEGNANDO IL TUO MANDALA"]
INVITO_DISSOLUZIONE = ["MUOVI IL VOLTO E LIBERATI DEL MANDALA"]
COMMIATO = ["NIENTE DI BELLO VA TRATTENUTO", "GRAZIE, A PRESTO"]

# Tutte quelle che non dipendono dal racconto: TD puo' disegnarle in anticipo,
# una volta sola, prima che l'esperienza cominci.
SCRITTE_FISSE = (SALUTO + INVITO + ATTESA + ATTESA_MANDALA
                 + INVITO_DISSOLUZIONE + COMMIATO + CHIUSURA)

# ---------- tempi (secondi) ----------
# REGOLA: nessuna scritta resta a schermo meno di LEGGIBILE, e questo tempo si
# conta DA QUANDO E' FORMATA, non da quando parte la transizione — durante la
# transizione le particelle si stanno ancora disponendo e non c'e' niente da
# leggere. Quindi ogni schermata dura: transizione + LEGGIBILE.
# MODALITA' PROVA: durante lo sviluppo aspettare sei secondi a scritta e' una
# tortura. Rimettere a 6.0 (o piu') prima di mostrarlo a qualcuno: una frase
# che si legge di corsa non da' il tempo di sentirla.
LEGGIBILE = 2.0

TRANSIZIONE = 2.0           # quanto dura il passaggio da una forma all'altra (prova; era 4.0)
TRANSIZIONE_BREVE = 1.5     # per i cambi rapidi (blocchi d'attesa) (prova; era 2.5)

# L'apertura ha una transizione tutta sua, molto piu' lenta delle altre: e' la
# nuvola di polvere che si raccoglie nelle prime parole, e vale la pena
# guardarla. Le altre transizioni collegano due scritte, questa apre l'opera.
TRANSIZIONE_APERTURA = 5.0
DURATA_SALUTO = TRANSIZIONE_APERTURA + LEGGIBILE
DURATA_INVITO = TRANSIZIONE + LEGGIBILE   # tranne l'ultimo blocco: quello
                                          # resta finche' non chiude gli occhi
DURATA_ATTESA = TRANSIZIONE_BREVE + LEGGIBILE

MIN_ASCOLTO = 3.0           # sotto questa durata l'ascolto non puo' finire
MAX_ATTESA_GESTO = 90.0     # se il gesto non arriva mai, si prosegue lo stesso

PERMANENZA_VOLTO = 1.5      # il volto non e' da leggere: puo' durare meno
PERMANENZA_FRASE = LEGGIBILE
PERMANENZA_CONCETTO = LEGGIBILE + 2.0   # il concetto finale merita piu' respiro
PERMANENZA_CHIUSURA = LEGGIBILE

# ---------- il tappeto sonoro ----------
# Un sottofondo che accompagna tutta l'esperienza, tranne la meditazione: li'
# tace e lascia il campo alla traccia costruita sull'emozione di chi ascolta.
# E' materiale dello stesso motore musicale, preso dal quadrante della calma —
# la destinazione verso cui ogni sessione tende comunque.
EMOZIONE_TAPPETO = "Q4"
DISSOLVENZA_TAPPETO = 4.0    # quanto ci mette a cambiare volume

VOLUME_APERTURA = 0.70       # saluto e invito
VOLUME_ASCOLTO = 0.30        # mentre la persona parla: si fa da parte
VOLUME_PREPARAZIONE = 0.70   # attesa, frasi personalizzate, danza
VOLUME_MEDITAZIONE = 0.00    # tace del tutto: parla la traccia generata
VOLUME_FINALE = 0.70         # mandala, dissoluzione, commiato

# ---------- fase 2: meditazione ----------
MIN_MEDITAZIONE = 3.0       # una riapertura fulminea non puo' bastare a finirla
MAX_MEDITAZIONE = 600.0     # rete di sicurezza per una presentazione (10 minuti)

# ---------- fase 3: il mandala ----------
DURATA_ATTESA_MANDALA = DURATA_ATTESA   # per ogni blocco, poi si ripete
TRANSIZIONE_MANDALA = 6.0    # il mandala si compone piu' lentamente del resto:
                             # e' il regalo finale, non deve sbrigarsi
SECONDI_PER_LIVELLO = 40.0   # ogni tot secondi di meditazione, un livello di dettaglio in piu'
BONUS_MASSIMO = 3            # tetto ai livelli: oltre, il disegno si affolla
                             # e si legge peggio invece che meglio
PERMANENZA_MANDALA = 12.0    # quanto lo si contempla prima di lasciarlo andare (prova; era 40.0)

# ---------- la dissoluzione ----------
DURATA_INVITO_DISSOLUZIONE = TRANSIZIONE + LEGGIBILE
MAX_DISSOLUZIONE = 60.0      # se non scuote mai, si prosegue lo stesso
# Lo stacco certifica un passaggio di stato, quindi deve avvenire solo dove
# gli occhi vengono davvero ascoltati. Negli altri otto stati chiudere o
# riaprire non fa succedere niente: interrompere li' la musica prometterebbe
# qualcosa che non sta accadendo, ed e' peggio del silenzio.
STATI_CHE_ASCOLTANO_GLI_OCCHI = (
    "invito", "ascolto", "invito_meditazione", "meditazione",
)
STACCO_SEMPRE = False    # True: stacca ad ogni cambio, anche quando e' a vuoto

TRANSIZIONE_LUNGA = 6.0      # per il commiato: le particelle sono sparse fuori
                             # campo e devono rientrare per comporre le parole
PERMANENZA_COMMIATO = LEGGIBILE


class Esperienza:
    def __init__(self, scena: modulo_scena.Scena, racconto: str, ascolto=None,
                 musica=None, tappeto=None, sincronia=None):
        self.scena = scena
        self.racconto = racconto      # ripiego se il microfono non c'e' o non sente
        self.ascolto = ascolto
        self.sincronia = sincronia    # web: sincronizza riflessione e risultati col browser
        self.occhi = modulo_occhi.Rilevatore()
        self.movimento = modulo_movimento.Movimento()
        self._generazione_avviata = False

        self.stato = None
        self.t_stato = 0.0
        self.finita = False

        self._ultimo_stato_occhi = None
        self._materiale = None
        self._t_pronto = None
        self._scritte_pronte = False

        self._indice_blocco = 0
        self._t_blocco = 0.0
        self._durata_meditazione = 0.0

        self.copione = []
        self.indice = 0

        # come l'ascolto: si puo' passare dall'esterno, cosi' l'esperienza
        # si prova senza far davvero partire l'audio
        self.musica = musica if musica is not None else modulo_musica.Music()
        # due sorgenti separate: il tappeto e la traccia della meditazione
        # vivono e sfumano in modo indipendente
        self.tappeto = tappeto if tappeto is not None else modulo_musica.Music()
        self.emozione = "Q2"   # ripiego se la generazione non risponde

        # lo stacco abbassa ENTRAMBE le sorgenti: uscendo dalla meditazione
        # suona la traccia, non il tappeto, e lasciarla su coprirebbe la
        # campana proprio nel passaggio piu' delicato
        self.stacco = modulo_stacco.Stacco(
            (self.tappeto, self.musica), modulo_musica.SAMPLE_RATE
        )

    def imposta_racconto(self, racconto: str):
        """Aggiorna il racconto scritto dall'utente prima della generazione."""
        self.racconto = racconto or self.racconto

    # ---------- avvio ----------

    def prepara_scritte(self):
        """Chiede a TD di disegnare in anticipo tutte le scritte fisse.

        Dopo questa chiamata bisogna lasciar passare del tempo prima di
        poterne mostrare una: TD le disegna e le campiona una alla volta, e
        chiedere una scritta non ancora pronta fa ripiegare sul volto."""
        self.scena.prepara(SCRITTE_FISSE)
        self._scritte_pronte = True

    def mostra_polvere(self):
        """Sparge le particelle, senza transizione.

        Da chiamare a finestra ancora chiusa: quando il sipario si alza si
        vede gia' la nuvola, ferma e sospesa. E' da li' che nasce tutto il
        resto."""
        self.scena.polvere(transizione=0.0)

    def mostra_saluto(self):
        """Mette il benvenuto a schermo SENZA transizione.

        Non serve a main.py, che apre sulla polvere: e' qui per chi volesse
        far partire l'esperienza con il benvenuto gia' composto."""
        self.scena.testo(SALUTO[0], transizione=0.0)

    def avvia(self, ora):
        # se si e' passati da prepara_scritte() non si rifa': ridisegnarle
        # costerebbe un secondo abbondante proprio mentre si parte
        if not self._scritte_pronte:
            self.prepara_scritte()
        self._vai("saluto", ora)
        # Il momento dell'apertura: le particelle sparse si raccolgono nelle
        # prime parole. Piu' lento del resto perche' e' l'inizio, e perche'
        # e' il primo movimento che lo spettatore vede.
        self._mostra_blocco(SALUTO, 0, ora, transizione=TRANSIZIONE_APERTURA)
        self.tappeto.play(EMOZIONE_TAPPETO, fade=DISSOLVENZA_TAPPETO,
                          volume=VOLUME_APERTURA, morbido=True)
        # anche il flusso della traccia si apre ADESSO, muto e senza nulla da
        # suonare: aprirlo piu' tardi, mentre il tappeto suona, farebbe
        # riconfigurare la scheda audio e si sentirebbe un click
        self.musica.apri()
        # e anche il microfono: aprirlo piu' tardi, quando la persona chiude
        # gli occhi, faceva click mentre il tappeto suonava
        if self.ascolto:
            self.ascolto.apri()

    # ---------- il ciclo lo chiama ad ogni fotogramma ----------

    def aggiorna(self, ora, punti=None):
        if self.finita:
            return

        stato_occhi = self.occhi.aggiorna(punti, ora)
        if stato_occhi != self._ultimo_stato_occhi:
            print(f"occhi: {stato_occhi}")
            # la prima lettura non e' un cambiamento: e' solo il primo
            # fotogramma utile, e non merita uno stacco
            conta = STACCO_SEMPRE or self.stato in STATI_CHE_ASCOLTANO_GLI_OCCHI
            if self._ultimo_stato_occhi is not None and conta:
                self.stacco.avvia(ora, chiusura=(stato_occhi == "chiusi"))
            self._ultimo_stato_occhi = stato_occhi

        # lo stacco ha i suoi tempi e non blocca nessuno: avanza qui, un
        # fotogramma alla volta, come la macchina a stati grande
        self.stacco.aggiorna(ora)

        trascorso = ora - self.t_stato

        if self.stato == "saluto":
            if ora - self._t_blocco >= DURATA_SALUTO:
                if self._indice_blocco + 1 < len(SALUTO):
                    self._mostra_blocco(SALUTO, self._indice_blocco + 1, ora)
                else:
                    self._vai("invito", ora)
                    self._mostra_blocco(INVITO, 0, ora)

        elif self.stato == "invito":
            ultimo_blocco = self._indice_blocco >= len(INVITO) - 1
            if not ultimo_blocco and (ora - self._t_blocco) >= DURATA_INVITO:
                self._mostra_blocco(INVITO, self._indice_blocco + 1, ora)

            # si passa oltre quando chiude gli occhi (o dopo molto tempo,
            # per non lasciare il sistema bloccato durante una presentazione)
            if stato_occhi == "chiusi" or trascorso >= MAX_ATTESA_GESTO:
                self._vai("ascolto", ora)
                self.scena.mostra("volto", transizione=TRANSIZIONE)
                # il tappeto si abbassa PRIMA di accendere il microfono: cio'
                # che suona in stanza finisce nella registrazione insieme alla
                # voce, e Whisper deve sentire lei, non la musica
                self.tappeto.volume(VOLUME_ASCOLTO, fade=1.5)
                if self.ascolto:
                    self.ascolto.inizia()

        elif self.stato == "ascolto":
            pronto_a_finire = trascorso >= MIN_ASCOLTO
            if (stato_occhi == "aperti" and pronto_a_finire) or trascorso >= MAX_ATTESA_GESTO:
                if self.ascolto:
                    self.ascolto.ferma()
                self.tappeto.volume(VOLUME_PREPARAZIONE, fade=DISSOLVENZA_TAPPETO)
                self._vai("attesa", ora)
                self._mostra_blocco(ATTESA, 0, ora, TRANSIZIONE_BREVE)
                if not self.ascolto:
                    self._avvia_generazione(self.racconto)

        elif self.stato == "attesa":
            # I blocchi girano in loop finche' il materiale non e' pronto.
            # Quando arriva NON se ne apre un altro: si lascia finire quello
            # in corso. Senza questa condizione una scritta poteva comparire
            # e sparire nello stesso istante, appena Claude rispondeva.
            attesa_finita = (ora - self._t_blocco) >= DURATA_ATTESA
            if self._materiale is None and len(ATTESA) > 1 and attesa_finita:
                prossimo = (self._indice_blocco + 1) % len(ATTESA)
                self._mostra_blocco(ATTESA, prossimo, ora, TRANSIZIONE_BREVE)
                attesa_finita = False

            # prima aspetto la trascrizione, poi parte la generazione
            if self.ascolto and not self._generazione_avviata:
                trascritto = self.ascolto.risultato()
                if trascritto is not None:
                    if trascritto:
                        print(f'ha detto: "{trascritto}"')
                    else:
                        print("ascolto: non ho sentito nulla, uso il racconto di ripiego")
                    self._avvia_generazione(trascritto or self.racconto)

            if self._materiale is not None and self._t_pronto is None:
                self._prepara_scritte_generate()
                self._t_pronto = ora
            pronto = self._t_pronto is not None
            td_pronto = pronto and (ora - self._t_pronto) >= modulo_scena.TEMPO_DI_PREPARAZIONE
            # si esce solo quando la scritta in corso e' stata letta per intero
            if pronto and td_pronto and attesa_finita:
                self._costruisci_copione()
                self._vai("danza", ora)
                self._mostra_scena_corrente()

        elif self.stato == "danza":
            _, _, transizione, permanenza = self.copione[self.indice]
            if trascorso >= transizione + permanenza:
                self.indice += 1
                if self.indice >= len(self.copione):
                    # la danza finisce sull'ultima scritta di CHIUSURA, che e'
                    # gia' l'invito a chiudere gli occhi per meditare
                    self._vai("invito_meditazione", ora)
                else:
                    self.t_stato = ora
                    self._mostra_scena_corrente()

        elif self.stato == "invito_meditazione":
            if stato_occhi == "chiusi" or trascorso >= MAX_ATTESA_GESTO:
                self._vai("meditazione", ora)
                self.scena.mostra("volto", transizione=TRANSIZIONE)
                self.tappeto.volume(VOLUME_MEDITAZIONE, fade=6.0)
                self.musica.play(self.emozione, fade=6.0)

        elif self.stato == "meditazione":
            pronto_a_finire = trascorso >= MIN_MEDITAZIONE
            if (stato_occhi == "aperti" and pronto_a_finire) or trascorso >= MAX_MEDITAZIONE:
                self._durata_meditazione = trascorso
                self._vai("preparazione_mandala", ora)
                self._mostra_blocco(ATTESA_MANDALA, 0, ora, TRANSIZIONE_BREVE)
                self._invia_mandala()
                self.musica.fade_out(6.0)
                self.tappeto.volume(VOLUME_FINALE, fade=6.0)

        elif self.stato == "preparazione_mandala":
            if len(ATTESA_MANDALA) > 1 and (ora - self._t_blocco) >= DURATA_ATTESA_MANDALA:
                prossimo = (self._indice_blocco + 1) % len(ATTESA_MANDALA)
                self._mostra_blocco(ATTESA_MANDALA, prossimo, ora, TRANSIZIONE_BREVE)
            # il mandala e' puro calcolo, pronto quasi subito: qui non si
            # aspetta perche' serva, ma perche' la scritta va letta
            if trascorso >= DURATA_ATTESA_MANDALA:
                self._vai("mandala", ora)
                self.scena.mostra("mandala", transizione=TRANSIZIONE_MANDALA)

        elif self.stato == "mandala":
            # lo si contempla, poi lo si lascia andare: e' il rito che vuole
            # cosi', l'attaccamento anche a cio' che e' bello produce sofferenza
            if trascorso >= PERMANENZA_MANDALA:
                self._vai("invito_dissoluzione", ora)
                self._mostra_blocco(INVITO_DISSOLUZIONE, 0, ora)

        elif self.stato == "invito_dissoluzione":
            if trascorso >= DURATA_INVITO_DISSOLUZIONE:
                # Il mandala torna ED E' GIA' DISFACIBILE: la dissoluzione
                # parte insieme alla sua ricomparsa, non dopo. Le particelle
                # si ricompongono mentre il naso puo' gia' spingerle via —
                # aspettare che la forma fosse completa creava qualche secondo
                # in cui il gesto non produceva nulla, e sembrava rotto.
                self._vai("dissoluzione", ora)
                self.movimento.azzera()
                self.scena.dissolvi(transizione=TRANSIZIONE)
                print("dissoluzione: muovi il volto per disperderlo")

        elif self.stato == "dissoluzione":
            self.movimento.aggiorna(punti, ora)
            if self.movimento.abbastanza() or trascorso >= MAX_DISSOLUZIONE:
                print(f"  disperso (energia del gesto: {self.movimento.energia:.1f})")
                if self.sincronia is not None:
                    self._vai("riflessione", ora)
                    self.scena.mostra("volto", transizione=TRANSIZIONE)
                    ui_apri = getattr(self.scena, "ui_riflessione_apri", None)
                    if ui_apri:
                        ui_apri()
                else:
                    self._vai("commiato", ora)
                    self._mostra_blocco(COMMIATO, 0, ora, transizione=TRANSIZIONE_LUNGA)

        elif self.stato == "riflessione":
            if self.sincronia and self.sincronia.riflessione_inviata.is_set():
                self.sincronia.riflessione_inviata.clear()
                self._vai("risultati", ora)
                self.scena.mostra("volto", transizione=1.0)

        elif self.stato == "risultati":
            if self.sincronia and self.sincronia.risultati_visti.is_set():
                self.sincronia.risultati_visti.clear()
                ui_nascondi = getattr(self.scena, "ui_nascondi", None)
                if ui_nascondi:
                    ui_nascondi()
                self._vai("commiato", ora)
                self._mostra_blocco(COMMIATO, 0, ora, transizione=TRANSIZIONE_LUNGA)

        elif self.stato == "commiato":
            durata = (TRANSIZIONE_LUNGA if self._indice_blocco == 0 else TRANSIZIONE)
            if ora - self._t_blocco >= durata + PERMANENZA_COMMIATO:
                if self._indice_blocco + 1 < len(COMMIATO):
                    self._mostra_blocco(COMMIATO, self._indice_blocco + 1, ora)
                else:
                    self.stato = "fine"
                    self.finita = True
                    self.ferma_suono()
                    print("esperienza: conclusa")

    # ---------- interno ----------

    def ferma_suono(self):
        """Spegne tappeto e traccia. Da chiamare anche se la sessione viene
        interrotta a meta': un flusso audio aperto sopravvive al programma."""
        # uno stacco lasciato a meta' terrebbe la musica attenuata a zero
        self.stacco.annulla()
        for sorgente in (self.tappeto, self.musica):
            try:
                sorgente.stop()
            except Exception:
                pass
        if self.ascolto:
            try:
                self.ascolto.chiudi()
            except Exception:
                pass

    def _vai(self, stato, ora):
        self.stato = stato
        self.t_stato = ora

    def _mostra_blocco(self, blocchi, indice, ora, transizione=TRANSIZIONE):
        """Mostra un blocco di testo di una sequenza (SALUTO/INVITO/ATTESA) e
        ricorda quando e' iniziato, per sapere quando passare al successivo."""
        self._indice_blocco = indice
        self._t_blocco = ora
        self.scena.mostra("testo", blocchi[indice], transizione=transizione)

    def _avvia_generazione(self, racconto):
        """La chiamata a Claude vive in un thread suo: cosi' i blocchi
        d'attesa continuano a scorrere e la webcam a girare mentre si aspetta."""
        self._generazione_avviata = True

        def lavoro():
            self._materiale = testi.genera(racconto)

        print("esperienza: genero le frasi...")
        threading.Thread(target=lavoro, daemon=True).start()

    def _prepara_scritte_generate(self):
        m = self._materiale
        self.emozione = m.get("emozione", "Q2") 
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
            ("testo", m["concetto"], TRANSIZIONE, PERMANENZA_CONCETTO),
        ]
        for scritta in CHIUSURA:
            self.copione.append(("testo", scritta, TRANSIZIONE, PERMANENZA_CHIUSURA))
        self.indice = 0

    def _mostra_scena_corrente(self):
        tipo, contenuto, transizione, _ = self.copione[self.indice]
        self.scena.mostra(tipo, contenuto, transizione)

    def _invia_mandala(self):
        """Combina il carattere scelto da Claude con quanto e' durata la
        meditazione: piu' tempo, piu' dettaglio.

        I petali crescono piu' in fretta degli anelli, e non e' un dettaglio:
        le particelle sono un numero fisso, quindi ogni anello in piu' se le
        divide e toglie definizione a tutti. I petali invece aggiungono
        merletto senza costare nulla. Il seed cambia ad ogni sessione, cosi'
        due mandala con gli stessi parametri non sono mai identici."""
        m = self._materiale
        bonus = min(int(self._durata_meditazione // SECONDI_PER_LIVELLO), BONUS_MASSIMO)
        petali = m["mandala_petali"] + bonus
        anelli = m["mandala_anelli"] + bonus // 2
        seed = random.randint(0, 999_999)
        print(
            f"  meditazione: {self._durata_meditazione:.0f}s -> "
            f"+{bonus} di dettaglio ({petali} petali, {anelli} anelli)"
        )
        self.scena.prepara_mandala(petali, anelli, m["mandala_tonalita"], seed)

        # Lo stesso mandala, ad alta risoluzione, come file da portare via.
        # Gira in un thread: disegnare 260.000 particelle richiede un paio di
        # secondi e il ciclo principale non deve fermarsi per questo.
        self._salva_immagine(petali, anelli, m["mandala_tonalita"], seed)

    def _salva_immagine(self, petali, anelli, tonalita, seed):
        def lavoro():
            percorso = modulo_mandala.salva(petali, anelli, tonalita, seed)
            if percorso:
                print(f"  il tuo mandala e' salvato in: {percorso}")

        threading.Thread(target=lavoro, daemon=True).start()
