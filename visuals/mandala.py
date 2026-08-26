"""
Il mandala della sessione, come immagine vera da portare via.

A schermo il mandala e' fatto di 13.664 particelle che si muovono; qui ne
disegniamo centinaia di migliaia, ferme, ad alta risoluzione. E' lo stesso
disegno — stessi petali, stessi anelli, stesso colore, stesso seme — ma
pensato per essere stampato o tenuto, non guardato per quaranta secondi.

Non serve TouchDesigner: la geometria e' la stessa manciata di formule, e
disegnarla qui vuol dire che l'immagine si genera anche se TD non e' aperto.

    python3 mandala.py 7 3 186 42      # petali anelli tonalita seme
"""

import colorsys
import os
from datetime import datetime

import numpy as np
from PIL import Image

# ---------- quanto e' grande e quanto e' fitto ----------
DIMENSIONE = 2400          # lato dell'immagine in pixel
PARTICELLE = 260_000       # molte piu' che a schermo: qui non deve animarsi
RIEMPIMENTO = 0.80         # quanta parte dell'immagine occupa il disegno

# ---------- forma (le stesse regole della versione a schermo) ----------
PETALO = 0.26
ARMONICA = 0.10
SPESSORE = 0.035
OCCHIO = 0.18              # il vuoto al centro, in frazione del raggio

# ---------- nebbia ----------
# Come a schermo: una parte delle particelle non sta sulla forma ma le
# aleggia intorno. Senza, il disegno diventa una figura di linee nette e
# perde la natura di polvere che e' il carattere di tutta l'opera.
FRAZIONE_NEBBIA = 0.30
NEBBIA_RAGGIO = 0.035

# ---------- resa ----------
# Il bagliore si ottiene sommando la stessa immagine sfocata a raggi diversi:
# un alone stretto e luminoso piu' aloni larghi e tenui. E' lo stesso principio
# del Bloom di TouchDesigner, fatto a mano perche' qui non c'e' la GPU.
#
# I pesi degli aloni larghi sono BASSI apposta: alzandoli i singoli grani si
# fondono in linee continue e il mandala diventa un disegno al neon invece che
# una nuvola di particelle.
ALONI = ((0.7, 1.00), (2.6, 0.26), (9.0, 0.13), (30.0, 0.08))
ESPOSIZIONE = 3.4          # quanto e' luminoso il risultato
SFONDO_CENTRO = (0.045, 0.060, 0.115)
SFONDO_BORDO = (0.004, 0.006, 0.016)
VIGNETTA = 0.35            # quanto scuriscono i bordi


def _riparti(n, gruppi):
    base, resto = divmod(n, gruppi)
    return [base + (1 if i < resto else 0) for i in range(gruppi)]


def posizioni(petali, anelli, seed, n=PARTICELLE):
    """Le stesse regole della versione a schermo: anelli concentrici, petali
    ottenuti raggruppando le particelle attorno a certi ANGOLI (non spostando
    il raggio), anelli alternati sfasati di mezzo petalo."""
    anelli = max(int(anelli), 1)
    petali = max(int(petali), 2)
    rng = np.random.default_rng(int(seed))

    conteggi = _riparti(n, anelli)
    spaziatura = (1.0 - OCCHIO) / anelli
    sfogo = spaziatura * 0.45

    angoli = np.empty(n)
    raggi = np.empty(n)

    inizio = 0
    for i, conteggio in enumerate(conteggi):
        if conteggio == 0:
            continue
        fetta = slice(inizio, inizio + conteggio)
        inizio += conteggio

        quota = (i + 1) / anelli
        raggio_base = OCCHIO + (1.0 - OCCHIO) * quota

        ampiezza = min(PETALO * raggio_base, sfogo) / raggio_base
        armonica = min(ARMONICA * raggio_base, sfogo * 0.4) / raggio_base

        tipo = i % 3
        if tipo == 0:
            gruppi, dispersione = petali, 0.20
        elif tipo == 1:
            gruppi, dispersione = petali * 2, 0.13
        else:
            gruppi, dispersione = 0, 0.0

        if gruppi:
            passo = 2.0 * np.pi / gruppi
            a = rng.integers(0, gruppi, conteggio) * passo
            a = a + rng.normal(0.0, passo * dispersione, conteggio)
        else:
            a = rng.uniform(0.0, 2.0 * np.pi, conteggio)

        fase = (np.pi / petali) * (i % 2) + rng.uniform(0.0, 0.4)
        modulazione = (1.0
                       + ampiezza * np.cos(petali * a + fase)
                       + armonica * np.cos(2 * petali * a + fase * 2.0))
        spessore = rng.normal(0.0, min(SPESSORE, spaziatura * 0.16), conteggio)

        angoli[fetta] = a
        raggi[fetta] = raggio_base * modulazione + spessore

    picco = float(np.abs(raggi).max())
    if picco > 1e-9:
        raggi /= picco          # normalizzato a 1, poi scalato all'immagine

    # la nebbia: alcune particelle si staccano dalla forma e le aleggiano
    # intorno, come a schermo
    quante = int(n * FRAZIONE_NEBBIA)
    if quante:
        scelte = rng.choice(n, size=quante, replace=False)
        raggi[scelte] += rng.normal(0.0, NEBBIA_RAGGIO, quante)
        angoli[scelte] += rng.normal(0.0, NEBBIA_RAGGIO * 1.6, quante)
    return angoli, raggi


