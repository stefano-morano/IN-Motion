"""
Costruisce dentro TouchDesigner tutta la resa grafica: colore per particella,
fusione additiva e la catena di post-produzione (bagliore, sfondo, vignetta,
grana). Lo sfondo e' in due pezzi — la forma dell'alone e la sua tinta, che
segue il colore della sessione.

DA ESEGUIRE UNA VOLTA, dentro TD, in una Textport o da un DAT:

    # encoding esplicito: senza, il Python dentro TD apre in ascii e si ferma
    # sul primo trattino lungo o accento di questo file
    exec(open('/percorso/di/visuals/td_estetica.py', encoding='utf-8').read())

Perche' esiste come script invece che come nodi cliccati a mano:
  - il .toe e' binario, quindi queste scelte sarebbero invisibili a git;
  - se il progetto si perde o si corrompe, la resa si ricostruisce in un
    colpo solo invece che a memoria;
  - e' idempotente: rieseguirlo non duplica nulla, rimette solo tutto a posto.

NOTA: non tocca la logica delle particelle, che vive in
face_points_callbacks (copia di riferimento in td_face_points.py).
"""

RIS_W, RIS_H = 1280, 720
PASSO = 200          # spaziatura fra i nodi nella rete
BASE = '/project1'


def _nodo(padre, tipo, nome, x, y):
    """Crea il nodo se manca, altrimenti riusa quello che c'e'. Serve a poter
    rieseguire lo script senza riempire la rete di copie."""
    n = padre.op(nome)
    if n is None or n.type != tipo.__name__.replace('TOP', 'TOP'):
        if n is not None:
            n.destroy()
        n = padre.create(tipo, nome)
    n.nodeX, n.nodeY = x, y
    return n


def _parametri_colore(n):
    """I tre parametri r, g, b di un nodo, cercati invece che dati per buoni.

    I nomi dei parametri di TouchDesigner cambiano da un tipo di nodo
    all'altro, e sbagliarli qui vorrebbe dire un AttributeError in mezzo alla
    costruzione, con la rete lasciata a meta'. Meglio guardare cosa c'e'
    davvero e, se non c'e', dirlo in chiaro alla fine."""
    for nomi in (('colorr', 'colorg', 'colorb'), ('color0', 'color1', 'color2'),
                 ('cropr', 'cropg', 'cropb')):
        if all(hasattr(n.par, x) for x in nomi):
            return [getattr(n.par, x) for x in nomi]
    raise AttributeError(
        "%s: nessun parametro colore riconosciuto fra %s"
        % (n.name, [x for x in dir(n.par) if 'color' in x.lower()]))


def _risoluzione(n):
    n.par.outputresolution = 'custom'
    n.par.resolutionw, n.par.resolutionh = RIS_W, RIS_H


