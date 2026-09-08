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
import voce as modulo_voce

# ---------- scritte sempre uguali ----------
# Per il saluto, l'invito, la chiusura e il commiato ci sono piu' varianti: se
# ne sceglie una a caso all'avvio del processo (un'esecuzione = una sessione),
# cosi' chi rifa' l'esperienza piu' volte — prove, dimostrazioni — non sente
# sempre le stesse parole. La macchina a stati usa len(...) per sapere quando
# passare oltre, quindi le varianti non devono avere tutte lo stesso numero di
# righe; devono pero' restare entro i 42 caratteri per riga (vedi MAX_CARATTERI
# in testi.py) e coprire lo stesso contenuto funzionale delle altre — INVITO,
# in particolare, deve sempre dire di chiudere gli occhi E raccontare.
# LA LINGUA DELL'OPERA E' L'INGLESE: le scritte, la voce che le legge e il
# racconto di chi partecipa. Non e' una traduzione della versione italiana —
# e' la lingua in cui il pezzo si mostra. Cambiarla vuol dire toccare tre
# posti: queste scritte, il prompt in testi.py, e LINGUA in ascolto.py e in
# voce.py.
SALUTO_BASE = "THANK YOU FOR BEING HERE"


def saluto_per(nome=None):
    """Opening line, personalized with the participant's first name when known.

    Particle text stays within MAX_CARATTERI (42); a long name becomes a
    second beat so the line does not spill.
    """
    nome = (nome or "").strip()
    if not nome:
        return [SALUTO_BASE]
    nome_vis = nome.upper()
    frase = f"{SALUTO_BASE}, {nome_vis}"
    if len(frase) <= testi.MAX_CARATTERI:
        return [frase]
    return [f"{SALUTO_BASE},", nome_vis[:testi.MAX_CARATTERI]]


# Kept as a list-of-lists so prepara_voce.py can still walk "variants".
SALUTO_VARIANTI = [
    [SALUTO_BASE],
]
INVITO_VARIANTI = [
    ["WHEN YOU FEEL READY", "CLOSE YOUR EYES AND TELL ME ANYTHING"],
    ["TAKE ALL THE TIME YOU NEED", "CLOSE YOUR EYES, TELL ME WHAT YOU CARRY"],
    ["NO HURRY", "CLOSE YOUR EYES AND TELL ME HOW YOU ARE"],
]
CHIUSURA_VARIANTI = [
    ["IT'S TIME TO MEDITATE", "CLOSE YOUR EYES WHEN YOU FEEL READY"],
    ["NOW IT'S YOUR TURN, IN SILENCE", "CLOSE YOUR EYES WHEN YOU'RE READY"],
    ["YOUR BREATH ALREADY KNOWS", "CLOSE YOUR EYES AND LET IT LEAD"],
]
COMMIATO_VARIANTI = [
    ["NOTHING BEAUTIFUL IS MEANT TO BE KEPT", "THANK YOU, SEE YOU SOON"],
    ["WHAT NEEDED TO HAPPEN HAS HAPPENED", "THANK YOU, TRULY"],
    ["TAKE ONLY WHAT YOU NEED WITH YOU", "SEE YOU SOON"],
]

SALUTO = saluto_per(None)   # default without name; each session may override
INVITO = random.choice(INVITO_VARIANTI)
CHIUSURA = random.choice(CHIUSURA_VARIANTI)
COMMIATO = random.choice(COMMIATO_VARIANTI)

ATTESA = ["I'M PREPARING YOUR MEDITATION", "FOCUS ON YOUR BREATH"]
ATTESA_MANDALA = ["I'M DRAWING YOUR MANDALA"]
INVITO_DISSOLUZIONE = ["MOVE YOUR FACE TO RELEASE THE MANDALA"]
# Solo sul web (con sincronia): dopo il mandala si chiede come ci si sente.
INVITO_RIFLESSIONE = "TELL ME WHAT YOU FEEL AFTER THE MEDITATION"

# Tutte quelle che non dipendono dal racconto: TD puo' disegnarle in anticipo,
# una volta sola, prima che l'esperienza cominci.
SCRITTE_FISSE = (SALUTO + INVITO + ATTESA + ATTESA_MANDALA
                 + INVITO_DISSOLUZIONE + [INVITO_RIFLESSIONE] + COMMIATO + CHIUSURA)

