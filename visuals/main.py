"""
IN-Motion — punto di avvio unico.

Un solo comando avvia tutto, Ctrl+C ferma tutto in modo pulito.

    python3 main.py "i am stressed about my thesis and i haven't slept in days"

Prima serve:
  - TouchDesigner aperto con visual_TD.toe (basta che sia aperto: la finestra
    di uscita si apre da sola qui sotto, e portandosi in primo piano tiene
    anche l'orologio di TD alla velocita' giusta)
  - ANTHROPIC_API_KEY impostata (senza, si usano le frasi di riserva)

L'immagine si guarda nella finestra a schermo intero, non nell'editor di
TouchDesigner: e' lo stesso fotogramma che TD sta gia' calcolando, mostrato
senza i pannelli intorno. Si chiude con Esc, oppure da sola a fine sessione.

La webcam lavora senza mostrare nulla: la finestra di anteprima esisteva solo
per controllare cosa vedeva, e rubava il primo piano a TouchDesigner. Per
riaccenderla in fase di debug, ANTEPRIMA_WEBCAM qui sotto.

L'AVVIO E' LENTO DI PROPOSITO, ma la finestra si apre SUBITO — nera. Dietro
quel nero si accende la telecamera, si carica il modello di trascrizione, si
aspetta di vedere un volto e si monta la scena; poi l'immagine sale. Chi
guarda trova la scena gia' pronta, e non assiste ai preparativi.
"""

import sys
import time

# ATTENZIONE ALL'ORDINE: volto.py carica OpenCV, ascolto.py carica Whisper (che
# a sua volta porta con se' una copia diversa delle librerie video). Se Whisper
# arriva per primo, e' la SUA copia a registrarsi nel sistema, e l'elenco delle
# webcam puo' risultare sfalsato. Caricando prima OpenCV la telecamera resta
# quella giusta.
from volto import Volto
from ascolto import Ascolto
from esperienza import Esperienza
from scena import Scena

# quanto lasciamo alla finestra per aprirsi e prendere il primo piano
SECONDI_PER_LA_FINESTRA = 1.5

# Quanto aspettiamo, dietro al nero, di vedere un volto. Se non arriva nessuno
# si parte lo stesso: l'opera deve reggere anche una stanza vuota, o una prova
# fatta senza mettersi davanti all'obiettivo.
MAX_ATTESA_VOLTO = 20.0

# Quanto diamo a TouchDesigner per disegnare e campionare tutte le scritte
# fisse. Chiederne una prima che sia pronta fa ripiegare sul volto.
SECONDI_PER_DISEGNARE = 1.5

# Quanto lasciamo alle particelle per disporsi nella nuvola. Si muovono per
# inerzia, non a scatti: e' il tempo in cui abbandonano la forma della
# sessione precedente e si sparpagliano.
SECONDI_PER_COMPORRE = 2.5

# L'apertura. Lo schermo e' nero da subito e ci resta per tutta la
# preparazione; poi l'immagine sale piano, la nuvola resta sospesa, e solo
# dopo si raccoglie nelle prime parole.
DURATA_DISSOLVENZA = 3.0     # quanto ci mette l'immagine ad accendersi
SECONDI_DI_POLVERE = 5.0     # nuvola a piena luce, prima che si raccolga

# False per lavorare dentro l'editor di TouchDesigner (utile mentre si
# modificano i nodi: a schermo intero non si vedrebbe la rete).
FINESTRA_A_SCHERMO_INTERO = True

# True solo per capire cosa inquadra la telecamera: apre una finestra che
# durante una sessione vera darebbe fastidio a TouchDesigner.
ANTEPRIMA_WEBCAM = False

RACCONTO_PREDEFINITO = "today i feel restless and i can't stop my thoughts"


def pompa(volto, secondi):
    """Tiene viva la webcam per un po', senza fare altro.

    Non e' un'attesa a vuoto: OGNI fotogramma mandato a TouchDesigner e' un
    fotogramma che TouchDesigner calcola. Fermarsi qui con un semplice sleep
    lo lascerebbe congelato esattamente com'era."""
    fine = time.time() + secondi
    while time.time() < fine:
        volto.aggiorna()


def attendi_volto(volto, massimo=MAX_ATTESA_VOLTO):
    """Aspetta che la telecamera veda qualcuno. True se l'ha visto.

    E' la sola prova che la telecamera e' davvero viva e che i punti stanno
    arrivando a TD: un tempo fisso non dimostrerebbe niente. Ma non aspetta
    per sempre — dopo 'massimo' si prosegue comunque."""
    scadenza = time.time() + massimo
    print("aspetto di vederti...", end="\r")
    while time.time() < scadenza:
        if volto.aggiorna() is not None:
            print(" " * 70, end="\r")
            return True
    print(" " * 70, end="\r")
    return False