def costruisci():
    p = op(BASE)
    render = p.op('face_render')
    geo = p.op('face_geo')
    mat = p.op('face_mat')
    punti = p.op('face_points')
    x0, y0 = render.nodeX, render.nodeY

    # ------------------------------------------------------------------
    # 1. COLORE PER PARTICELLA
    # Il colore non e' piu' un valore unico sul materiale: ogni particella
    # ha il suo, calcolato in face_points e letto da qui. E' cio' che da'
    # profondita' — la nebbia sprofonda nel blu scuro, la forma viene avanti.
    # ------------------------------------------------------------------
    geo.par.instancecolorop = punti
    geo.par.instancer, geo.par.instanceg, geo.par.instanceb = 'r', 'g', 'b'
    geo.par.instancecolormode = 'replace'
    mat.par.colorr = mat.par.colorg = mat.par.colorb = 1.0

    # ------------------------------------------------------------------
    # 2. FUSIONE ADDITIVA
    # Dove due particelle si sovrappongono la luce si somma, come polvere
    # illuminata. Senza depth test/writing, altrimenti le particelle si
    # nasconderebbero a vicenda invece di sommarsi.
    # ------------------------------------------------------------------
    mat.par.blending = True
    mat.par.blendop = 'add'
    mat.par.srcblend = 'one'
    mat.par.destblend = 'one'
    mat.par.depthtest = False
    mat.par.depthwriting = False

    # ------------------------------------------------------------------
    # 3. CATENA DI POST-PRODUZIONE
    #    render -> bagliore -> (+ sfondo x sfondo_tinta)
    #           -> (x vignetta) -> (+ grana) -> finale
    # ------------------------------------------------------------------
    sfondo = _nodo(p, rampTOP, 'sfondo', x0 + PASSO, y0 - 180)
    sfondo_tinta = _nodo(p, constantTOP, 'sfondo_tinta', x0 + PASSO, y0 - 340)
    sfondo_col = _nodo(p, compositeTOP, 'sfondo_col', x0 + PASSO * 2, y0 - 180)
    bagliore = _nodo(p, bloomTOP, 'bagliore', x0 + PASSO, y0)
    composito = _nodo(p, compositeTOP, 'composito', x0 + PASSO * 2, y0)
    vign_map = _nodo(p, rampTOP, 'vignetta_mappa', x0 + PASSO * 2, y0 - 180)
    vignetta = _nodo(p, compositeTOP, 'vignetta', x0 + PASSO * 3, y0)
    grana = _nodo(p, noiseTOP, 'grana', x0 + PASSO * 3, y0 - 180)
    grana_mix = _nodo(p, compositeTOP, 'grana_mix', x0 + PASSO * 4, y0)
    finale = _nodo(p, nullTOP, 'finale', x0 + PASSO * 5, y0)

    # --- sfondo: non nero piatto ma un alone profondo, appena piu' chiaro al
    # centro. Il nero assoluto fa sembrare l'immagine spenta; un gradiente al
    # limite del percettibile da' aria e stacca le particelle.
    # ATTENZIONE: in TD 'radial' e' un gradiente ANGOLARE (a spicchi, come un
    # radar); quello concentrico si chiama 'circular'.
    #
    # Il gradiente qui e' BIANCO: porta solo la forma dell'alone, il colore
    # arriva dopo (sfondo_tinta). Erano una cosa sola finche' il fondo e' stato
    # blu per sempre; da quando segue la tinta di chi medita vanno separati,
    # perche' una tabella di chiavi non si puo' riscrivere ad ogni fotogramma
    # ma un parametro con un'espressione si rivaluta da solo.
    sfondo.par.type = 'circular'
    sfondo.par.extendleft = 'hold'      # 'repeat' disegnerebbe un bordo netto
    sfondo.par.extendright = 'hold'
    sfondo.par.fitaspect = 'fill'
    sfondo.par.outputaspect = 'resolution'
    _risoluzione(sfondo)
    tab = p.op('sfondo_keys')
    tab.clear()
    tab.appendRow(['pos', 'r', 'g', 'b', 'a'])
    tab.appendRow(['0', '1', '1', '1', '1'])
    tab.appendRow(['1', '0.188', '0.188', '0.188', '1'])   # SFONDO_QUOTA_BORDO

    # --- tinta dell'alone: un colore piatto, che pero' si muove. I tre canali
    # sono tre parametri distinti, ognuno con la sua espressione, e ognuna
    # nomina absTime.seconds NEL TESTO: e' l'unico modo perche' TD si accorga
    # che il valore dipende dal tempo e lo rivaluti (vedi luminosita() in
    # td_face_points.py, dove non farlo aveva fatto sparire la dissolvenza).
    _risoluzione(sfondo_tinta)
    canali = _parametri_colore(sfondo_tinta)
    for i, par in enumerate(canali):
        par.expr = ("op('face_points_callbacks').module"
                    ".sfondo_colore(%d, absTime.seconds)" % i)
    sfondo_col.inputConnectors[0].connect(sfondo)
    sfondo_col.inputConnectors[1].connect(sfondo_tinta)
    sfondo_col.par.operand = 'multiply'

    # --- bagliore: il pezzo che trasforma dei puntini in luce. Soglia alta e
    # intensita' contenuta: deve sembrare polvere illuminata, non un neon.
    bagliore.inputConnectors[0].connect(render)
    bagliore.par.bloomthreshold = 0.28
    bagliore.par.bloomintensity = 0.85
    bagliore.par.minbloomradius = 0.10
    bagliore.par.maxbloomradius = 0.62
    bagliore.par.bloomscurve = 1.6

    # --- composito: la luce si SOMMA allo sfondo. Le particelle sono luce,
    # non oggetti opachi che lo coprirebbero.
    composito.inputConnectors[0].connect(bagliore)
    composito.inputConnectors[1].connect(sfondo_col)
    composito.par.operand = 'add'

    # --- vignetta: bordi appena piu' scuri, lo sguardo va al centro
    vign_map.par.type = 'circular'
    vign_map.par.extendleft = 'hold'
    vign_map.par.extendright = 'hold'
    vign_map.par.fitaspect = 'fill'
    vign_map.par.outputaspect = 'resolution'
    _risoluzione(vign_map)
    tv = p.op('vignetta_mappa_keys')
    tv.clear()
    tv.appendRow(['pos', 'r', 'g', 'b', 'a'])
    tv.appendRow(['0', '1', '1', '1', '1'])
    tv.appendRow(['0.55', '0.97', '0.97', '0.97', '1'])
    tv.appendRow(['1', '0.55', '0.58', '0.68', '1'])
    vignetta.inputConnectors[0].connect(composito)
    vignetta.inputConnectors[1].connect(vign_map)
    vignetta.par.operand = 'multiply'

    # --- grana: pochissima, ma toglie la sensazione di "digitale pulito".
    # Il seme cambia ad ogni fotogramma: ferma sembrerebbe sporco sul vetro.
    _risoluzione(grana)
    grana.par.type = 'random'
    grana.par.mono = True
    grana.par.amp = 0.010
    grana.par.offset = 0.0
    grana.par.seed.expr = 'absTime.frame % 4096'
    grana_mix.inputConnectors[0].connect(vignetta)
    grana_mix.inputConnectors[1].connect(grana)
    grana_mix.par.operand = 'add'

    finale.inputConnectors[0].connect(grana_mix)

    # 'finale' e' il nodo da guardare: e' l'immagine completa.
    finale.viewer = True
    render.viewer = False

    nodi = (sfondo, sfondo_tinta, sfondo_col, bagliore, composito, vign_map,
            vignetta, grana, grana_mix, finale)
    errori = {n.name: n.errors() for n in nodi if n.errors()}
    return "resa costruita. errori: %s" % (errori or 'nessuno')


# Questo file e' fatto per essere eseguito con exec() dentro TouchDesigner,
# non importato: la costruzione parte da sola.
print(costruisci())
