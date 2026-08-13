"""
IN-Motion — punto di avvio unico.

Un solo comando avvia tutto, Ctrl+C ferma tutto in modo pulito.

    python3 main.py "sono stressato per la tesi e non dormo da giorni"

Prima serve:
  - TouchDesigner aperto con visual_TD.toe, e lasciato in PRIMO PIANO:
    quando non e' la finestra attiva il suo orologio rallenta e le
    transizioni restano immobili
  - ANTHROPIC_API_KEY impostata (senza, si usano le frasi di riserva)

La webcam lavora senza mostrare nulla: la finestra di anteprima esisteva solo
per controllare cosa vedeva, e rubava il primo piano a TouchDesigner. Per
riaccenderla in fase di debug, ANTEPRIMA_WEBCAM qui sotto.
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

SECONDI_PER_PASSARE_A_TD = 3

# True solo per capire cosa inquadra la telecamera: apre una finestra che
# durante una sessione vera darebbe fastidio a TouchDesigner.
ANTEPRIMA_WEBCAM = False

RACCONTO_PREDEFINITO = "oggi mi sento agitato e non riesco a fermare i pensieri"


def conto_alla_rovescia(secondi):
    for restanti in range(secondi, 0, -1):
        print(f"passa a TouchDesigner e lascialo davanti... {restanti} ", end="\r")
        time.sleep(1)
    print(" " * 60, end="\r")


def main():
    racconto = " ".join(sys.argv[1:]) or RACCONTO_PREDEFINITO
    print(f'racconto: "{racconto}"\n')

    scena = Scena()
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

    conto_alla_rovescia(SECONDI_PER_PASSARE_A_TD)

    try:
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
        volto.chiudi()
        print("fermato.")


if __name__ == "__main__":
    main()
