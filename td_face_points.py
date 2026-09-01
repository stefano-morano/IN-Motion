# COPIA DI RIFERIMENTO — l'originale vive dentro visual_TD.toe
# (nodo /project1/face_points_callbacks).
#
# Serve perche' il .toe e' binario: senza questa copia le modifiche alla
# logica di TouchDesigner sarebbero invisibili a git e irrecuperabili se
# il progetto si corrompesse. Modificare QUI non cambia nulla: va
# ricaricata dentro TD con:
#   op('/project1/face_points_callbacks').text = open('td_face_points.py').read()

# Decide dove deve stare ogni particella, e di che colore, fotogramma per
# fotogramma.
#
# Riceve i 1434 numeri di MediaPipe (x,y,z, x,y,z, ...) e li usa per costruire
# la forma "volto"; in alternativa usa una scritta gia' preparata, oppure il
# mandala della sessione. Poi fa danzare le particelle da una forma all'altra.
#
# Chi comanda e' Python (main.py) via OSC: qui non c'e' nessuna sequenza
# automatica, questo modulo e' solo il motore che disegna.
#
# IMPORTANTE: le scritte si preparano con prepara_testi(), che va chiamata da
# FUORI. Far ricalcolare un altro nodo da dentro onCook manda TD in crash.

import colorsys
import math
import os

import numpy as np

# ---------- forma del volto ----------
ASPETTO = 16.0 / 9.0    # la webcam e' 16:9, senza questo il volto e' stretto
SCALA = 2.0

TOTALE_PARTICELLE = 13664

# Come si distribuiscono le particelle fra i triangoli della mesh.
# I punti di MediaPipe sono fittissimi attorno a occhi, narici e labbra e radi
# sulle guance. Le due strade estreme sono state provate entrambe e sbagliano
# tutte e due:
#   esponente 0  -> quota uguale per triangolo: i lineamenti si vedono benissimo
#                   (sono proprio gli addensamenti a disegnarli) ma in fusione
#                   additiva bruciano in macchie bianche
#   esponente 1  -> densita' di superficie uniforme: niente piu' bruciature,
#                   ma il volto diventa una macchia informe senza occhi ne' bocca
# La via di mezzo tiene gli addensamenti che disegnano il viso, smorzandoli
# quanto basta perche' non saturino.
ESPONENTE_DENSITA = 0.45

# ---------- scritte ----------
# Ingombro massimo concesso a una scritta: viene ridimensionata per starci
# dentro, qualunque sia la sua lunghezza, cosi' non esce mai dall'inquadratura.
TESTO_LARGHEZZA = 1.9
TESTO_ALTEZZA = 0.9

# ---------- colore ----------
# Ogni particella ha il SUO colore, preso lungo un gradiente fra due tinte:
# una profonda e spenta, una luminosa. Non e' decorazione — e' quello che da'
# profondita': le particelle di nebbia pescano dal fondo scuro e sprofondano,
# quelle della forma pescano dall'alto e vengono avanti. Con un colore piatto
# la nuvola sembra un adesivo, con il gradiente sembra volume.
#
# Il materiale e' in fusione additiva: dove le particelle si sovrappongono la
# luce si somma, come polvere illuminata. Per questo i valori di partenza sono
# bassi: sono la luce di UNA particella, non quella che si vede.
PALETTE_CALMA = {
    'fondo':  (0.020, 0.045, 0.115),  # indaco profondo
    'luce':   (0.300, 0.460, 0.640),  # azzurro, non bianco
}
NEBBIA_LUMINOSITA = 0.35   # quanto sono piu' spente le particelle sospese
SCINTILLIO = 0.16          # quanto ogni particella respira di luce propria
SCINTILLIO_VELOCITA = 0.35
PROFONDITA_COLORE = 0.30   # quanto la vicinanza all'osservatore schiarisce

# ---------- mandala ----------
# Non serve disegnarlo e poi campionarlo come il testo: anelli concentrici
# modulati da piu' armoniche si descrivono con poche formule, quindi le
# posizioni si generano direttamente.
#
# Essendo circolare e' l'ALTEZZA dell'inquadratura a vincolarlo, non la
# larghezza: il raggio viene ricavato dalla telecamera invece che fissato a
# mano, cosi' resta dentro il fotogramma anche se cambi fov o distanza.
MANDALA_RIEMPIMENTO = 0.88   # quanta parte dell'altezza visibile occupa
MANDALA_PETALO = 0.26        # quanto i petali fanno respirare il raggio
MANDALA_ARMONICA = 0.10      # secondo ordine di petali: aggiunge merletto
MANDALA_SFASAMENTO = True    # anelli alternati ruotati di mezzo petalo
MANDALA_CUPOLA = 0.16        # rilievo al centro: lo rende una cupola, non un disco
MANDALA_SPESSORE = 0.035     # quanto e' spesso ogni anello
MANDALA_ROTAZIONE = 0.06     # giri al secondo (lenta: ~17s per giro completo)
MANDALA_NEBBIA = 0.3         # la nebbia che va bene per volto e testo qui
                             # cancellerebbe il disegno: il mandala e' l'unica
                             # forma che deve leggersi nitida, non suggerita

# ---------- la polvere iniziale ----------
# La nuvola sparsa che si vede all'apertura, prima che le particelle si
# raccolgano nel benvenuto.
POLVERE_AMPIEZZA = 0.68     # larghezza della nuvola, in frazione dell'inquadratura.
                            # Piu' in alto (0.85) riempie ancora, ma diventa un
                            # cielo stellato uniforme: si perde il cuore denso
                            # al centro, e con lui l'idea che sia UNA nuvola
POLVERE_PROFONDITA = 1.00   # quanto si estende in Z: e' la profondita' vera,
                            # quella che fa sembrare la nuvola uno spazio e
                            # non un adesivo piatto
