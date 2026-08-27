"""
IN-Motion — punto di avvio unico.

Un solo comando avvia tutto, Ctrl+C ferma tutto in modo pulito.

    python3 main.py "sono stressato per la tesi e non dormo da giorni"

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

L'AVVIO E' LENTO DI PROPOSITO. Fra un lancio e l'altro TouchDesigner resta
acceso e congelato sull'ultima immagine di chi c'e' stato prima, e si
scongela solo quando ricomincia a ricevere punti dalla webcam. Per questo la
finestra non si apre subito: prima si aspetta di aver visto un volto, poi si
lascia alle particelle il tempo di tornarci sopra. Chi guarda trova la scena
gia' pulita, e non assiste alla pulizia.
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

# Quanto aspettiamo di vedere un volto prima di aprire la finestra. Se non
# arriva nessuno si parte lo stesso: l'opera deve reggere anche una stanza
# vuota, o una prova fatta senza mettersi davanti.
MAX_ATTESA_VOLTO = 20.0

# Quanto diamo a TouchDesigner per disegnare e campionare tutte le scritte
# fisse. Chiederne una prima che sia pronta fa ripiegare sul volto.
SECONDI_PER_DISEGNARE = 1.5

# Quanto lasciamo alle particelle per disporsi nella nuvola. Si muovono per
# inerzia, non a scatti: e' il tempo in cui abbandonano la forma della
# sessione precedente e si sparpagliano.
SECONDI_PER_COMPORRE = 2.5

# L'apertura, in tre tempi. Lo schermo si apre nero, l'immagine sale piano,
# la nuvola resta sospesa — e solo dopo si raccoglie nelle prime parole.
SECONDI_DI_BUIO = 0.4        # nero pieno: il primo fotogramma che si vede
DURATA_DISSOLVENZA = 3.0     # quanto ci mette l'immagine ad accendersi
SECONDI_DI_POLVERE = 5.0     # nuvola a piena luce, prima che si raccolga

# False per lavorare dentro l'editor di TouchDesigner (utile mentre si
# modificano i nodi: a schermo intero non si vedrebbe la rete).
FINESTRA_A_SCHERMO_INTERO = True

# True solo per capire cosa inquadra la telecamera: apre una finestra che
# durante una sessione vera darebbe fastidio a TouchDesigner.
ANTEPRIMA_WEBCAM = False

RACCONTO_PREDEFINITO = "oggi mi sento agitato e non riesco a fermare i pensieri"


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
    # Per prima cosa, prima ancora della webcam e del modello di trascrizione:
    # TouchDesigner e' rimasto acceso dalla sessione precedente e sta ancora
    # mostrando la sua ultima schermata. Azzerare adesso, e non fra dieci
    # secondi quando l'esperienza parte davvero, e' la differenza fra vedere
    # il commiato di un altro e trovare la scena pulita.
    scena.azzera()

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

    # ---- il risveglio, prima che chiunque possa vedere qualcosa ----
    # Azzerare la scena da Python non basta a scongelare TouchDesigner: TD
    # ricalcola solo quando gli arrivano dati NUOVI, e un dizionario Python
    # non fa parte delle sue dipendenze. Finche' la webcam non manda punti,
    # resta fermo sull'ultima immagine della sessione prima — che e'
    # esattamente il "GRAZIE, A PRESTO" che si vedeva all'avvio.
    # Quindi: prima la telecamera, poi la finestra. Mai il contrario.
    if not attendi_volto(volto):
        print("non ti ho visto, ma parto lo stesso")

    # A sipario chiuso si monta la scena: TD disegna le scritte e le
    # particelle si sparpagliano. Quando la finestra si apre si vede la
    # nuvola, ferma e sospesa — non il volto dello spettatore, che a quel
    # punto sarebbe il montaggio della scena e non l'opera.
    esperienza.prepara_scritte()
    pompa(volto, SECONDI_PER_DISEGNARE)
    esperienza.mostra_polvere()
    pompa(volto, SECONDI_PER_COMPORRE)

    # L'immagine si spegne PRIMA che la finestra si apra: cosi' il primo
    # fotogramma che lo spettatore vede e' nero, non la scena gia' accesa.
    scena.buio()
    if FINESTRA_A_SCHERMO_INTERO:
        scena.finestra(True)
    else:
        print("passa a TouchDesigner e lascialo davanti")
        pompa(volto, SECONDI_PER_LA_FINESTRA)

    pompa(volto, SECONDI_DI_BUIO)
    scena.accendi(DURATA_DISSOLVENZA)
    pompa(volto, DURATA_DISSOLVENZA + SECONDI_DI_POLVERE)

    try:
        # e qui la polvere si raccoglie nelle prime parole. Da adesso corre il
        # tempo dell'esperienza, e parte la musica.
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
        # anche se si interrompe a meta': un flusso audio aperto
        # sopravviverebbe al programma
        esperienza.ferma_suono()   # chiude anche il microfono
        volto.chiudi()
        if FINESTRA_A_SCHERMO_INTERO:
            # anche dopo un Ctrl+C: una finestra a schermo intero rimasta
            # aperta coprirebbe tutto, e senza cursore visibile
            scena.finestra(False)
        print("fermato.")


if __name__ == "__main__":
    main()