# Alla voce si fa preparare qualcosa in piu': anche le frasi di RISERVA, quelle
# che entrano quando Claude non risponde. Non stanno in SCRITTE_FISSE perche'
# TD non deve disegnarle in anticipo — nella stragrande maggioranza delle
# sessioni non serviranno — ma sintetizzarle costa una volta sola sessanta
# caratteri, e senza di loro il ripiego sarebbe MUTO: proprio quando qualcosa
# si e' rotto, la guida smetterebbe di parlare. Un ripiego che funziona a
# meta' non e' un ripiego.
SCRITTE_DA_DIRE = SCRITTE_FISSE + [
    testi.RISERVA[campo] for campo in testi.CAMPI_TESTO]

# ---------- tempi (secondi) ----------
# REGOLA: nessuna scritta resta a schermo meno di LEGGIBILE, e questo tempo si
# conta DA QUANDO E' FORMATA, non da quando parte la transizione — durante la
# transizione le particelle si stanno ancora disponendo e non c'e' niente da
# leggere. Quindi ogni schermata dura: transizione + LEGGIBILE.
# E DA QUANDO C'E' LA VOCE, quel minimo puo' non bastare: se la guida ci mette
# di piu' a dire la frase, la scritta resta finche' non ha finito. La durata
# vera di ogni schermata non e' quindi piu' una costante — si calcola in
# _mostra_blocco() e vive in self._durata_blocco. L'unica eccezione e'
# l'ultimo blocco dell'invito, che resta a schermo finche' non chiude gli occhi.
# MODALITA' PROVA: durante lo sviluppo si puo' abbassare a 2.0, ma prima di
# mostrarlo a qualcuno va rimesso a 6.0 (o piu'): una frase che si legge di
# corsa non da' il tempo di sentirla.
LEGGIBILE = 6.0

TRANSIZIONE = 2.0           # quanto dura il passaggio da una forma all'altra (prova; era 4.0)
TRANSIZIONE_BREVE = 1.5     # per i cambi rapidi (blocchi d'attesa) (prova; era 2.5)

# L'apertura ha una transizione tutta sua, molto piu' lenta delle altre: e' la
# nuvola di polvere che si raccoglie nelle prime parole, e vale la pena
# guardarla. Le altre transizioni collegano due scritte, questa apre l'opera.
TRANSIZIONE_APERTURA = 5.0

MIN_ASCOLTO = 3.0           # sotto questa durata l'ascolto non puo' finire
MAX_ATTESA_GESTO = 90.0     # se il gesto non arriva mai, si prosegue lo stesso

PERMANENZA_VOLTO = 1.5      # il volto non e' da leggere: puo' durare meno
PERMANENZA_FRASE = LEGGIBILE
PERMANENZA_CONCETTO = LEGGIBILE + 2.0   # il concetto finale merita piu' respiro

# Il motore musicale (music/reference_select.py) fa scendere l'energia
# lentamente per Q1/Q2 (si parte da un'arousal alta), mentre per Q3/Q4 e'
# gia' vicina alla calma quando la danza finisce. Per Q1/Q2 il concetto
# finale resta a schermo un po' di piu': la musica sotto sta ancora
# atterrando, e il testo non deve anticipare un arrivo che il suono non ha
# ancora fatto.
RESPIRO_EXTRA_DISCESA = 2.0
QUADRANTI_IN_DISCESA = ("Q1", "Q2")
PERMANENZA_CHIUSURA = LEGGIBILE

# ---------- il tappeto sonoro ----------
# Un sottofondo che accompagna tutta l'esperienza, tranne la meditazione: li'
# tace e lascia il campo alla traccia costruita sull'emozione di chi ascolta.
# E' materiale dello stesso motore musicale, preso dal quadrante della calma —
# la destinazione verso cui ogni sessione tende comunque.
EMOZIONE_TAPPETO = "Q4"
DISSOLVENZA_TAPPETO = 4.0    # quanto ci mette a cambiare volume

# All'apertura il tappeto sale INSIEME all'immagine, dallo stesso nero: e' la
# stessa curva della dissolvenza visiva (CURVA_DISSOLVENZA in
# td_face_points.py). Una rampa lineare sotto un'immagine che sale in modo
# curvo si sentirebbe arrivare prima di quel che si vede.
CURVA_APERTURA = 2.2

