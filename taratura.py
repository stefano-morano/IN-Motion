"""
Taratura degli occhi: misura quanto sono aperti i TUOI occhi, con la TUA luce,
e propone la soglia che separa "aperti" da "chiusi".

Non fa parte dell'esperienza: e' un attrezzo, si usa una volta e poi si copia
il numero dentro occhi.py.

    python3 taratura.py

Un suono segnala ogni cambio di fase, cosi' sai cosa fare anche a occhi chiusi.
"""

import time

import occhi
from volto import Volto

SECONDI_ISTRUZIONI = 4
SECONDI_MISURA = 8
SECONDI_PER_CHIUDERE = 3


def suono():
    print("\a", end="", flush=True)


def barra(valore, massimo=0.45, larghezza=36):
    pieni = max(0, min(larghezza, int(valore / massimo * larghezza)))
    return "█" * pieni + "·" * (larghezza - pieni)


def misura(volto, etichetta, secondi):
    """Raccoglie le aperture per un po', mostrandole dal vivo."""
    valori = []
    inizio = time.time()
    while time.time() - inizio < secondi:
        punti = volto.aggiorna()
        if volto.uscita_richiesta():
            return None
        if punti is None:
            continue
        valore = occhi.apertura(punti)
        valori.append(valore)
        restanti = secondi - (time.time() - inizio)
        print(f"  {etichetta}  {valore:5.3f}  {barra(valore)}  {restanti:3.0f}s", end="\r")
    print(" " * 78, end="\r")
    return valori


def riassunto(nome, valori):
    media = sum(valori) / len(valori)
    print(f"  {nome:8}  media {media:.3f}   minimo {min(valori):.3f}   massimo {max(valori):.3f}")
    return media


def main():
    print("\nTARATURA DEGLI OCCHI")
    print("Guarda la webcam da dove ti metterai davvero durante la meditazione.\n")
    print("Due fasi, un suono segnala il passaggio:")
    print("  1. occhi APERTI, normalmente")
    print("  2. occhi CHIUSI\n")

    volto = Volto(anteprima=True)
    try:
        for restanti in range(SECONDI_ISTRUZIONI, 0, -1):
            volto.aggiorna()
            print(f"si comincia tra {restanti}... ", end="\r")
            time.sleep(1)
        print(" " * 40, end="\r")

        suono()
        print("\nFASE 1 — tieni gli occhi APERTI")
        aperti = misura(volto, "aperti", SECONDI_MISURA)
        if aperti is None:
            return

        suono()
        print(f"\nFASE 2 — CHIUDI GLI OCCHI ora (hai {SECONDI_PER_CHIUDERE} secondi)")
        print("         li riapri quando senti il secondo suono")
        inizio = time.time()
        while time.time() - inizio < SECONDI_PER_CHIUDERE:
            volto.aggiorna()
        chiusi = misura(volto, "chiusi", SECONDI_MISURA)
        suono()
        if chiusi is None:
            return

        if not aperti or not chiusi:
            print("\nNon ho visto il volto abbastanza a lungo. Riprova con piu' luce.")
            return

        print("\nRISULTATI")
        media_aperti = riassunto("aperti", aperti)
        media_chiusi = riassunto("chiusi", chiusi)

        distanza = media_aperti - media_chiusi
        soglia = (media_aperti + media_chiusi) / 2

        print()
        if distanza < 0.05:
            print("  ATTENZIONE: le due fasi si assomigliano troppo.")
            print("  Il rilevamento sarebbe inaffidabile — riprova con piu' luce,")
            print("  o piu' vicino alla webcam.")
        else:
            print(f"  Separazione fra le due fasi: {distanza:.3f}  (buona)")
            print(f"\n  SOGLIA CONSIGLIATA: {soglia:.3f}")
            print("  Copiala in occhi.py, alla riga  SOGLIA = ...")
    finally:
        volto.chiudi()


if __name__ == "__main__":
    main()
