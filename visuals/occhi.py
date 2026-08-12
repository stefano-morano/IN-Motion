"""
Gli occhi: dai punti del viso ricava quanto sono aperti, e da li' decide se
l'utente li ha chiusi di proposito.

Non serve nessuna libreria in piu': le palpebre sono gia' dentro i 478 punti
che MediaPipe manda ad ogni fotogramma.

COME SI MISURA: si confronta l'altezza dell'occhio con la sua larghezza. Un
occhio aperto e' alto circa un quarto della sua larghezza; chiuso, quasi zero.
Usare il rapporto invece dell'altezza pura serve a non farsi ingannare dalla
distanza: se ti avvicini alla webcam l'occhio diventa piu' grande in tutte le
direzioni, ma il rapporto resta lo stesso.
"""

import math

# Le coordinate di MediaPipe sono normalizzate: la x sulla larghezza
# dell'immagine, la y sull'altezza. Su una webcam 16:9 questo significa che
# un passo in x e uno in y NON sono la stessa distanza reale — senza questa
# correzione il rapporto risulterebbe sistematicamente sbagliato.
ASPETTO = 16.0 / 9.0

# Sei punti per occhio: due angoli (larghezza) e due coppie sopra/sotto (altezza).
OCCHIO_DESTRO = (33, 160, 158, 133, 153, 144)
OCCHIO_SINISTRO = (362, 385, 387, 263, 373, 380)


def _distanza(a, b):
    return math.hypot((a.x - b.x) * ASPETTO, a.y - b.y)


def _apertura_occhio(punti, indici):
    angolo_1, alto_1, alto_2, angolo_2, basso_2, basso_1 = (punti[i] for i in indici)
    larghezza = _distanza(angolo_1, angolo_2)
    if larghezza < 1e-6:
        return 0.0
    altezza = _distanza(alto_1, basso_1) + _distanza(alto_2, basso_2)
    return altezza / (2.0 * larghezza)


def apertura(punti):
    """Quanto sono aperti gli occhi, come media dei due.
    Indicativamente: ~0.30 spalancati, ~0.05 chiusi."""
    return (
        _apertura_occhio(punti, OCCHIO_DESTRO)
        + _apertura_occhio(punti, OCCHIO_SINISTRO)
    ) / 2.0


# Misurato con taratura.py (12/08/2026): occhi aperti in media 0.298, chiusi
# 0.064, con i valori "chiusi" che non superano mai 0.086. La soglia sta in
# mezzo, quindi con largo margine da entrambi i lati.
# Se cambiano webcam, luce o distanza, rilanciare taratura.py.
SOGLIA = 0.18
CONFERMA_CHIUSURA = 2.0   # un battito di ciglia dura ~0.3s: non deve contare
CONFERMA_APERTURA = 0.4   # riaprire e' un gesto piu' netto, basta meno


class Rilevatore:
    """Trasforma la misura istantanea in uno stato stabile: 'aperti' o 'chiusi'.

    Un cambiamento viene accettato solo se dura abbastanza. Senza questa
    conferma il sistema partirebbe a registrare ad ogni battito di ciglia."""

    def __init__(
        self,
        soglia=SOGLIA,
        conferma_chiusura=CONFERMA_CHIUSURA,
        conferma_apertura=CONFERMA_APERTURA,
    ):
        self.soglia = soglia
        self.conferma_chiusura = conferma_chiusura
        self.conferma_apertura = conferma_apertura
        self.stato = "aperti"
        self._candidato = None
        self._candidato_da = None

    def aggiorna(self, punti, ora):
        """Da chiamare ad ogni fotogramma. Restituisce lo stato confermato."""
        if punti is None:
            return self.stato

        istantaneo = "chiusi" if apertura(punti) < self.soglia else "aperti"

        if istantaneo == self.stato:
            self._candidato = None
            return self.stato

        if self._candidato != istantaneo:
            self._candidato = istantaneo
            self._candidato_da = ora

        attesa = (
            self.conferma_chiusura if istantaneo == "chiusi" else self.conferma_apertura
        )
        if ora - self._candidato_da >= attesa:
            self.stato = istantaneo
            self._candidato = None

        return self.stato