POLVERE_ARRETRAMENTO = 0.30 # la nuvola sta un po' PIU' INDIETRO dell'origine:
                            # le particelle davanti diventano piu' grandi per
                            # prospettiva, e qualche sassata vicinissima
                            # all'obiettivo sembra un difetto, non profondita'
SEME_POLVERE = 20260827     # fisso, cosi' l'apertura e' sempre la stessa

# ---------- dissolvenza d'apertura ----------
# Lo schermo parte nero e sale. Non e' un effetto sulle particelle: e' l'intera
# immagine che si accende, quindi vive su un Level TOP a valle di tutto.
DURATA_DISSOLVENZA = 3.0
# La salita NON e' lineare. L'occhio distingue molto meglio le differenze in
# penombra che quelle in piena luce: con una rampa lineare l'immagine "arriva"
# quasi subito e poi passa il resto del tempo a schiarire di poco — si vede
# comparire, non nascere. Elevando l'avanzamento a questa potenza il nero
# resta nero piu' a lungo e la luce sale alla fine, che e' come la percepiamo.
CURVA_DISSOLVENZA = 2.2

# ---------- dissoluzione ----------
# L'ultima scena. Il mandala NON si ferma: continua a ruotare, galleggiare e
# respirare come ha sempre fatto, e ogni particella continua a inseguire il
# proprio posto con la propria inerzia.
#
# Cambia una cosa sola: il naso diventa una calamita che respinge. Le
# particelle che entrano nel suo raggio d'azione ricevono una spinta e si
# LIBERANO — smettono di inseguire il mandala e volano via per conto loro,
# ognuna con la velocita' che ha ricevuto. Non tornano indietro, e non perche'
# glielo impedisca una forza apposta: semplicemente non hanno piu' un posto a
# cui tornare. E' li' che sta l'irreversibilita' del gesto.
NASO = 4                     # punta del naso: il punto piu' sporgente dei 478
RAGGIO_NASO = 0.38           # entro quanto la calamita fa effetto. Fuori di qui
                             # le particelle non si accorgono di nulla, ed e'
                             # cio' che rende il gesto una spinta mirata invece
                             # di un soffio uniforme su tutto.
FORZA_NASO = 3.00            # quanto schizzano via, a parita' di velocita' del naso
VELOCITA_LIBERAZIONE = 0.25  # oltre questa velocita' propria una particella e'
                             # libera del tutto e non insegue piu' il mandala
SPINTA_Z = 0.30              # quanto della spinta va in profondita'. Tenuta
                             # bassa: a piena forza qualche particella schizza
                             # verso l'osservatore e diventa un quadrone enorme,
                             # che sembra un difetto invece che un effetto.
ATTRITO_FUGA = 0.999         # quasi nessuno: chi e' partito continua ad andare
SOGLIA_MOVIMENTO = 0.20      # sotto questa velocita' del naso e' respiro e
                             # imprecisione del tracciamento, non volonta'

DURATA_TRANSIZIONE = 4.0  # secondi per passare da una forma all'altra
RITARDO_MAX = 0.7         # 0 = tutte le particelle partono insieme,
                          # 1 = molto sfalsate (l'effetto e' un'onda)
ESPANSIONE = 0.10         # quanto si allargano a meta' viaggio, in frazione
                          # della dimensione della forma

# ---------- nebbia ----------
FRAZIONE_NEBBIA = 0.40    # quante particelle restano sospese intorno
NEBBIA_RAGGIO = 0.035     # quanto si allontanano, in frazione della forma

# ---------- fluttuazione (movimento individuale) ----------
FLUTTUAZIONE = 0.012      # nessuna particella sta mai ferma
FLUTTUAZIONE_NEBBIA = 3.0 # la nebbia oscilla di piu'

# ---------- corrente (movimento comune) ----------
# Una spinta che dipende da DOVE si trova la particella, non da chi e'.
# Particelle vicine ricevono quasi la stessa spinta, quindi le forme
# galleggiano intere invece di limitarsi a vibrare sul posto.
CORRENTE_AMPIEZZA = 0.035  # quanto spinge
CORRENTE_SCALA = 1.4       # ampiezza delle zone che si muovono insieme:
                           # piu' basso = zone piu' grandi, piu' compatte
CORRENTE_VELOCITA = 0.25   # quanto lentamente scorre

# ---------- inerzia ----------
INERZIA_MIN = 0.04        # piu' basso = piu' pigra = scia piu' lunga
INERZIA_MAX = 0.28

# Tutto cio' che va calcolato una volta sola vive qui: ricalcolarlo ad ogni
# fotogramma farebbe "bollire" le particelle invece di farle muovere.
_c = {}


