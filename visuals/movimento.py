"""
Il movimento: dai punti del viso ricava quanta energia c'e' nel gesto.

Serve a una cosa sola: sapere quando l'utente ha scosso abbastanza da
essersi liberato del mandala. Le particelle le disperde TouchDesigner, che
il naso ce l'ha gia' dentro i 478 punti; qui si tiene solo il conto.

Le coordinate vengono portate nello stesso spazio di TouchDesigner, cosi'
la soglia e le velocita' significano la stessa cosa da tutte e due le parti.
"""

import math

NASO = 4               # punta del naso: il punto piu' sporgente dei 478
ASPETTO = 16.0 / 9.0   # le stesse costanti con cui TD porta i punti in scena
SCALA = 2.0

# Sotto questa velocita' e' respiro, o imprecisione del tracciamento, non
# volonta' di liberarsi di qualcosa. Deve restare uguale a quella dentro TD.
SOGLIA = 0.20

# Quanta energia serve per considerare concluso il gesto. Misurata sulla
# dissoluzione vera: una scossa decisa ci arriva in una decina di secondi,
# una timida ce ne mette il doppio — ed e' giusto cosi', il gesto va fatto.
ENERGIA_NECESSARIA = 14.0


class Movimento:
    """Accumula quanto si e' mosso il naso, ignorando i movimenti minimi."""

    def __init__(self, soglia=SOGLIA):
        self.soglia = soglia
        self.energia = 0.0
        self._precedente = None
        self._istante = None

    def azzera(self):
        self.energia = 0.0
        self._precedente = None
        self._istante = None

    def aggiorna(self, punti, ora):
        """Da chiamare ad ogni fotogramma. Restituisce l'energia accumulata."""
        if punti is None:
            return self.energia

        p = punti[NASO]
        posizione = (
            (0.5 - p.x) * ASPETTO * SCALA,
            (0.5 - p.y) * SCALA,
            -p.z * SCALA,
        )

        if self._precedente is not None and self._istante is not None:
            dt = ora - self._istante
            # il salto va limitato: al primo giro, o dopo un rallentamento,
            # un intervallo enorme falserebbe la velocita'
            if 1e-4 < dt < 0.2:
                spostamento = math.dist(posizione, self._precedente)
                velocita = max(0.0, spostamento / dt - self.soglia)
                self.energia += velocita * dt

        self._precedente = posizione
        self._istante = ora
        return self.energia

    def abbastanza(self, necessaria=ENERGIA_NECESSARIA):
        return self.energia >= necessaria
