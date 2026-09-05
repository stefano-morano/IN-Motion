"""
Sintetizza in anticipo tutte le scritte fisse, e le lascia su disco.

    python3 prepara_voce.py

Da lanciare UNA VOLTA dopo aver scelto la voce (python3 voci.py), e di nuovo
solo se si cambia voce o si riscrive qualche scritta. Da quel momento
l'esperienza parla senza toccare la rete: legge dei file.

Perche' non farlo al volo durante la sessione:

  - COSTA. Il piano gratuito di ElevenLabs da' circa 10.000 crediti al mese,
    e un credito e' un carattere. Sintetizzare le scritte fisse ad ogni
    sessione — sono sempre le stesse — brucerebbe la quota in una giornata di
    prove, e a quel punto tacerebbero anche le frasi personali, che sono le
    uniche che DEVONO essere generate ogni volta.
  - SI SENTE. Una chiamata di rete costa uno o due secondi. In mezzo
    all'esperienza sarebbe un buco, e l'esperienza non ha buchi.
  - PUO' NON ESSERCI. In mostra la rete e' quella che e'. Con la cache piena
    l'unica cosa che dipende da internet sono le tre frasi personali, che
    hanno gia' il loro ripiego.

Prepara TUTTE le varianti di saluto, invito, chiusura e commiato, non solo
quelle sorteggiate per questa esecuzione: al lancio successivo il sorteggio
dara' un altro risultato, e deve trovare la sua voce gia' pronta.
"""

import os
import sys

import esperienza
import voce as modulo_voce


def tutte_le_scritte():
    """Ogni scritta fissa che una sessione potrebbe mostrare, varianti
    comprese. Se domani se ne aggiunge una in esperienza.py, finisce qui
    dentro da sola."""
    scritte = []
    for varianti in (esperienza.SALUTO_VARIANTI, esperienza.INVITO_VARIANTI,
                     esperienza.CHIUSURA_VARIANTI, esperienza.COMMIATO_VARIANTI):
        for blocchi in varianti:
            scritte.extend(blocchi)
    scritte.extend(esperienza.ATTESA)
    scritte.extend(esperienza.ATTESA_MANDALA)
    scritte.extend(esperienza.INVITO_DISSOLUZIONE)
    # e le frasi di riserva: entrano solo se Claude non risponde, ma allora la
    # rete non c'e' — e sintetizzarle in quel momento sarebbe impossibile
    import testi
    scritte.extend(testi.RISERVA[campo] for campo in testi.CAMPI_TESTO)
    # senza doppioni, ma nell'ordine in cui si sentiranno
    viste, ordinate = set(), []
    for s in scritte:
        if s not in viste:
            viste.add(s)
            ordinate.append(s)
    return ordinate


def main():
    scritte = tutte_le_scritte()
    guida = modulo_voce.Voce()

    if not guida.disponibile:
        print("\nLa voce non e' configurata, quindi non c'e' niente da preparare.")
        print("L'esperienza funzionera' lo stesso, muta.\n")
        return 1

    da_fare = [s for s in scritte if not guida.pronta(s)]
    caratteri = sum(len(s) for s in da_fare)
    print(f"\n{len(scritte)} scritte fisse, {len(da_fare)} da sintetizzare "
          f"(~{caratteri} crediti).\n")
    if not da_fare:
        print("Sono gia' tutte in cache: non c'e' niente da fare.\n")
        return 0

    fatte = guida.prepara(da_fare)
    mancanti = [s for s in scritte if not guida.pronta(s)]

    print(f"\n{fatte} sintetizzate in {modulo_voce.CACHE}")
    if mancanti:
        print(f"{len(mancanti)} non sono riuscite:")
        for s in mancanti:
            print(f"  - {s}")
        print("Quelle resteranno mute. Rilancia questo script per riprovare.\n")
        return 1
    print("Tutte pronte. L'esperienza ora parla anche senza rete.\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