def _quote_per_area(triangoli, P):
    """Quante particelle tocca a ciascun triangolo. In proporzione all'area,
    cosi' la superficie ha densita' uniforme invece di ammassarsi dove i punti
    del viso sono fitti. Serve una posa di riferimento per misurare le aree:
    se il volto si avvicina o allontana scalano tutte insieme, quindi le
    proporzioni restano valide e il calcolo si fa una volta sola."""
    if P is None:
        # nessuna posa disponibile: ripiego sulla divisione in parti uguali
        quota = max(TOTALE_PARTICELLE // triangoli.shape[0], 1)
        return np.full(triangoli.shape[0], quota, dtype=np.int64)

    v0, v1, v2 = P[triangoli[:, 0]], P[triangoli[:, 1]], P[triangoli[:, 2]]
    aree = 0.5 * np.linalg.norm(np.cross(v1 - v0, v2 - v0), axis=1)
    if float(aree.sum()) <= 1e-9:
        quota = max(TOTALE_PARTICELLE // triangoli.shape[0], 1)
        return np.full(triangoli.shape[0], quota, dtype=np.int64)

    # l'esponente decide quanto seguire l'area (vedi ESPONENTE_DENSITA)
    peso = np.power(aree, ESPONENTE_DENSITA)
    peso /= peso.sum()

    # almeno una particella ciascuno: nessun triangolo deve sparire del tutto
    conteggi = np.maximum(1, np.round(peso * TOTALE_PARTICELLE)).astype(np.int64)

    # l'arrotondamento sballa il totale: si aggiusta sui triangoli piu' grandi,
    # dove una particella in piu' o in meno non si nota
    differenza = TOTALE_PARTICELLE - int(conteggi.sum())
    if differenza:
        ordine = np.argsort(-aree)
        passo = 1 if differenza > 0 else -1
        for i in range(abs(differenza)):
            j = ordine[i % ordine.size]
            if conteggi[j] + passo >= 1:
                conteggi[j] += passo
    return conteggi


def _prepara(n, P=None):
    """Sorteggia, una volta sola, le caratteristiche fisse di ogni particella:
    dove sta dentro il suo triangolo, quanto e' pigra, se e' nebbia, come
    oscilla, in che direzione fiorisce, che tono di colore le tocca."""
    percorso = os.path.join(project.folder, 'face_triangoli.txt')
    triangoli = np.loadtxt(percorso, dtype=np.int64, comments='#')

    rng = np.random.default_rng(7)

    conteggi = _quote_per_area(triangoli, P)
    idx = np.repeat(triangoli, conteggi, axis=0)
    n_part = idx.shape[0]

    # posizione casuale dentro ogni triangolo (coordinate baricentriche)
    r = rng.random((n_part, 2))
    fuori = r.sum(axis=1) > 1.0
    r[fuori] = 1.0 - r[fuori]
    pesi = np.column_stack([1.0 - r[:, 0] - r[:, 1], r[:, 0], r[:, 1]]).astype('float32')

    _c['a'], _c['b'], _c['c'] = idx[:, 0], idx[:, 1], idx[:, 2]
    _c['pesi'] = pesi

    _c['inerzia'] = rng.uniform(
        INERZIA_MIN, INERZIA_MAX, (n_part, 1)).astype('float32')

    e_nebbia = rng.random(n_part) < FRAZIONE_NEBBIA
    scostamento = rng.normal(0.0, 1.0, (n_part, 3)).astype('float32')
    scostamento[~e_nebbia] = 0.0
    _c['nebbia'] = scostamento
    _c['e_nebbia'] = e_nebbia

    _c['frequenze'] = rng.uniform(0.15, 0.6, (n_part, 3)).astype('float32')
    _c['fasi'] = rng.uniform(0.0, 6.283, (n_part, 3)).astype('float32')
    ampiezze = np.where(e_nebbia, FLUTTUAZIONE * FLUTTUAZIONE_NEBBIA, FLUTTUAZIONE)
    _c['ampiezze'] = ampiezze.astype('float32')[:, None]

    # ogni particella parte con un suo ritardo: e' questo che trasforma la
    # transizione in un'onda invece che in uno spostamento in blocco
    _c['ritardi'] = rng.uniform(0.0, RITARDO_MAX, (n_part, 1)).astype('float32')

    # direzione in cui "fiorisce" a meta' transizione
    d = rng.normal(0.0, 1.0, (n_part, 3))
    d /= np.linalg.norm(d, axis=1, keepdims=True)
    _c['direzioni'] = d.astype('float32')

    # dove pesca ogni particella lungo il gradiente di colore. La nebbia pesca
    # in basso (resta sul fondo scuro), la forma in alto (viene avanti).
    tono = rng.uniform(0.45, 1.0, n_part)
    tono[e_nebbia] = rng.uniform(0.0, NEBBIA_LUMINOSITA, int(e_nebbia.sum()))
    _c['tono'] = tono.astype('float32')
    _c['scint_freq'] = rng.uniform(0.5, 1.6, n_part).astype('float32')
    _c['scint_fase'] = rng.uniform(0.0, 6.283, n_part).astype('float32')

    _c['posizioni'] = None
    _c['n'] = n
    # ricorda se le aree sono state misurate su un volto vero: se no, va
    # rifatto appena arriva il primo fotogramma buono
    _c['per_area'] = P is not None


def _campiona_scritta(n):
    """Legge la scritta attualmente disegnata da testo_top e sceglie n pixel
    accesi a caso come bersagli. Usandone solo una parte il testo resta
    rarefatto: si intuisce invece di essere pieno. NON fa cuocere nulla."""
    img = op('testo_top').numpyArray(delayed=False)
    if img is None:
        return None

    righe, colonne = np.nonzero(img[..., 0] > 0.5)
    if righe.size == 0:
        return None

    rng = np.random.default_rng(99)
    scelti = rng.choice(righe.size, size=n, replace=(righe.size < n))

    # misura l'ingombro vero della scritta e la scala per farla stare nel
    # riquadro concesso, mantenendo le proporzioni
    c_min, c_max = float(colonne.min()), float(colonne.max())
    r_min, r_max = float(righe.min()), float(righe.max())
    scala = min(TESTO_LARGHEZZA / max(c_max - c_min, 1.0),
                TESTO_ALTEZZA / max(r_max - r_min, 1.0))

    cam = op('face_cam')
    pos = np.empty((n, 3), dtype='float32')
    pos[:, 0] = cam.par.tx.eval() + (colonne[scelti] - (c_min + c_max) / 2.0) * scala
    pos[:, 1] = cam.par.ty.eval() + (righe[scelti] - (r_min + r_max) / 2.0) * scala
    pos[:, 2] = 0.0
    return pos


def _raggio_visibile():
    """Il raggio piu' grande che sta dentro l'inquadratura. Il fov di TD e'
    ORIZZONTALE, quindi l'altezza va ricavata dividendo per il rapporto
    d'aspetto: e' l'altezza a limitare una forma circolare."""
    cam = op('face_cam')
    render = op('face_render')
    mezza_larghezza = math.tan(math.radians(cam.par.fov.eval()) / 2.0) * cam.par.tz.eval()
    aspetto = render.par.resolutionw.eval() / render.par.resolutionh.eval()
    return (mezza_larghezza / aspetto) * MANDALA_RIEMPIMENTO


def _forma_polvere(n):
    """Particelle sparse: la nuvola da cui nasce il benvenuto.

    Si calcola UNA VOLTA SOLA e si ricorda. Rigenerarla ad ogni fotogramma
    non darebbe una nuvola sospesa ma rumore che sfarfalla, e soprattutto non
    sarebbe una forma verso cui muoversi: le particelle inseguirebbero un
    bersaglio che si sposta a caso sessanta volte al secondo.

    Tre scelte, tutte e tre visibili a occhio:

    GAUSSIANA, NON UNIFORME. Si addensa al centro e si dirada verso i bordi,
    come polvere vera dentro un fascio di luce. Una nuvola uniforme si legge
    come un rettangolo di puntini, e si vede che e' stata calcolata.

    CENTRATA SULL'INQUADRATURA, NON SULL'ORIGINE. La telecamera e' spostata
    in basso (ty negativo) per inquadrare bene il volto: una nuvola centrata
    sull'origine finisce percio' nella meta' alta dello schermo. Il centro
    giusto e' dove la telecamera guarda, e si ricava da lei — cosi' resta
    giusto anche se un giorno la si sposta.

    PIU' LARGA CHE ALTA. L'inquadratura e' 16:10, quindi una nuvola circolare
    lascerebbe i lati vuoti. La larghezza segue il rapporto d'aspetto."""
    pos = _c.get('polvere')
    if pos is not None and pos.shape[0] == n:
        return pos

    cam = op('face_cam')
    render = op('face_render')
    aspetto = render.par.resolutionw.eval() / render.par.resolutionh.eval()
    raggio = _raggio_visibile()

    rng = np.random.default_rng(SEME_POLVERE)
    pos = np.empty((n, 3), dtype='float32')
    pos[:, 0] = rng.normal(0.0, raggio * POLVERE_AMPIEZZA * aspetto, n)
    pos[:, 1] = rng.normal(0.0, raggio * POLVERE_AMPIEZZA, n)
    pos[:, 2] = rng.normal(0.0, raggio * POLVERE_PROFONDITA, n)

    pos[:, 0] += cam.par.tx.eval()
    pos[:, 1] += cam.par.ty.eval()
    pos[:, 2] -= raggio * POLVERE_ARRETRAMENTO

    _c['polvere'] = pos
    return pos


def buio():
    """Schermo nero. Ci resta finche' non si chiama accendi()."""
    _c['dissolvenza'] = (None, 0.0)


def accendi(durata=DURATA_DISSOLVENZA):
    """Fa salire l'immagine dal nero, in 'durata' secondi."""
    _c['dissolvenza'] = (absTime.seconds, float(durata))


def luminosita(ora=None):
    """Quanto e' accesa l'immagine adesso: 0 nero, 1 piena.

    L'ORA VA PASSATA DA FUORI, e non e' un vezzo. Questa funzione sta in una
    espressione su un parametro del Level TOP, e TouchDesigner rivaluta una
    espressione solo quando cambia qualcosa da cui DICHIARA di dipendere.
    Leggendo absTime qui dentro, TD non puo' accorgersene: vede una chiamata
    Python opaca, la valuta una volta e tiene il risultato in cache per
    sempre. La dissolvenza non risultava lenta — non avveniva affatto, e la
    luce saltava da 0 a 1 in un colpo appena qualcos'altro forzava un
    ricalcolo. Mettendo absTime.seconds nel TESTO dell'espressione, la
    dipendenza dal tempo diventa visibile e il parametro si aggiorna ad ogni
    fotogramma.

    Se nessuno ha mai chiesto una dissolvenza risponde 1: il comportamento
    normale e' vedere."""
    if ora is None:
        ora = absTime.seconds
    stato = _c.get('dissolvenza')
    if stato is None:
        return 1.0
    t0, durata = stato
    if t0 is None:
        return 0.0
    if durata <= 0.0:
        return 1.0
    avanzamento = min(1.0, max(0.0, (ora - t0) / durata))
    return avanzamento ** CURVA_DISSOLVENZA


def _riparti(n, gruppi):
    """n diviso in 'gruppi' parti il piu' uguali possibile."""
    base, resto = divmod(n, gruppi)
    return [base + (1 if i < resto else 0) for i in range(gruppi)]


def _genera_mandala(n, petali, anelli, seed):
    """Posizioni disposte in anelli concentrici, ciascuno modulato da 'petali'
    lobi piu' una seconda armonica che aggiunge merletto. Gli anelli alternati
    sono sfasati di mezzo petalo (i lobi si incastrano invece di allinearsi) e
    la simmetria viene dagli ANGOLI, non dal raggio: e' quello che la rende
    leggibile anche quando gli anelli sono tanti."""
    anelli = max(int(anelli), 1)
    petali = max(int(petali), 2)
    rng = np.random.default_rng(int(seed))

    raggio_max = _raggio_visibile()
    conteggi = _riparti(n, anelli)

    # Distanza fra un anello e il successivo. Tutto cio' che sposta le
    # particelle in senso radiale — petali, armonica, spessore — viene tenuto
    # sotto questa misura: altrimenti con molti anelli i lobi di uno invadono
    # il vicino e il mandala diventa una macchia invece che un disegno.
    spaziatura = (0.82 / anelli) * raggio_max
    sfogo = spaziatura * 0.45

    angoli = np.empty(n, dtype='float32')
    raggi = np.empty(n, dtype='float32')

    inizio = 0
    for i, conteggio in enumerate(conteggi):
        if conteggio == 0:
            continue
        fetta = slice(inizio, inizio + conteggio)
        inizio += conteggio

        # gli anelli non partono dal centro: lasciano un occhio libero
        quota = (i + 1) / anelli
        raggio_base = raggio_max * (0.18 + 0.82 * quota)

        # le ampiezze sono in frazione del raggio dell'anello, ma non possono
        # superare lo sfogo concesso fra un anello e l'altro
        ampiezza = min(MANDALA_PETALO * raggio_base, sfogo) / raggio_base
        armonica = min(MANDALA_ARMONICA * raggio_base, sfogo * 0.4) / raggio_base

        # La simmetria si ottiene raggruppando le particelle ATTORNO A CERTI
        # ANGOLI, non spostandole in raggio: cosi' i petali restano leggibili
        # anche quando gli anelli sono tanti e lo spazio radiale e' poco.
        # I tre tipi si alternano in ordine fisso: alternarli a caso dava
        # composizioni slegate, a turno danno strati che si leggono.
        tipo_anello = i % 3
        if tipo_anello == 0:
            gruppi = petali                     # petali larghi
            dispersione = 0.20
        elif tipo_anello == 1:
            gruppi = petali * 2                 # perline fitte
            dispersione = 0.13
        else:
            gruppi = 0                          # anello continuo, fa da cornice

        if gruppi:
            passo = 2.0 * np.pi / gruppi
            a = rng.integers(0, gruppi, conteggio) * passo
            a = a + rng.normal(0.0, passo * dispersione, conteggio)
        else:
            a = rng.uniform(0.0, 2.0 * np.pi, conteggio)

        # anelli alternati sfasati: i lobi si incastrano fra loro
        fase = (np.pi / petali) * (i % 2) if MANDALA_SFASAMENTO else 0.0
        fase += rng.uniform(0.0, 0.4)

        modulazione = (1.0
                       + ampiezza * np.cos(petali * a + fase)
                       + armonica * np.cos(2 * petali * a + fase * 2.0))
        # anche lo spessore segue lo spazio disponibile: un anello non deve
        # mai essere piu' grasso della distanza che lo separa dal vicino
        spessore = rng.normal(0.0, min(MANDALA_SPESSORE * raggio_max, spaziatura * 0.16),
                              conteggio)

        angoli[fetta] = a
        raggi[fetta] = raggio_base * modulazione + spessore

    # I petali e le armoniche gonfiano il raggio in modo difficile da prevedere
    # a tavolino. Invece di tarare le costanti a mano, si misura la forma finita
    # e la si riscala: cosi' qualunque combinazione entra nell'inquadratura per
    # costruzione, e MANDALA_RIEMPIMENTO significa davvero "quanto la riempie".
    picco = float(np.abs(raggi).max())
    if picco > 1e-6:
        raggi *= raggio_max / picco

    # tenuti in polari: ruotare il mandala diventa una somma sull'angolo
    _c['mandala_angoli'] = angoli
    _c['mandala_raggi'] = raggi.astype('float32')
    _c['mandala_raggio_max'] = float(raggio_max)
    return n


def _forma_mandala(ora):
    """Le posizioni del mandala a questo istante, gia' ruotate. Restare in
    coordinate polari rende la rotazione una semplice somma sull'angolo,
    invece di una moltiplicazione di matrici su tutte le particelle."""
    angoli = _c['mandala_angoli'] + ora * (MANDALA_ROTAZIONE * 2.0 * np.pi)
    raggi = _c['mandala_raggi']
    raggio_max = _c['mandala_raggio_max']

    cam = op('face_cam')
    pos = np.empty((angoli.shape[0], 3), dtype='float32')
    pos[:, 0] = cam.par.tx.eval() + raggi * np.cos(angoli)
    pos[:, 1] = cam.par.ty.eval() + raggi * np.sin(angoli)
    # rilievo verso l'osservatore al centro: una cupola, non un disco piatto
    pos[:, 2] = np.cos(np.clip(raggi / raggio_max, 0.0, 1.0) * (np.pi / 2.0)) * MANDALA_CUPOLA
    return pos


def prepara_testi(frasi):
    """Disegna una per una le scritte e ne ricava le posizioni.
    DA CHIAMARE DA FUORI dal ciclo di rendering, mai da dentro onCook:
    far cuocere un nodo mentre un altro sta cuocendo fa crashare TouchDesigner."""
    if 'pesi' not in _c:
        _prepara(478)
    n = _c['pesi'].shape[0]

    top = op('testo_top')
    testi = dict(_c.get('testi', {}))
    for testo in frasi or []:
        top.par.text = testo
        top.cook(force=True)
        pos = _campiona_scritta(n)
        if pos is not None:
            testi[testo] = pos
    _c['testi'] = testi
    return sorted(testi.keys())


# ---------- il gradiente, per emozione ----------
# Copia dei valori di visuals/mandala.py: la tonalita' scelta da Claude e'
# l'ANCORA (il colore personale), l'emozione decide quanto il gradiente si apre
# a cavallo di quell'ancora — mezza apertura per la tinta profonda, mezza per
# la luminosa. Aprendolo cosi' invece di spostare entrambe le tinte dalla
# stessa parte, il colore personale resta il centro invece di essere
# sostituito. Se cambi i numeri qui, cambiali anche li'.
GRADIENTE = {
    "Q1": {"apertura": 46.0, "verso": 1, "sat_fondo": 0.86, "sat_luce": 0.60},
    "Q2": {"apertura": 42.0, "verso": -1, "sat_fondo": 0.92, "sat_luce": 0.68},
    "Q3": {"apertura": 24.0, "verso": -1, "sat_fondo": 0.88, "sat_luce": 0.55},
    "Q4": {"apertura": 14.0, "verso": 1, "sat_fondo": 0.80, "sat_luce": 0.45},
}
EMOZIONE_PREDEFINITA = "Q2"


def prepara_mandala(petali, anelli, tonalita, seed, emozione=EMOZIONE_PREDEFINITA):
    """Genera e ricorda la forma del mandala. E' puro calcolo, ma resta
    comandata da fuori come prepara_testi() per lasciare a TD un fotogramma."""
    if 'pesi' not in _c:
        _prepara(478)
    n = _c['pesi'].shape[0]
    _c['mandala_tonalita'] = float(tonalita)
    _c['mandala_emozione'] = str(emozione)
    return _genera_mandala(n, petali, anelli, seed)


def prepara_in_coda():
    """Eseguita un fotogramma dopo l'arrivo del messaggio OSC, cosi' il lavoro
    pesante non avviene dentro una callback."""
    return prepara_testi(_c.pop('da_preparare', None))


def prepara_mandala_in_coda():
    """Come prepara_in_coda, per il messaggio /mandala."""
    args = _c.pop('da_preparare_mandala', None)
    if not args or len(args) < 4:
        return None
    petali, anelli, tonalita, seed = args[:4]
    emozione = args[4] if len(args) > 4 else EMOZIONE_PREDEFINITA
    return prepara_mandala(petali, anelli, tonalita, seed, emozione)


def vai_a(tipo, testo='', durata=None):
    """Fa partire la transizione verso una nuova forma.
    E' il comando che Python manda via OSC."""
    if tipo == 'dissoluzione':
        # si parte da ferme, da dove sono adesso: nessuna transizione, la
        # dissoluzione prende in consegna le particelle dove le trova
        _c['fuga'] = None
        _c['libera'] = None
        _c['naso_prec'] = None
        _c['t_diss'] = None
    _c['scena_da'] = _c.get('scena_a', ('volto', ''))
    _c['scena_a'] = (tipo, testo)
    _c['t0'] = absTime.seconds
    _c['durata'] = DURATA_TRANSIZIONE if durata is None else float(durata)
    return _c['scena_a']


def azzera():
    """Riporta la scena all'inizio, senza transizione.

    TouchDesigner resta aperto fra una sessione e l'altra, quindi si ricorda
    tutto: chi rilancia main.py si troverebbe davanti l'ultima schermata di
    chi c'e' stato prima — di solito il "GRAZIE, A PRESTO" del commiato — e la
    vedrebbe restare li' per tutti i secondi che Python impiega a svegliarsi.

    Qui si buttano via tre cose:
      - la dissoluzione in corso, se la sessione era finita li' (altrimenti le
        particelle resterebbero "libere" e la scena nuova non le riprenderebbe)
      - la scena corrente, riportata al volto: e' lo stato neutro da cui parte
        anche un TouchDesigner appena aperto
      - le scritte in memoria, comprese le frasi personali di chi ha appena
        finito: non servono piu' a nessuno e non e' roba da lasciare in giro

    Le POSIZIONI delle particelle non si toccano apposta: lasciandole dove
    sono, scivolano verso il volto con la loro inerzia invece di saltarci di
    scatto. Un salto si vedrebbe come un errore."""
    _c['fuga'] = None
    _c['libera'] = None
    _c['naso_prec'] = None
    _c['t_diss'] = None
    _c['testi'] = {}
    _c['dissolvenza'] = None      # luce piena: il buio si chiede apposta
    _c['scena_da'] = ('volto', '')
    _c['scena_a'] = ('volto', '')
    _c['t0'] = absTime.seconds
    _c['durata'] = 0.0
    return _c['scena_a']


def _forma_volto(P):
    w = _c['pesi']
    return (P[_c['a']] * w[:, 0:1]
            + P[_c['b']] * w[:, 1:2]
            + P[_c['c']] * w[:, 2:3])


def _forma(scena, P, n, ora, sorgente=False):
    """Le posizioni-bersaglio di una scena. Se una scritta o il mandala non
    sono stati preparati, ripiega sul volto invece di rompere l'animazione.

    sorgente=True quando e' la forma da cui si VIENE, non quella verso cui si
    va: per la dissoluzione le due cose sono diverse, vedi sotto."""
    tipo = scena[0]
    if tipo == 'dissoluzione':
        if sorgente:
            # Si viene DA una dissoluzione: le particelle stanno sparse dove
            # le ha lasciate il gesto, e la fusione verso la scritta finale
            # deve partire DA LI'. Rispondendo "il mandala" si ricomponeva
            # tutto per una frazione di secondo prima di andare alle parole —
            # esattamente cio' che il gesto aveva appena disfatto.
            pos = _c.get('posizioni')
            if pos is not None and pos.shape[0] == n:
                return pos
            return _forma_volto(P)
        # Ci si va: il bersaglio resta il mandala, che continua a ruotare.
        # Sono le particelle liberate a smettere di inseguirlo.
        tipo = 'mandala'
    if tipo == 'mandala':
        if _c.get('mandala_raggi') is None or _c['mandala_raggi'].shape[0] != n:
            return _forma_volto(P)
        return _forma_mandala(ora)
    if tipo == 'polvere':
        return _forma_polvere(n)
    if tipo == 'testo':
        pos = _c.get('testi', {}).get(scena[1])
        if pos is not None and pos.shape[0] == n:
            return pos
    return _forma_volto(P)


def _palette(tipo):
    """Le due tinte fra cui pesca ogni particella. Volto e testo restano sul
    blu di sempre; il mandala prende la tonalita' scelta da Claude, declinata
    in una versione profonda e una luminosa della stessa tinta."""
    # la dissoluzione e' il mandala che si disfa: tiene il suo colore
    if tipo not in ('mandala', 'dissoluzione') or 'mandala_tonalita' not in _c:
        return PALETTE_CALMA['fondo'], PALETTE_CALMA['luce']

    # I valori restano bassi come nella palette blu: sono la luce di UNA
    # particella, e in fusione additiva dove si sovrappongono si somma. Una
    # tinta luminosa vicina al bianco pieno satura e il colore scelto da
    # Claude sparisce — che e' esattamente il contrario di quello che serve.
    g = GRADIENTE.get(_c.get('mandala_emozione'), GRADIENTE[EMOZIONE_PREDEFINITA])
    h = (_c['mandala_tonalita'] % 360.0) / 360.0
    # le due tinte si aprono a cavallo dell'ancora, mezza apertura per parte:
    # due toni identici cambiati solo di luminosita' darebbero un risultato
    # piatto, ma spostarli entrambi dalla stessa parte perderebbe l'ancora
    mezza = (g["apertura"] / 2.0) / 360.0 * g["verso"]
    fondo = colorsys.hsv_to_rgb((h - mezza) % 1.0, g["sat_fondo"], 0.090)
    luce = colorsys.hsv_to_rgb((h + mezza) % 1.0, g["sat_luce"], 0.620)
    return fondo, luce


def _colori(tipo_da, tipo_a, avanzamento, pos, ora):
    """Il colore di ogni particella: un punto lungo il gradiente fra la tinta
    profonda e quella luminosa. Durante una transizione le due palette si
    mescolano, cosi' il colore cambia insieme alla forma invece di scattare."""
    fondo_a, luce_a = _palette(tipo_a)
    if tipo_da != tipo_a and avanzamento < 1.0:
        fondo_d, luce_d = _palette(tipo_da)
        k = avanzamento
        fondo = tuple(fondo_d[i] * (1 - k) + fondo_a[i] * k for i in range(3))
        luce = tuple(luce_d[i] * (1 - k) + luce_a[i] * k for i in range(3))
    else:
        fondo, luce = fondo_a, luce_a

    # ogni particella respira di luce propria, con il suo ritmo
    scintillio = np.sin(ora * _c['scint_freq'] * SCINTILLIO_VELOCITA
                        + _c['scint_fase']) * SCINTILLIO

    # cio' che e' piu' vicino all'osservatore schiarisce: e' quello che fa
    # leggere il volume invece di una sagoma piatta
    z = pos[:, 2]
    ampiezza_z = float(z.max() - z.min())
    profondita = ((z - z.min()) / ampiezza_z - 0.5) * PROFONDITA_COLORE if ampiezza_z > 1e-5 else 0.0

    t = np.clip(_c['tono'] + scintillio + profondita, 0.0, 1.0)[:, None]

    fondo = np.array(fondo, dtype='float32')
    luce = np.array(luce, dtype='float32')
    return fondo + (luce - fondo) * t


def _fuga(pos, bersaglio, P, ora):
    """Il passo di posizione durante la dissoluzione.

    Ogni particella continua a inseguire il proprio posto nel mandala — che
    intanto ruota e galleggia come sempre — con la propria inerzia. Ma se il
    naso le passa vicino riceve una spinta, e quella spinta la libera: piu' e'
    veloce, meno insegue e piu' vola per conto suo.

    La liberazione non e' un interruttore ma una misura: si ricava dalla
    velocita' che la particella si porta dietro. Chi ha preso una botta piena
    e' libero del tutto, chi e' stato sfiorato insegue ancora un po'. E' questo
    che fa disperdere la nuvola a pezzi irregolari invece che tutta insieme."""
    fuga = _c.get('fuga')
    if fuga is None or fuga.shape != pos.shape:
        fuga = np.zeros_like(pos)

    precedente = _c.get('t_diss')
    dt = 0.016 if precedente is None else min(max(ora - precedente, 1.0 / 240), 0.1)
    _c['t_diss'] = ora

    # .copy(): P[NASO] e' una VISTA sulla memoria dell'array. Conservarla
    # significherebbe confrontare il naso con se stesso al fotogramma dopo.
    naso = np.array(P[NASO], dtype='float32')
    naso_prec = _c.get('naso_prec')
    _c['naso_prec'] = naso
    velocita_naso = 0.0 if naso_prec is None else float(np.linalg.norm(naso - naso_prec)) / dt
    velocita_naso = max(0.0, velocita_naso - SOGLIA_MOVIMENTO)

    if velocita_naso > 0.0:
        # la calamita: respinge solo dentro il suo raggio, e sempre meno man
        # mano che ci si allontana dal centro, fino ad annullarsi sul bordo
        d = pos - naso
        distanza = np.sqrt((d * d).sum(axis=1)) + 1e-5
        dentro = distanza < RAGGIO_NASO
        if dentro.any():
            vicinanza = 1.0 - distanza[dentro] / RAGGIO_NASO
            spinta = (FORZA_NASO * velocita_naso) * vicinanza * vicinanza
            direzione = d[dentro] / distanza[dentro, None]
            direzione[:, 2] *= SPINTA_Z      # la dispersione resta sul piano
            fuga[dentro] += direzione * spinta[:, None] * dt

    fuga *= ATTRITO_FUGA
    _c['fuga'] = fuga

    # Quanto una particella si e' staccata: 0 = insegue ancora il mandala,
    # 1 = se n'e' andata e non lo insegue piu'.
    #
    # Il valore puo' solo CRESCERE. E' la differenza fra un gesto che libera e
    # uno che sposta soltanto: senza il cricchetto la velocita' di fuga si
    # smorzava, la particella tornava sotto soglia e ricominciava a inseguire
    # il mandala — l'85% risultava liberato e non ne usciva una.
    adesso = np.clip(np.linalg.norm(fuga, axis=1) / VELOCITA_LIBERAZIONE, 0.0, 1.0)
    precedente_libera = _c.get('libera')
    if precedente_libera is None or precedente_libera.shape != adesso.shape:
        precedente_libera = np.zeros_like(adesso)
    libera = np.maximum(precedente_libera, adesso)
    _c['libera'] = libera
    libera = libera[:, None]

    return pos + (bersaglio - pos) * _c['inerzia'] * (1.0 - libera) + fuga * dt


def _stato_danza(ora):
    """Dice: da quale forma veniamo, verso quale andiamo, e a che punto siamo
    della transizione (0 = appena partiti, 1 = arrivati)."""
    if 'scena_a' not in _c:
        _c['scena_da'] = ('volto', '')
        _c['scena_a'] = ('volto', '')
        _c['t0'] = ora
        _c['durata'] = DURATA_TRANSIZIONE

    avanzamento = (ora - _c['t0']) / max(_c['durata'], 0.001)
    return _c['scena_da'], _c['scena_a'], min(max(avanzamento, 0.0), 1.0)


def onCook(scriptOp):
    scriptOp.clear()
    scriptOp.isTimeSlice = False

    dati = op('face_osc').numpyArray()
    if dati is None or dati.shape[0] < 3:
        return

    flat = dati[:, 0]
    n_punti = flat.shape[0] // 3
    if n_punti == 0:
        return

    # dalle coordinate dell'immagine allo spazio 3D di TouchDesigner.
    # La X e' invertita apposta: cosi' l'opera si comporta come uno specchio.
    P = np.stack([
        (0.5 - flat[0::3]) * ASPETTO * SCALA,
        (0.5 - flat[1::3]) * SCALA,
        -flat[2::3] * SCALA,
    ], axis=1)

    # la prima volta le particelle vengono ripartite per area usando questa
    # posa del volto: senza un volto vero non si possono misurare i triangoli
    if _c.get('n') != n_punti or not _c.get('per_area'):
        _prepara(n_punti, P)

    ora = absTime.seconds
    da_scena, a_scena, avanzamento = _stato_danza(ora)

    n_part = _c['pesi'].shape[0]
    a = _forma(a_scena, P, n_part, ora)
    fioritura = None

    if da_scena != a_scena and avanzamento < 1.0:
        da = _forma(da_scena, P, n_part, ora, sorgente=True)

        # ogni particella ha il suo ritardo: la transizione attraversa la
        # forma come un'onda invece di spostare tutto in blocco
        locale = np.clip(avanzamento * (1.0 + RITARDO_MAX) - _c['ritardi'], 0.0, 1.0)
        # partenza e arrivo morbidi, niente scatti
        k = locale * locale * (3.0 - 2.0 * locale)

        bersaglio = da * (1.0 - k) + a * k
        fioritura = np.sin(np.pi * k)
    else:
        bersaglio = a

    estensione = float(np.max(a.max(axis=0) - a.min(axis=0)))

    # a meta' viaggio le particelle si allargano un po', invece di andare
    # dritte da una forma all'altra
    if fioritura is not None:
        bersaglio = bersaglio + _c['direzioni'] * fioritura * (ESPANSIONE * estensione)

    # le particelle "nebbia" restano sospese intorno alla forma, ma sul
    # mandala si tengono molto piu' vicine: e' l'unica forma che deve
    # leggersi come un disegno preciso
    alone = NEBBIA_RAGGIO * estensione
    if a_scena[0] == 'mandala':
        alone *= MANDALA_NEBBIA
    bersaglio = bersaglio + _c['nebbia'] * alone

    # nessuna particella e' mai davvero ferma (movimento individuale)
    bersaglio = bersaglio + _c['ampiezze'] * np.sin(
        ora * _c['frequenze'] + _c['fasi'])

    # corrente comune: dipende dalla posizione, quindi zone vicine si
    # muovono insieme e le forme galleggiano intere
    px = bersaglio[:, 0] * CORRENTE_SCALA
    py = bersaglio[:, 1] * CORRENTE_SCALA
    tt = ora * CORRENTE_VELOCITA
    corrente = np.empty_like(bersaglio)
    corrente[:, 0] = np.sin(py + tt) * np.cos(px * 0.6 + tt * 1.3)
    corrente[:, 1] = np.sin(px + tt * 1.1) * np.cos(py * 0.6 + tt * 0.9)
    corrente[:, 2] = np.sin(px * 0.8 + tt * 0.8) * np.cos(py * 0.8 + tt * 1.2)
    bersaglio = bersaglio + corrente * CORRENTE_AMPIEZZA

    # ogni particella insegue il proprio bersaglio con la sua pigrizia:
    # da qui la scia quando qualcosa si muove in fretta
    pos = _c['posizioni']
    if pos is None or pos.shape != bersaglio.shape:
        pos = bersaglio.copy()
    elif a_scena[0] == 'dissoluzione':
        pos = _fuga(pos, bersaglio, P, ora)
    else:
        pos += (bersaglio - pos) * _c['inerzia']
    _c['posizioni'] = pos

    colore = _colori(da_scena[0], a_scena[0], avanzamento, pos, ora)

    scriptOp.numSamples = pos.shape[0]
    scriptOp.appendChan('tx').vals = pos[:, 0]
    scriptOp.appendChan('ty').vals = pos[:, 1]
    scriptOp.appendChan('tz').vals = pos[:, 2]
    scriptOp.appendChan('r').vals = colore[:, 0]
    scriptOp.appendChan('g').vals = colore[:, 1]
    scriptOp.appendChan('b').vals = colore[:, 2]

    return
