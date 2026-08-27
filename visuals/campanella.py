"""
La campanella: il piccolo suono che conferma il passaggio di stato.

Ogni volta che il sistema ACCETTA un cambiamento degli occhi — chiusi
confermati, oppure riaperti — suona una campana. Serve a rispondere alla
domanda che chi ha gli occhi chiusi non puo' farsi in nessun altro modo:
"mi ha visto?". A occhi chiusi lo schermo non esiste, e il suono e' l'unico
canale rimasto.

DUE NOTE, NON UNA. Chiudere e riaprire sono movimenti opposti e meritano
suoni diversi, altrimenti il segnale dice "e' successo qualcosa" ma non dice
cosa:
    chiusura  -> nota grave, si scende dentro
    apertura  -> una quinta sopra, si torna fuori
La quinta giusta e' l'intervallo piu' consonante dopo l'ottava: qualunque sia
la tonalita' del tappeto musicale, due note a distanza di quinta non ci
litigano quasi mai.

PERCHE' NON BASTA UN SENO. Una sinusoide che sfuma suona come un fischio,
non come metallo. Tre dettagli fisici fanno la differenza, e sono tutti qui
sotto:

  1. PARZIALI NON ARMONICHE. In una corda le frequenze che risuonano sono
     multipli interi della fondamentale (2x, 3x, 4x). In un corpo di metallo
     ricurvo no: stanno a rapporti irregolari (qui 2.71, 5.18, 8.35). E'
     questa irregolarita' che l'orecchio riconosce come "percosso", e non
     come "suonato".

  2. LE ACUTE SI SPENGONO PRIMA. E' il dettaglio che conta di piu'. In un
     corpo che vibra le frequenze alte perdono energia molto piu' in fretta:
     il suono comincia brillante e diventa scuro mentre svanisce. Se tutte
     le parziali svanissero insieme si sentirebbe un accordo d'organo.

  3. IL BATTIMENTO. Una ciotola non e' mai perfettamente simmetrica, quindi
     ogni modo di vibrazione si sdoppia in due frequenze vicinissime. Le due
     onde vanno a tempo e poi in opposizione, e il volume ondeggia
     lentamente: e' quel respiro che fa sembrare il suono vivo invece che
     stampato.

L'attacco e' smussato su una decina di millisecondi. Un attacco istantaneo
contiene un salto, e un salto e' un click: il difetto contro cui questo
progetto ha gia' combattuto altrove.
"""

import numpy as np

# rapporto rispetto alla fondamentale, quanto pesa, in quanti secondi svanisce.
# I rapporti sono quelli tipici di una ciotola cantante; le acute si spengono
# per prime (punto 2 qui sopra).
PARZIALI = (
    (1.00, 1.00, 3.20),
    (2.71, 0.55, 1.80),
    (5.18, 0.28, 1.00),
    (8.35, 0.12, 0.55),
)

DURATA = 3.6          # secondi di coda: piu' lunga della conferma degli occhi,
                      # cosi' il suono accompagna la transizione invece di
                      # chiuderla
ATTACCO = 0.012       # 12 ms di salita morbida: senza, si sentirebbe un click
BATTIMENTO = 0.9      # Hz di scarto fra le due meta' di ogni parziale
VOLUME = 0.22         # sotto la musica, ma sopra il silenzio della meditazione

GRAVE = 220.0         # LA3  — la chiusura
ACUTA = 330.0         # MI4  — l'apertura, una quinta giusta sopra


def _voce(fondamentale, sr, sfasamento):
    """Un canale della campana. 'sfasamento' sposta di pochissimo la fase del
    battimento: dandone uno diverso a destra e a sinistra, le due ondulazioni
    non coincidono e il suono si apre in larghezza senza nessun effetto
    aggiunto."""
    n = int(sr * DURATA)
    t = np.arange(n, dtype=np.float64) / sr
    onda = np.zeros(n, dtype=np.float64)

    for rapporto, ampiezza, decadimento in PARZIALI:
        f = fondamentale * rapporto
        # le parziali acute battono piu' in fretta, come nel corpo vero
        battito = BATTIMENTO * rapporto
        inviluppo = ampiezza * np.exp(-t / decadimento)
        gemella = 2.0 * np.pi * (f + battito) * t + sfasamento
        onda += inviluppo * 0.5 * (np.sin(2.0 * np.pi * f * t) + np.sin(gemella))

    n_attacco = max(1, int(sr * ATTACCO))
    salita = np.linspace(0.0, 1.0, n_attacco)
    onda[:n_attacco] *= 0.5 - 0.5 * np.cos(np.pi * salita)
    return onda


def campana(fondamentale, sr=44100, volume=VOLUME):
    """Una campana pronta da mixare: stereo, float32, gia' al volume giusto."""
    sinistra = _voce(fondamentale, sr, 0.0)
    destra = _voce(fondamentale, sr, 0.6)
    stereo = np.stack([sinistra, destra], axis=1)
    picco = float(np.abs(stereo).max())
    if picco > 0:
        stereo *= volume / picco
    return stereo.astype(np.float32)


def coppia(sr=44100, volume=VOLUME):
    """Le due campane della sessione: (chiusura, apertura)."""
    return campana(GRAVE, sr, volume), campana(ACUTA, sr, volume)


if __name__ == '__main__':
    # prova rapida: python3 campanella.py
    import sounddevice as sd
    import time

    sr = 44100
    bassa, alta = coppia(sr)
    for nome, suono in (("chiusura (LA3)", bassa), ("apertura (MI4)", alta)):
        print(nome)
        sd.play(suono, sr)
        sd.wait()
        time.sleep(0.4)