def _densita(angoli, raggi, lato):
    """Conta quante particelle cadono in ogni pixel. Sommare i conteggi e poi
    sfocare costa infinitamente meno che disegnare 260.000 alonicini uno per
    uno, e il risultato e' lo stesso."""
    centro = lato / 2.0
    scala = centro * RIEMPIMENTO
    x = np.clip((centro + raggi * np.cos(angoli) * scala).astype(np.int32), 0, lato - 1)
    y = np.clip((centro + raggi * np.sin(angoli) * scala).astype(np.int32), 0, lato - 1)

    mappa = np.zeros((lato, lato), dtype=np.float32)
    np.add.at(mappa, (y, x), 1.0)
    return mappa


def _media_mobile(m, raggio, asse):
    """Media su una finestra, calcolata con una somma cumulativa: costa lo
    stesso qualunque sia l'ampiezza della finestra, invece di crescere con
    essa. E' quello che rende praticabile un alone largo 34 pixel."""
    if raggio < 1:
        return m
    riempimento = [(0, 0), (0, 0)]
    riempimento[asse] = (raggio + 1, raggio)
    p = np.cumsum(np.pad(m, riempimento, mode='constant'), axis=asse)
    larghezza = 2 * raggio + 1
    if asse == 0:
        return (p[larghezza:, :] - p[:-larghezza, :]) / larghezza
    return (p[:, larghezza:] - p[:, :-larghezza]) / larghezza


def _sfoca(m, sigma):
    """Sfocatura gaussiana approssimata. Tre passate di media mobile bastano:
    la differenza da una gaussiana vera e' invisibile in un alone, e non
    servono librerie in piu' (PIL non sfoca immagini in virgola mobile)."""
    raggio = max(1, int(round(sigma * 0.9)))
    for _ in range(3):
        m = _media_mobile(m, raggio, 0)
        m = _media_mobile(m, raggio, 1)
    return m


def _bagliore(mappa):
    """Somma la stessa mappa sfocata a raggi diversi: alone stretto e intenso
    piu' aloni larghi e tenui. E' quello che trasforma dei punti in luce."""
    fuori = np.zeros_like(mappa)
    for sigma, peso in ALONI:
        fuori += _sfoca(mappa, sigma) * peso
    return fuori


def _colora(luce, tonalita, lato):
    """Dalla quantita' di luce al colore: le zone deboli prendono la tinta
    profonda, quelle intense la tinta chiara. Due toni della stessa tonalita'
    invece di uno solo schiarito — altrimenti il risultato sembra finto."""
    h = (float(tonalita) % 360.0) / 360.0
    fondo = np.array(colorsys.hsv_to_rgb(h, 0.80, 0.32), dtype=np.float32)
    chiaro = np.array(colorsys.hsv_to_rgb((h - 0.045) % 1.0, 0.34, 1.0), dtype=np.float32)

    # la luce cresce senza limite dove le particelle si ammassano: la curva la
    # comprime, cosi' i grumi restano leggibili invece di diventare macchie
    t = 1.0 - np.exp(-luce * ESPOSIZIONE)
    t = t[..., None]

    disegno = fondo + (chiaro - fondo) * t
    disegno = disegno * t          # dove non c'e' luce non c'e' colore

    # sfondo: alone profondo, piu' chiaro al centro
    coord = (np.arange(lato, dtype=np.float32) - lato / 2.0) / (lato / 2.0)
    xx, yy = np.meshgrid(coord, coord)
    distanza = np.clip(np.sqrt(xx * xx + yy * yy), 0.0, 1.0)[..., None]
    centro = np.array(SFONDO_CENTRO, dtype=np.float32)
    bordo = np.array(SFONDO_BORDO, dtype=np.float32)
    sfondo = centro + (bordo - centro) * distanza

    immagine = sfondo + disegno
    immagine *= 1.0 - VIGNETTA * distanza ** 2      # bordi piu' scuri
    return np.clip(immagine, 0.0, 1.0)


def genera(petali, anelli, tonalita, seed, lato=DIMENSIONE):
    """L'immagine del mandala, pronta da salvare."""
    angoli, raggi = posizioni(petali, anelli, seed)
    mappa = _densita(angoli, raggi, lato)
    luce = _bagliore(mappa)
    finale = _colora(luce, tonalita, lato)
    return Image.fromarray((finale * 255).astype(np.uint8), mode='RGB')


def salva(petali, anelli, tonalita, seed, cartella=None):
    """Salva il mandala e restituisce il percorso. Non solleva mai eccezioni:
    se il salvataggio fallisce l'esperienza non deve fermarsi per questo."""
    try:
        if cartella is None:
            cartella = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'mandala')
        os.makedirs(cartella, exist_ok=True)
        # secondi e seme nel nome: due sessioni nello stesso minuto non devono
        # sovrascriversi a vicenda, e dal nome si risale ai parametri esatti
        nome = datetime.now().strftime('mandala_%Y-%m-%d_%H-%M-%S') + f'_{int(seed)}.png'
        percorso = os.path.join(cartella, nome)
        genera(petali, anelli, tonalita, seed).save(percorso)
        return percorso
    except Exception as errore:
        print(f"[mandala] non sono riuscito a salvare l'immagine ({errore})")
        return None


if __name__ == '__main__':
    import sys

    argomenti = sys.argv[1:]
    petali = int(argomenti[0]) if len(argomenti) > 0 else 7
    anelli = int(argomenti[1]) if len(argomenti) > 1 else 3
    tonalita = float(argomenti[2]) if len(argomenti) > 2 else 186.0
    seed = int(argomenti[3]) if len(argomenti) > 3 else 42

    print(f"disegno: {petali} petali, {anelli} anelli, tonalita' {tonalita:.0f}°, seme {seed}")
    percorso = salva(petali, anelli, tonalita, seed)
    print(f"salvato in: {percorso}")
