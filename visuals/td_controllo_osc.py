# COPIA DI RIFERIMENTO — l'originale vive dentro visual_TD.toe
# (nodo /project1/controllo_osc_callbacks).
#
# Serve perche' il .toe e' binario: senza questa copia le modifiche alla
# logica di TouchDesigner sarebbero invisibili a git e irrecuperabili se
# il progetto si corrompesse. Modificare QUI non cambia nulla: va
# ricaricata dentro TD.

"""Riceve i comandi di regia da Python (porta 8001).

  /prepara  "frase 1"  "frase 2"  ...
      TD disegna le frasi e ne ricava le posizioni delle particelle.
      Va mandato una volta, prima di usarle.

  /mandala  petali  anelli  tonalita  seed  emozione
      TD genera le posizioni del mandala (calcolo puro, nessun disegno da
      campionare). Va mandato una volta, prima di mostrarlo. L'emozione
      ('Q1'..'Q4') decide quanto il colore si apre in gradiente.

  /tinta  tonalita  emozione
      La tinta personale ricavata dal racconto. Va mandata appena Claude ha
      risposto — molto prima del mandala — perche' da li' in poi comincia a
      entrare anche nelle scritte e nel volto. Da sola non cambia nulla: e'
      /tinta_forza a decidere quanta se ne veda.

  /tinta_forza  valore  durata
      Quanta tinta personale si vede, da 0 (il blu di sempre) a 1 (solo lei),
      raggiunta in 'durata' secondi. E' la regia del colore: Python la alza
      fase per fase, cosi' il mandala non e' piu' l'unico momento colorato.

  /scena  tipo  testo  durata
      Fa partire la transizione. tipo = 'volto', 'testo' oppure 'mandala'.

  /finestra  1|0
      Apre (1) o chiude (0) la finestra di uscita a schermo intero, cioe' il
      TOP finale mostrato senza l'editor intorno.

  /azzera
      Riporta la scena all'inizio, senza transizione. Lo manda main.py appena
      parte, perche' TD si ricorda l'ultima schermata della sessione prima.

  /buio
  /accendi  durata
      Schermo nero, e risalita dal nero in 'durata' secondi. E' la
      dissolvenza d'apertura: la finestra si apre gia' nera, poi l'immagine
      sale.

La preparazione non viene eseguita qui dentro ma rimandata di un fotogramma:
far cuocere un nodo dentro una callback e' il tipo di operazione che ha gia'
fatto crashare TouchDesigner una volta.
"""


def onReceiveOSC(dat, rowIndex, message, byteData, timeStamp, address, args, peer):
    regia = op('face_points_callbacks').module

    if address == '/prepara':
        regia._c['da_preparare'] = [str(a) for a in args]
        run("op('/project1/face_points_callbacks').module.prepara_in_coda()",
            delayFrames=1)

    elif address == '/mandala':
        # i primi quattro sono numeri, il quinto (l'emozione) e' una sigla:
        # convertire tutto a float come si faceva prima farebbe fallire su 'Q2'
        numeri = [float(a) for a in args[:4]]
        emozione = str(args[4]) if len(args) > 4 else 'Q2'
        regia._c['da_preparare_mandala'] = numeri + [emozione]
        run("op('/project1/face_points_callbacks').module.prepara_mandala_in_coda()",
            delayFrames=1)

    elif address == '/tinta':
        # niente da cuocere e niente da disegnare: e' solo un valore messo da
        # parte, quindi si puo' fare subito dentro la callback
        tonalita = float(args[0]) if args else 200.0
        emozione = str(args[1]) if len(args) > 1 else 'Q2'
        regia.tinta(tonalita, emozione)

    elif address == '/tinta_forza':
        valore = float(args[0]) if args else 0.0
        durata = float(args[1]) if len(args) > 1 else regia.DURATA_TINTA
        regia.tinta_forza(valore, durata)

    elif address == '/scena':
        # se qualcuno comanda da fuori, TD smette di scorrere da solo
        regia.AUTOMATICO = False
        tipo = str(args[0]) if len(args) > 0 else 'volto'
        testo = str(args[1]) if len(args) > 1 else ''
        durata = float(args[2]) if len(args) > 2 else None
        regia.vai_a(tipo, testo, durata)

    elif address == '/azzera':
        regia.AUTOMATICO = False
        regia.azzera()

    elif address == '/buio':
        regia.buio()

    elif address == '/accendi':
        if args:
            regia.accendi(float(args[0]))
        else:
            regia.accendi()

    elif address == '/finestra':
        # apre o chiude la finestra di uscita a schermo intero.
        # Come per /prepara: non si tocca una finestra dentro una callback,
        # si rimanda di un fotogramma.
        apri = bool(args[0]) if args else True
        comando = 'winopen' if apri else 'winclose'
        run("op('/perform').par.%s.pulse()" % comando, delayFrames=1)

    return