# Un solo livello per tutta l'opera. Qualunque cosa stia suonando — il tappeto
# o la traccia della meditazione — suona a questo volume: cambia la musica, non
# quanto e' forte.
VOLUME_PIENO = 0.70

VOLUME_APERTURA = VOLUME_PIENO       # saluto e invito
VOLUME_PREPARAZIONE = VOLUME_PIENO   # attesa, frasi personalizzate, danza
VOLUME_FINALE = VOLUME_PIENO         # mandala, dissoluzione, commiato

# Le due sole eccezioni, e sono funzionali, non estetiche:
VOLUME_ASCOLTO = 0.30        # mentre la persona parla il tappeto si fa da
                             # parte, altrimenti Whisper sente lui e non lei
VOLUME_MEDITAZIONE = 0.00    # il TAPPETO tace durante la meditazione, per
                             # lasciare il campo alla traccia generata — che
                             # suona comunque a VOLUME_PIENO

# Quanto resta della musica sotto la campana dello stacco. Non zero: la
# campana nel silenzio assoluto suona come un'interruzione, non come un
# passaggio. Un filo di musica sotto la tiene dentro il pezzo.
VOLUME_SOTTO_CAMPANA = 0.30

# ---------- la voce che legge ----------
# Una guida legge ad alta voce le stesse parole che le particelle disegnano.
# Voce e scritta sono la STESSA cosa detta due volte, non due contenuti: la
# voce entra quando la scritta si e' formata, non mentre si sta formando —
# durante la transizione non c'e' ancora niente da leggere, e sentir dire una
# frase che non si vede ancora la trasformerebbe in un annuncio.
CODA_VOCE = 1.5         # respiro dopo l'ultima parola, prima di cambiare
                        # scritta. Senza, la frase successiva parte addosso
                        # alla precedente e la meditazione diventa un elenco.
                        # Cresciuto da 1.2 quando la voce e' scesa a 0.75: se
                        # le parole rallentano ma le pause restano, il rapporto
                        # fra suono e silenzio si stringe — e il silenzio, qui,
                        # e' meta' del lavoro.
ATTENUAZIONE_VOCE = 0.35    # quanto scende la musica mentre la voce parla
MAX_ATTESA_VOCE = 15.0      # oltre, si va avanti muti invece che aspettare

# ---------- il colore personale ----------
# Il blu delle prime fasi e' il colore di PRIMA che l'opera sappia chi ha
# davanti. La tinta che Claude ricava dal racconto non aspetta il mandala per
# farsi vedere: entra appena esiste, e cresce fase per fase. Cosi' il mandala
# smette di essere l'unico momento colorato e diventa l'arrivo di qualcosa che
# era gia' cominciato — e le sette fasi non sono piu' cinque blu e due colorate.
#
# I tre valori non sono distribuiti a caso lungo la strada: a meta' (0.5) il
# colore passa per il grigio, perche' e' li' che il blu ha finito di scaricarsi
# e la tinta personale non ha ancora cominciato a caricarsi (vedi _miscela in
# td_face_points.py). Una fase che si fermasse li' resterebbe scolorita per un
# minuto, quindi le due soste stanno una PRIMA e una DOPO quel punto, e il
# grigio si attraversa in movimento — dove non lo si nota.
#
# Cosi' la danza e' ancora blu, ma un blu che sta mollando la presa; la
# meditazione e' gia' la tinta di chi medita, tenuta bassa; il mandala e' quella
# tinta piena. Nessuna delle tre e' riconoscibile come "un cambio di colore":
# se ne accorge chi guarda tutta la sessione, ed e' giusto cosi', perche' e'
# un cambiamento che RIGUARDA chi ha parlato.
TINTA_DANZA = 0.18          # il blu appena scaricato. Provato anche a 0.25 e
                            # 0.35: da li' in poi non si legge piu' come blu
                            # che molla la presa ma come immagine scolorita,
                            # e uno scolorimento sembra un guasto
TINTA_MEDITAZIONE = 0.75    # la tinta personale a meta' saturazione
TINTA_MANDALA = 1.0         # la tinta personale piena
# La miscela si sposta lentamente, e sempre a cavallo di un cambio di scena:
# il colore cambia mentre le particelle si stanno gia' muovendo, che e' il
# momento in cui un cambio di tinta si nota di meno.
RAMPA_TINTA = 12.0
RAMPA_TINTA_MANDALA = 6.0    # l'ultima salita e' piu' rapida: dev'essere
                             # finita quando il mandala si compone, altrimenti
                             # lo si vedrebbe cambiare colore da fermo

