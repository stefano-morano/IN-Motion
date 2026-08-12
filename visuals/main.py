"""
IN-Motion — punto di avvio unico.

Un solo comando avvia tutto, Ctrl+C (o 'q' sulla finestra della webcam)
ferma tutto in modo pulito.

    python3 main.py "sono stressato per la tesi e non dormo da giorni"

Prima serve:
  - TouchDesigner aperto con visual_TD.toe, e lasciato in PRIMO PIANO:
    quando non e' la finestra attiva il suo orologio rallenta e le
    transizioni restano immobili
  - ANTHROPIC_API_KEY impostata (senza, si usano le frasi di riserva)
"""

import sys
import time

from esperienza import Esperienza
from scena import Scena
from volto import Volto

SECONDI_PER_PASSARE_A_TD = 5

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
    volto = Volto()
    esperienza = Esperienza(scena, racconto)

    conto_alla_rovescia(SECONDI_PER_PASSARE_A_TD)

    try:
        esperienza.avvia(time.time())
        while not esperienza.finita:
            punti = volto.aggiorna()
            esperienza.aggiorna(time.time(), punti)
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
