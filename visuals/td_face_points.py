# COPIA DI RIFERIMENTO — l'originale vive dentro visual_TD.toe
# (nodo /project1/face_points_callbacks).
#
# Serve perche' il .toe e' binario: senza questa copia le modifiche alla
# logica di TouchDesigner sarebbero invisibili a git e irrecuperabili se
# il progetto si corrompesse. Modificare QUI non cambia nulla: va
# ricaricata dentro TD.

# Decide dove deve stare ogni particella, fotogramma per fotogramma.
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
PER_TRIANGOLO = 16      # particelle dentro ogni triangolino della mesh

# ---------- scritte ----------
# Ingombro massimo concesso a una scritta: viene ridimensionata per starci
# dentro, qualunque sia la sua lunghezza, cosi' non esce mai dall'inquadratura.
TESTO_LARGHEZZA = 1.9
TESTO_ALTEZZA = 0.9

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
COLORE_DEFAULT = (0.62, 0.80, 0.95)   # blu tenue, il colore di volto e testo

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


def _prepara(n):
    """Sorteggia, una volta sola, le caratteristiche fisse di ogni particella:
    dove sta dentro il suo triangolo, quanto e' pigra, se e' nebbia, come
    oscilla, in che direzione fiorisce."""
    percorso = os.path.join(project.folder, 'face_triangoli.txt')
    triangoli = np.loadtxt(percorso, dtype=np.int64, comments='#')

    rng = np.random.default_rng(7)

    # posizione casuale dentro ogni triangolo (coordinate baricentriche)
    r = rng.random((triangoli.shape[0] * PER_TRIANGOLO, 2))
    fuori = r.sum(axis=1) > 1.0
    r[fuori] = 1.0 - r[fuori]
    pesi = np.column_stack([1.0 - r[:, 0] - r[:, 1], r[:, 0], r[:, 1]]).astype('float32')

    idx = np.repeat(triangoli, PER_TRIANGOLO, axis=0)
    n_part = pesi.shape[0]

    _c['a'], _c['b'], _c['c'] = idx[:, 0], idx[:, 1], idx[:, 2]
    _c['pesi'] = pesi

    _c['inerzia'] = rng.uniform(
        INERZIA_MIN, INERZIA_MAX, (n_part, 1)).astype('float32')

    e_nebbia = rng.random(n_part) < FRAZIONE_NEBBIA
    scostamento = rng.normal(0.0, 1.0, (n_part, 3)).astype('float32')
    scostamento[~e_nebbia] = 0.0
    _c['nebbia'] = scostamento

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

    _c['posizioni'] = None
    _c['n'] = n


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


def _genera_mandala(n, petali, anelli, seed):
    """Posizioni disposte in anelli concentrici, ciascuno modulato da 'petali'
    lobi piu' una seconda armonica che aggiunge merletto. Gli anelli alternati
    sono sfasati di mezzo petalo (i lobi si incastrano invece di allinearsi) e
    alcuni sono "a perline": le particelle si raccolgono in gruppi discreti
    invece di spalmarsi, ed e' quello che da' l'aria di mandala vero."""
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


def _riparti(n, gruppi):
    """n diviso in 'gruppi' parti il piu' uguali possibile."""
    base, resto = divmod(n, gruppi)
    return [base + (1 if i < resto else 0) for i in range(gruppi)]


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


def prepara_mandala(petali, anelli, tonalita, seed):
    """Genera e ricorda la forma del mandala. E' puro calcolo, ma resta
    comandata da fuori come prepara_testi() per lasciare a TD un fotogramma."""
    if 'pesi' not in _c:
        _prepara(478)
    n = _c['pesi'].shape[0]
    _c['mandala_tonalita'] = float(tonalita)
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
    petali, anelli, tonalita, seed = args
    return prepara_mandala(petali, anelli, tonalita, seed)


def vai_a(tipo, testo='', durata=None):
    """Fa partire la transizione verso una nuova forma.
    E' il comando che Python manda via OSC."""
    _c['scena_da'] = _c.get('scena_a', ('volto', ''))
    _c['scena_a'] = (tipo, testo)
    _c['t0'] = absTime.seconds
    _c['durata'] = DURATA_TRANSIZIONE if durata is None else float(durata)
    return _c['scena_a']


def _forma_volto(P):
    w = _c['pesi']
    return (P[_c['a']] * w[:, 0:1]
            + P[_c['b']] * w[:, 1:2]
            + P[_c['c']] * w[:, 2:3])


def _forma(scena, P, n, ora):
    """Le posizioni-bersaglio di una scena. Se una scritta o il mandala non
    sono stati preparati, ripiega sul volto invece di rompere l'animazione."""
    tipo = scena[0]
    if tipo == 'mandala':
        if _c.get('mandala_raggi') is None or _c['mandala_raggi'].shape[0] != n:
            return _forma_volto(P)
        return _forma_mandala(ora)
    if tipo == 'testo':
        pos = _c.get('testi', {}).get(scena[1])
        if pos is not None and pos.shape[0] == n:
            return pos
    return _forma_volto(P)


def _applica_colore(tipo):
    """Il mandala prende il colore scelto da Claude in base al tono del
    racconto; volto e testo restano sul blu tenue di sempre.
    Scrive i parametri solo quando cambiano davvero: assegnarli ad ogni
    fotogramma farebbe ricuocere il materiale per nulla."""
    if tipo == 'mandala' and 'mandala_tonalita' in _c:
        colore = colorsys.hsv_to_rgb(_c['mandala_tonalita'] / 360.0, 0.55, 0.95)
    else:
        colore = COLORE_DEFAULT

    if _c.get('colore') == colore:
        return
    _c['colore'] = colore

    mat = op('face_mat')
    mat.par.colorr, mat.par.colorg, mat.par.colorb = colore


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

    if _c.get('n') != n_punti:
        _prepara(n_punti)

    ora = absTime.seconds
    da_scena, a_scena, avanzamento = _stato_danza(ora)
    _applica_colore(a_scena[0])

    n_part = _c['pesi'].shape[0]
    a = _forma(a_scena, P, n_part, ora)
    fioritura = None

    if da_scena != a_scena and avanzamento < 1.0:
        da = _forma(da_scena, P, n_part, ora)

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
    else:
        pos += (bersaglio - pos) * _c['inerzia']
    _c['posizioni'] = pos

    scriptOp.numSamples = pos.shape[0]
    scriptOp.appendChan('tx').vals = pos[:, 0]
    scriptOp.appendChan('ty').vals = pos[:, 1]
    scriptOp.appendChan('tz').vals = pos[:, 2]

    return