# ---------- fase 2: meditazione ----------
MIN_MEDITAZIONE = 3.0       # una riapertura fulminea non puo' bastare a finirla
MAX_MEDITAZIONE = 600.0     # rete di sicurezza per una presentazione (10 minuti)

# ---------- fase 3: il mandala ----------
TRANSIZIONE_MANDALA = 6.0    # il mandala si compone piu' lentamente del resto:
                             # e' il regalo finale, non deve sbrigarsi
SECONDI_PER_LIVELLO = 40.0   # ogni tot secondi di meditazione, un livello di dettaglio in piu'
BONUS_MASSIMO = 3            # tetto ai livelli: oltre, il disegno si affolla
                             # e si legge peggio invece che meglio
PERMANENZA_MANDALA = 12.0    # quanto lo si contempla prima di lasciarlo andare (prova; era 40.0)

# ---------- la dissoluzione ----------
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
                 musica=None, tappeto=None, voce=None, sincronia=None,
                 nome=None):
        self.scena = scena
        self.racconto = racconto      # ripiego se il microfono non c'e' o non sente
        self.ascolto = ascolto
        self.sincronia = sincronia    # web: sincronizza riflessione e risultati col browser
        self.saluto = saluto_per(nome)
        self.occhi = modulo_occhi.Rilevatore()
        self.movimento = modulo_movimento.Movimento()
        self._generazione_avviata = False

        self.stato = None
        self.t_stato = 0.0
        self.finita = False

        self._ultimo_stato_occhi = None
        self._occhi_armati = False   # must see eyes open before a close counts
        self._materiale = None
        self._t_pronto = None
        self._scritte_pronte = False
        self._tappeto_avviato = False

        self._indice_blocco = 0
        self._t_blocco = 0.0
        self._durata_blocco = 0.0   # quanto dura la schermata in corso:
                                    # non e' una costante perche' dipende da
                                    # quanto ci mette la voce a dirla
        self._durata_meditazione = 0.0
        self._voce_da_dire = None   # frase gia' a schermo che sta per essere
                                    # detta, e il momento in cui dirla
        self._t_voce = 0.0
        self._voce_generata = threading.Event()

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
        # l'attenuazione e' un MOLTIPLICATORE, quindi il rapporto fra i due
        # livelli: lo stacco non deve sapere a che volume sta la scena
        self.stacco = modulo_stacco.Stacco(
            (self.tappeto, self.musica), modulo_musica.SAMPLE_RATE,
            attenuazione=VOLUME_SOTTO_CAMPANA / VOLUME_PIENO,
        )

        # la voce abbassa le stesse due sorgenti, ma con un moltiplicatore
        # tutto suo: cosi' puo' capitare insieme a uno stacco senza che i due
        # si riportino su la musica a vicenda
        self.voce = voce if voce is not None else modulo_voce.Voce(
            (self.tappeto, self.musica), attenuazione=ATTENUAZIONE_VOCE)

    # ---------- avvio ----------

    def _scritte_sessione(self):
        """Fixed lines for this session, with the personalized greeting first."""
        return (self.saluto + INVITO + ATTESA + ATTESA_MANDALA
                + INVITO_DISSOLUZIONE + [INVITO_RIFLESSIONE] + COMMIATO + CHIUSURA)

    def prepara_scritte(self):
        """Chiede a TD di disegnare in anticipo tutte le scritte fisse.

        Dopo questa chiamata bisogna lasciar passare del tempo prima di
        poterne mostrare una: TD le disegna e le campiona una alla volta, e
        chiedere una scritta non ancora pronta fa ripiegare sul volto."""
        self.scena.prepara(self._scritte_sessione())
        self._scritte_pronte = True

    def prepara_voce(self):
        """Fa sintetizzare le scritte fisse, in sottofondo.

        Da chiamare a sipario chiuso, il prima possibile. Con la cache gia'
        piena — cioe' sempre, dopo il primo giro o dopo prepara_voce.py —
        finisce in un istante perche' non c'e' niente da fare. A cache fredda
        ci mette qualche decina di secondi, e le scritte che non fanno in
        tempo restano semplicemente mute: nessuna si fa aspettare.

        The opening (greeting + eye-close invitation) is prepared first and
        synchronously: those lines set the rhythm of the first minute, and a
        name-specific greeting is rarely already in cache.
        """
        # Speak the closing reflection prompt up front: it is the last guide
        # line before the mic opens, and must not wait on the background queue.
        apertura = list(self.saluto) + list(INVITO) + [INVITO_RIFLESSIONE]
        try:
            self.voce.prepara(apertura, silenzioso=True)
        except Exception as exc:
            print(f"voce: apertura non preparata ({exc})")
        da_dire = self._scritte_sessione() + [
            testi.RISERVA[campo] for campo in testi.CAMPI_TESTO]
        return self.voce.prepara_in_sottofondo(da_dire)

    def prepara_tappeto(self):
        """Carica il tappeto senza farlo partire.

        Il caricamento e' l'operazione piu' lenta di tutto l'avvio (si
        ricampiona e si filtra la traccia): va fatta a sipario chiuso, non nel
        momento in cui la musica deve entrare."""
        self.tappeto.carica(EMOZIONE_TAPPETO, morbido=True)

    def avvia_tappeto(self, fade=DISSOLVENZA_TAPPETO, curva=CURVA_APERTURA):
        """Fa entrare il tappeto. Se non e' stato caricato prima lo carica
        adesso — funziona lo stesso, ma il ciclo si ferma per un secondo."""
        if not self.tappeto.pronta:
            self.prepara_tappeto()
        self.tappeto.parti(fade=fade, volume=VOLUME_APERTURA, curva=curva)
        self._tappeto_avviato = True

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
        self.scena.testo(self.saluto[0], transizione=0.0)

    def avvia(self, ora):
        # se si e' passati da prepara_scritte() non si rifa': ridisegnarle
        # costerebbe un secondo abbondante proprio mentre si parte
        if not self._scritte_pronte:
            self.prepara_scritte()
        self._vai("saluto", ora)
        # Il momento dell'apertura: le particelle sparse si raccolgono nelle
        # prime parole. Piu' lento del resto perche' e' l'inizio, e perche'
        # e' il primo movimento che lo spettatore vede.
        self._mostra_blocco(self.saluto, 0, ora, transizione=TRANSIZIONE_APERTURA)
        # di norma il tappeto e' gia' entrato con la dissolvenza d'apertura;
        # qui si copre il caso in cui avvia() venga chiamata da sola
        if not self._tappeto_avviato:
            self.avvia_tappeto()
        # anche il flusso della traccia si apre ADESSO, muto e senza nulla da
        # suonare: aprirlo piu' tardi, mentre il tappeto suona, farebbe
        # riconfigurare la scheda audio e si sentirebbe un click
        self.musica.apri()
        # stessa ragione per la voce: il suo flusso si apre adesso, muto
        self.voce.apri()
        # e anche il microfono: aprirlo piu' tardi, quando la persona chiude
        # gli occhi, faceva click mentre il tappeto suonava
        if self.ascolto:
            self.ascolto.apri()

    # ---------- il ciclo lo chiama ad ogni fotogramma ----------

    def aggiorna(self, ora, punti=None, blink=None):
        if self.finita:
            return

        stato_occhi = self.occhi.aggiorna(punti, ora, blink=blink)
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

        # la voce entra quando la scritta ha finito di comporsi: qui si
        # guarda solo se e' arrivato il momento, mai si aspetta
        if self._voce_da_dire is not None and ora >= self._t_voce:
            self.voce.di(self._voce_da_dire)
            self._voce_da_dire = None
        self.voce.aggiorna(ora)

        trascorso = ora - self.t_stato

        if self.stato == "saluto":
            if ora - self._t_blocco >= self._durata_blocco:
                if self._indice_blocco + 1 < len(self.saluto):
                    self._mostra_blocco(self.saluto, self._indice_blocco + 1, ora)
                else:
                    self._vai("invito", ora)
                    self._mostra_blocco(INVITO, 0, ora)

        elif self.stato == "invito":
            # Looking down at Restart / the keyboard often reads as "closed".
            # Arm only after open eyes are confirmed in this phase.
            if stato_occhi == "aperti":
                self._occhi_armati = True

            ultimo_blocco = self._indice_blocco >= len(INVITO) - 1
            if not ultimo_blocco and (ora - self._t_blocco) >= self._durata_blocco:
                self._mostra_blocco(INVITO, self._indice_blocco + 1, ora)
                ultimo_blocco = self._indice_blocco >= len(INVITO) - 1

            pronto_occhi = (
                self._occhi_armati and ultimo_blocco and stato_occhi == "chiusi"
            )
            if pronto_occhi or trascorso >= MAX_ATTESA_GESTO:
                self._vai("ascolto", ora)
                # la guida tace PRIMA che il microfono si accenda: quello che
                # suona in stanza finisce nella registrazione, e una frase
                # ancora in bocca verrebbe trascritta come se l'avesse detta
                # la persona
                self.voce.zittisci()
                self._voce_da_dire = None
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
            attesa_finita = (ora - self._t_blocco) >= self._durata_blocco
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
            # anche la voce dev'essere pronta: entrare nella danza mentre le
            # frasi si stanno ancora sintetizzando vorrebbe dire mostrarne una
            # muta e dire la successiva. Ma non si aspetta all'infinito: se la
            # rete e' lenta o assente si prosegue in silenzio.
            voce_pronta = self._voce_generata.is_set() or (
                pronto and (ora - self._t_pronto) >= MAX_ATTESA_VOCE)
            td_pronto = td_pronto and voce_pronta
            # si esce solo quando la scritta in corso e' stata letta per intero
            if pronto and td_pronto and attesa_finita:
                self._costruisci_copione()
                self._vai("danza", ora)
                # il colore comincia ad entrare qui: sono le prime parole che
                # l'opera ha scritto per questa persona, ed e' il primo
                # momento in cui ha senso che non sia piu' del tutto blu
                self.scena.tinta_forza(TINTA_DANZA, RAMPA_TINTA)
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
            # The cue is the last dance line itself, so many people already have
            # their eyes closed when we enter this state. Do NOT require a fresh
            # open→close here (that trapped the gesture and felt "stuck").
            if stato_occhi == "chiusi" or trascorso >= MAX_ATTESA_GESTO:
                self._vai("meditazione", ora)
                self.scena.mostra("volto", transizione=TRANSIZIONE)
                # il colore sale insieme alla musica dell'emozione: sono la
                # stessa cosa detta in due modi, e devono entrare insieme
                self.scena.tinta_forza(TINTA_MEDITAZIONE, RAMPA_TINTA)
                self.tappeto.volume(VOLUME_MEDITAZIONE, fade=6.0)
                self.musica.play(self.emozione, fade=6.0, volume=VOLUME_PIENO)

        elif self.stato == "meditazione":
            pronto_a_finire = trascorso >= MIN_MEDITAZIONE
            if (stato_occhi == "aperti" and pronto_a_finire) or trascorso >= MAX_MEDITAZIONE:
                self._durata_meditazione = trascorso
                self._vai("preparazione_mandala", ora)
                self._mostra_blocco(ATTESA_MANDALA, 0, ora, TRANSIZIONE_BREVE)
                # l'ultimo passo: la scritta d'attesa finisce di colorarsi
                # mentre si legge, cosi' il mandala non arriva come uno stacco
                # di colore ma come il punto d'arrivo di quello che c'era gia'
                self.scena.tinta_forza(TINTA_MANDALA, RAMPA_TINTA_MANDALA)
                self._invia_mandala()
                self.musica.fade_out(6.0)
                self.tappeto.volume(VOLUME_FINALE, fade=6.0)

        elif self.stato == "preparazione_mandala":
            if len(ATTESA_MANDALA) > 1 and (ora - self._t_blocco) >= self._durata_blocco:
                prossimo = (self._indice_blocco + 1) % len(ATTESA_MANDALA)
                self._mostra_blocco(ATTESA_MANDALA, prossimo, ora, TRANSIZIONE_BREVE)
            # il mandala e' puro calcolo, pronto quasi subito: qui non si
            # aspetta perche' serva, ma perche' la scritta va letta
            if trascorso >= self._durata_blocco:
                self._vai("mandala", ora)
                self.scena.mostra("mandala", transizione=TRANSIZIONE_MANDALA)

        elif self.stato == "mandala":
            # lo si contempla, poi lo si lascia andare: e' il rito che vuole
            # cosi', l'attaccamento anche a cio' che e' bello produce sofferenza
            if trascorso >= PERMANENZA_MANDALA:
                self._vai("invito_dissoluzione", ora)
                self._mostra_blocco(INVITO_DISSOLUZIONE, 0, ora)

        elif self.stato == "invito_dissoluzione":
            if trascorso >= self._durata_blocco:
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
                    # Speak the reflection prompt first; opening the mic in the
                    # same frame used to cancel the scheduled TTS clip.
                    self._vai("riflessione_invito", ora)
                    self._mostra_blocco([INVITO_RIFLESSIONE], 0, ora,
                                        transizione=TRANSIZIONE)
                    ui_apri = getattr(self.scena, "ui_riflessione_apri", None)
                    if ui_apri:
                        ui_apri()
                else:
                    self._vai("commiato", ora)
                    self._mostra_blocco(COMMIATO, 0, ora,
                                        transizione=TRANSIZIONE_LUNGA,
                                        permanenza=PERMANENZA_COMMIATO)

        elif self.stato == "riflessione_invito":
            # Wait until the prompt has been shown/spoken, then open the mic.
            # Do not zittisci here: cutting the clip early made guide + mic overlap
            # when the browser was still finishing playback.
            if ora - self._t_blocco >= self._durata_blocco:
                self._voce_da_dire = None
                self._vai("riflessione_ascolto", ora)
                if self.ascolto:
                    self.ascolto.apri()
                    self.ascolto.inizia()

        elif self.stato == "riflessione_ascolto":
            # Sul web: Fine (o timeout) imposta riflessione_inviata.
            finito = (
                self.sincronia
                and self.sincronia.riflessione_inviata.is_set()
            ) or trascorso >= MAX_ATTESA_GESTO
            if finito:
                if self.ascolto:
                    self.ascolto.ferma()
                self._vai("riflessione", ora)

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
                # Farewell clips are rarely needed mid-session: make sure they
                # exist before showing, otherwise the closing lines stay mute.
                try:
                    self.voce.prepara(COMMIATO, silenzioso=True)
                except Exception as exc:
                    print(f"voce: commiato non preparato ({exc})")
                self._vai("commiato", ora)
                self._mostra_blocco(COMMIATO, 0, ora,
                                    transizione=TRANSIZIONE_LUNGA,
                                    permanenza=PERMANENZA_COMMIATO)

        elif self.stato == "commiato":
            if ora - self._t_blocco >= self._durata_blocco:
                if self._indice_blocco + 1 < len(COMMIATO):
                    self._mostra_blocco(COMMIATO, self._indice_blocco + 1, ora,
                                        permanenza=PERMANENZA_COMMIATO)
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
        try:
            self.voce.stop()
        except Exception:
            pass
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
        # Phases that wait for a deliberate eye-close after looking at the UI
        # (first story invite) need a fresh open→close. Meditation invite does
        # not: the cue is on the previous screen and eyes are often already shut.
        if stato == "invito":
            self._occhi_armati = False

    def imposta_racconto(self, racconto: str):
        """Update the story text before Claude runs (web mid-session path)."""
        self.racconto = racconto or self.racconto

    def _mostra_blocco(self, blocchi, indice, ora, transizione=TRANSIZIONE,
                       permanenza=LEGGIBILE):
        """Mostra un blocco di testo di una sequenza (SALUTO/INVITO/ATTESA) e
        ricorda quando e' iniziato, per sapere quando passare al successivo.

        Qui si decide anche QUANTO dura la schermata, e non e' piu' una
        costante: se la voce la legge, la scritta resta finche' la voce non ha
        finito. Una scritta che sparisce a meta' di una frase detta rompe
        l'illusione che voce e particelle siano la stessa cosa."""
        testo = blocchi[indice]
        self._indice_blocco = indice
        self._t_blocco = ora
        self.scena.mostra("testo", testo, transizione=transizione)
        self._durata_blocco = transizione + self._permanenza(testo, permanenza)
        self._programma_voce(testo, ora + transizione)

    def _permanenza(self, testo, base):
        """Quanto la scritta resta a schermo DOPO essersi formata.

        Almeno il tempo di leggerla; di piu' se la voce ci mette di piu' a
        dirla. Se la clip non c'e' (niente chiave, niente rete, cache fredda)
        durata() vale zero e si ricade esattamente sui tempi di prima."""
        detta = self.voce.durata(testo)
        return max(base, detta + CODA_VOCE) if detta else base

    def _programma_voce(self, testo, quando):
        """Segna che questa frase va detta a quell'ora. Ci pensa aggiorna().

        Programmata invece che detta subito perche' deve entrare a scritta
        formata: e' il momento in cui c'e' qualcosa da leggere."""
        self._voce_da_dire = testo
        self._t_voce = quando

    def _avvia_generazione(self, racconto):
        """La chiamata a Claude vive in un thread suo: cosi' i blocchi
        d'attesa continuano a scorrere e la webcam a girare mentre si aspetta."""
        self._generazione_avviata = True

        def lavoro():
            materiale = testi.genera(racconto)
            # prima si consegna il materiale — TD puo' gia' cominciare a
            # disegnare le scritte — e solo dopo si sintetizza la voce, che e'
            # la parte lenta. Le due attese si sovrappongono invece di sommarsi.
            self._materiale = materiale
            try:
                self.voce.prepara([materiale["frase_1"], materiale["frase_2"],
                                   materiale["concetto"]] + CHIUSURA)
            finally:
                self._voce_generata.set()

        print("esperienza: genero le frasi...")
        threading.Thread(target=lavoro, daemon=True).start()

    def _prepara_scritte_generate(self):
        m = self._materiale
        self.emozione = m.get("emozione", "Q2") 
        # la tinta personale si consegna a TD SUBITO, non col mandala: da qui
        # in poi esiste un colore di questa persona, e le fasi che seguono
        # possono cominciare a miscelarlo al blu
        self.scena.tinta(m["mandala_tonalita"], self.emozione)
        print(f"  frase 1:  {m['frase_1']}")
        print(f"  frase 2:  {m['frase_2']}")
        print(f"  concetto: {m['concetto']}")
        if m["segnale_disagio"]:
            print("  (segnalata una possibile sofferenza seria)")
        self.scena.prepara([m["frase_1"], m["frase_2"], m["concetto"]])

    def _costruisci_copione(self):
        m = self._materiale
        permanenza_concetto = PERMANENZA_CONCETTO
        if self.emozione in QUADRANTI_IN_DISCESA:
            permanenza_concetto += RESPIRO_EXTRA_DISCESA
        self.copione = [
            ("volto", "", TRANSIZIONE, PERMANENZA_VOLTO),
            ("testo", m["frase_1"], TRANSIZIONE,
             self._permanenza(m["frase_1"], PERMANENZA_FRASE)),
            ("volto", "", TRANSIZIONE, PERMANENZA_VOLTO),
            ("testo", m["frase_2"], TRANSIZIONE,
             self._permanenza(m["frase_2"], PERMANENZA_FRASE)),
            ("testo", m["concetto"], TRANSIZIONE,
             self._permanenza(m["concetto"], permanenza_concetto)),
        ]
        for scritta in CHIUSURA:
            self.copione.append(("testo", scritta, TRANSIZIONE,
                                 self._permanenza(scritta, PERMANENZA_CHIUSURA)))
        self.indice = 0

    def _mostra_scena_corrente(self):
        tipo, contenuto, transizione, _ = self.copione[self.indice]
        self.scena.mostra(tipo, contenuto, transizione)
        if tipo == "testo":
            self._programma_voce(contenuto, self.t_stato + transizione)

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
        # l'emozione viaggia con gli altri parametri: e' lei a decidere quanto
        # il colore si apre in gradiente, di qua e nell'immagine salvata
        self.scena.prepara_mandala(petali, anelli, m["mandala_tonalita"], seed,
                                   self.emozione)

        # Lo stesso mandala, ad alta risoluzione, come file da portare via.
        # Gira in un thread: disegnare 260.000 particelle richiede un paio di
        # secondi e il ciclo principale non deve fermarsi per questo.
        self._salva_immagine(petali, anelli, m["mandala_tonalita"], seed,
                             self.emozione)

    def _salva_immagine(self, petali, anelli, tonalita, seed, emozione):
        def lavoro():
            percorso = modulo_mandala.salva(petali, anelli, tonalita, seed,
                                            emozione=emozione)
            if percorso:
                print(f"  il tuo mandala e' salvato in: {percorso}")

        threading.Thread(target=lavoro, daemon=True).start()
