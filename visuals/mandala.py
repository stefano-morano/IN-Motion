"""
Il mandala della sessione, come immagine vera da portare via.

A schermo il mandala e' fatto di 13.664 particelle che si muovono; qui ne
disegniamo centinaia di migliaia, ferme, ad alta risoluzione. E' lo stesso
disegno — stessi petali, stessi anelli, stesso colore, stesso seme — ma
pensato per essere stampato o tenuto, non guardato per quaranta secondi.

Non serve TouchDesigner: la geometria e' la stessa manciata di formule, e
disegnarla qui vuol dire che l'immagine si genera anche se TD non e' aperto.

    python3 mandala.py 7 3 186 42      # petali anelli tonalita seme
    python3 mandala.py 7 3 186 42 Q1   # ...e l'emozione, che apre il gradiente
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

# L'alone di sfondo. Le tinte scritte qui sono quelle BLU di partenza: nel
# disegno finito prendono la tonalita' personale, tenendo la loro saturazione e
# la loro luminosita' (vedi _sfondo_tinto). Sono piu' chiare di quelle a
# schermo — 0.115 contro 0.085 al centro — perche' l'immagine ferma non ha il
# bagliore a darle aria e il fondo deve fare quel lavoro da solo.
SFONDO_CENTRO = (0.045, 0.060, 0.115)
SFONDO_BORDO = (0.004, 0.006, 0.016)
VIGNETTA = 0.35            # quanto scuriscono i bordi

# Quanto sono accesi i colori. 1.0 e' la taratura originale, che alla prova
# usciva slavata: in fusione additiva le particelle sovrapposte sommano la luce
# e la spingono verso il bianco, quindi una saturazione che sul singolo colore
# sembra giusta a schermo si perde. Si alza la SATURAZIONE e basta — tonalita'
# e luminosita' restano quelle tarate, cosi' questa manopola cambia quanto il
# colore e' acceso e non quale colore e'.
#
# Il tetto pratico e' 1.5: da li' in su rosso e ambra sbattono contro la
# saturazione piena, le due tinte del gradiente ci arrivano insieme e il
# mandala diventa una tinta unita invece di un passaggio.
INTENSITA_COLORE = 1.35
# Copia del valore di visuals/td_face_points.py, come per GRADIENTE: se lo
# cambi qui, cambialo anche li' — altrimenti l'immagine da portare via non e'
# piu' il mandala che la persona ha visto.

# ---------- il gradiente, per emozione ----------
# La tonalita' scelta da Claude resta l'ANCORA: e' il colore personale, ricavato
# da cio' che la persona ha raccontato, e non va sostituito. L'emozione decide
# invece come quel colore si APRE in un gradiente — di quanti gradi la tinta
# luminosa si stacca da quella profonda, e quanto restano sature entrambe.
#
# Il criterio e' l'arousal, lo stesso che guida la musica: piu' l'emozione e'
# attiva piu' il salto e' ampio e il colore acceso (il mandala attraversa piu'
# tinte e sembra muoversi), piu' e' quieta piu' il gradiente si stringe attorno
# a una tinta sola (il disegno diventa quasi monocromo, e sta fermo).
#
# 'apertura' e' l'ampiezza TOTALE del gradiente in gradi, e si apre a CAVALLO
# dell'ancora: la tinta profonda sta mezza apertura da una parte, quella
# luminosa mezza dall'altra. E' la differenza fra modulare il colore personale
# e sostituirlo — spostando entrambe le tinte dalla stessa parte, la tinta
# luminosa (che l'occhio legge per prima) diventava lei il colore del mandala e
# la tonalita' scelta da Claude spariva: con la stessa ancora, Q1 usciva blu e
# Q2 verde. Aperto cosi', l'ancora resta il centro e cambia solo quanta strada
# il colore percorre.
# 'verso' dice da che parte va la tinta luminosa: non cambia il centro, ma
# evita che due emozioni di pari apertura si somiglino.
#
# Le aperture sono state provate anche molto piu' larghe (86/74/32/14),
# pensando che stringendosi cosi' il mandala uscisse quasi monocromo. Messe a
# confronto una accanto all'altra non e' vero: cambia pochissimo, perche' fra
# le due tinte quello che l'occhio legge e' soprattutto il salto di
# LUMINOSITA', non quello di tonalita' — e in cambio le due tinte si
# allontanano abbastanza dall'ancora da non farla piu' riconoscere. Restano
# questi.
GRADIENTE = {
    "Q1": {"apertura": 46.0, "verso": 1, "sat_fondo": 0.86, "sat_luce": 0.60},   # felice-attivo
    "Q2": {"apertura": 42.0, "verso": -1, "sat_fondo": 0.92, "sat_luce": 0.68},  # teso-agitato
    "Q3": {"apertura": 24.0, "verso": -1, "sat_fondo": 0.88, "sat_luce": 0.55},  # triste-spento
    "Q4": {"apertura": 14.0, "verso": 1, "sat_fondo": 0.80, "sat_luce": 0.45},   # calmo
}
# Lo stesso ripiego di testi.py: se l'emozione manca o non si riconosce, Q2 e'
# il viaggio che funziona per piu' gente.
EMOZIONE_PREDEFINITA = "Q2"


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


def _sfondo_tinto(rgb, tonalita):
    """L'alone di sfondo nella tonalita' personale.

    Cambia SOLO la tinta: saturazione e luminosita' restano quelle tarate sul
    blu, perche' il fondo deve continuare a essere un alone appena percettibile
    che da' aria al nero, non una macchia di colore dietro il mandala."""
    _, sat, val = colorsys.rgb_to_hsv(*rgb)
    return colorsys.hsv_to_rgb((float(tonalita) % 360.0) / 360.0,
                               min(1.0, sat * INTENSITA_COLORE), val)