def main():
    racconto = " ".join(sys.argv[1:]) or RACCONTO_PREDEFINITO
    print(f'racconto: "{racconto}"\n')

    scena = Scena()
    # PRIMA DI OGNI ALTRA COSA. TouchDesigner e' rimasto acceso dalla sessione
    # precedente e mostra ancora la sua ultima schermata: si azzera la scena,
    # si spegne l'immagine, e si apre subito la finestra — nera.
    #
    # Aprirla adesso, e non a preparazione finita, e' la differenza fra un
    # programma che parte e uno che sembra non partire. Quello che viene dopo
    # — telecamera, modello di trascrizione, attesa di un volto davanti
    # all'obiettivo — puo' prendere anche mezzo minuto, e in tutto quel tempo
    # non si vedrebbe accadere niente. Il nero non e' un'attesa a vuoto: e'
    # gia' il sipario, e dietro ci si prepara.
    scena.azzera()
    scena.buio()
    if FINESTRA_A_SCHERMO_INTERO:
        scena.finestra(True)

    volto = None
    esperienza = None
    try:
        volto = Volto(anteprima=ANTEPRIMA_WEBCAM)

        # Il modello di trascrizione si carica adesso, non quando serve: farlo
        # dopo aggiungerebbe secondi di attesa nel momento peggiore.
        # La prima volta in assoluto viene anche scaricato (~150 MB).
        try:
            ascoltatore = Ascolto()
        except Exception as errore:
            print(f"ascolto non disponibile ({errore}) — useremo il racconto scritto")
            ascoltatore = None

        esperienza = Esperienza(scena, racconto, ascoltatore)

        # La voce si mette a sintetizzare adesso, in sottofondo. Con la cache
        # gia' piena (python3 prepara_voce.py) finisce all'istante perche' non
        # c'e' niente da fare; a cache fredda continua dietro al nero, e le
        # scritte che non fanno in tempo restano semplicemente mute. E' la
        # stessa scelta delle frasi di riserva: quello che manca non ferma
        # niente.
        esperienza.prepara_voce()

        # ---- dietro al nero si monta la scena ----
        # Azzerare da Python non basta a scongelare TouchDesigner: TD ricalcola
        # le PARTICELLE solo quando gli arrivano punti nuovi. Quindi prima la
        # telecamera, poi tutto il resto.
        if not attendi_volto(volto):
            print("non ti ho visto, ma parto lo stesso")

        esperienza.prepara_scritte()
        pompa(volto, SECONDI_PER_DISEGNARE)
        esperienza.mostra_polvere()
        # il tappeto si carica adesso: leggere e filtrare la traccia ferma il
        # programma per un secondo e mezzo, e farlo mentre l'immagine sale
        # inchioderebbe la dissolvenza a meta'
        esperienza.prepara_tappeto()
        pompa(volto, SECONDI_PER_COMPORRE)

        if not FINESTRA_A_SCHERMO_INTERO:
            print("passa a TouchDesigner e lascialo davanti")
            pompa(volto, SECONDI_PER_LA_FINESTRA)

        # immagine e musica salgono INSIEME, dallo stesso nero e con la stessa
        # curva: e' un unico gesto di apertura, non due cose che si accavallano
        scena.accendi(DURATA_DISSOLVENZA)
        esperienza.avvia_tappeto(DURATA_DISSOLVENZA)
        pompa(volto, DURATA_DISSOLVENZA + SECONDI_DI_POLVERE)

        # e qui la polvere si raccoglie nelle prime parole. La musica sta gia'
        # suonando: da adesso corre il tempo dell'esperienza.
        esperienza.avvia(time.time())
        while not esperienza.finita:
            punti = volto.aggiorna()
            esperienza.aggiorna(time.time(), punti)
            # ha effetto solo con l'anteprima accesa ('q' sulla finestra)
            if volto.uscita_richiesta():
                print("\ninterrotto dalla finestra webcam")
                break
    except KeyboardInterrupt:
        print("\ninterrotto da tastiera")
    finally:
        # Vale anche se si e' rotto qualcosa a meta' preparazione, ed e' il
        # motivo per cui tutta la preparazione sta dentro questo try: un flusso
        # audio aperto sopravviverebbe al programma, e la finestra — che a quel
        # punto e' gia' aperta e nera — coprirebbe lo schermo senza nemmeno un
        # cursore per uscirne.
        if esperienza is not None:
            esperienza.ferma_suono()   # chiude anche il microfono
        if volto is not None:
            volto.chiudi()
        if FINESTRA_A_SCHERMO_INTERO:
            scena.finestra(False)
        print("fermato.")


if __name__ == "__main__":
    main()