def _colora(luce, tonalita, lato, emozione=EMOZIONE_PREDEFINITA):
    """Dalla quantita' di luce al colore: le zone deboli prendono la tinta
    profonda, quelle intense la tinta chiara. Due toni invece di uno solo
    schiarito — altrimenti il risultato sembra finto.

    Quanto le due tinte distano fra loro, e quanto sono sature, lo decide
    l'emozione (vedi GRADIENTE): e' li' che il colore smette di essere una
    tinta sola e diventa un gradiente che racconta come sta la persona."""
    g = GRADIENTE.get(emozione, GRADIENTE[EMOZIONE_PREDEFINITA])
    h = (float(tonalita) % 360.0) / 360.0
    # le due tinte si aprono a cavallo dell'ancora, mezza apertura per parte:
    # due toni identici cambiati solo di luminosita' darebbero un risultato
    # piatto, ma spostarli entrambi dalla stessa parte perderebbe l'ancora
    mezza = (g["apertura"] / 2.0) / 360.0 * g["verso"]
    h_fondo = (h - mezza) % 1.0
    h_chiaro = (h + mezza) % 1.0
    sat_fondo = min(1.0, g["sat_fondo"] * INTENSITA_COLORE)
    sat_luce = min(1.0, g["sat_luce"] * INTENSITA_COLORE)
    fondo = np.array(colorsys.hsv_to_rgb(h_fondo, sat_fondo, 0.34), dtype=np.float32)
    # la saturazione della tinta chiara conta piu' di quanto sembri: e' quella
    # delle zone piu' luminose, cioe' quelle che si vedono per prime. Troppo
    # bassa e il mandala sbiadisce verso il bianco proprio dove dovrebbe essere
    # piu' vivo.
    chiaro = np.array(colorsys.hsv_to_rgb(h_chiaro, sat_luce, 1.0), dtype=np.float32)

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
    centro = np.array(_sfondo_tinto(SFONDO_CENTRO, tonalita), dtype=np.float32)
    bordo = np.array(_sfondo_tinto(SFONDO_BORDO, tonalita), dtype=np.float32)
    sfondo = centro + (bordo - centro) * distanza

    immagine = sfondo + disegno
    immagine *= 1.0 - VIGNETTA * distanza ** 2      # bordi piu' scuri
    return np.clip(immagine, 0.0, 1.0)


def genera(petali, anelli, tonalita, seed, lato=DIMENSIONE,
           emozione=EMOZIONE_PREDEFINITA):
    """L'immagine del mandala, pronta da salvare."""
    angoli, raggi = posizioni(petali, anelli, seed)
    mappa = _densita(angoli, raggi, lato)
    luce = _bagliore(mappa)
    finale = _colora(luce, tonalita, lato, emozione)
    return Image.fromarray((finale * 255).astype(np.uint8), mode='RGB')


def salva(petali, anelli, tonalita, seed, cartella=None,
          emozione=EMOZIONE_PREDEFINITA):
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
        genera(petali, anelli, tonalita, seed, emozione=emozione).save(percorso)
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
    emozione = argomenti[4].upper() if len(argomenti) > 4 else EMOZIONE_PREDEFINITA

    print(f"disegno: {petali} petali, {anelli} anelli, tonalita' {tonalita:.0f}°, "
          f"seme {seed}, emozione {emozione}")
    percorso = salva(petali, anelli, tonalita, seed, emozione=emozione)
    print(f"salvato in: {percorso}")
