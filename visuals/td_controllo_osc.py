# COPIA DI RIFERIMENTO — l'originale vive dentro visual_TD.toe
# (nodo /project1/controllo_osc_callbacks).
#
# Serve perche' il .toe e' binario: senza questa copia le modifiche alla
# logica di TouchDesigner sarebbero invisibili a git e irrecuperabili se
# il progetto si corrompesse. Modificare QUI non cambia nulla: va
# ricaricata dentro TD.

"""Riceve i comandi di regia da Python (porta 8001).

Tre messaggi:

  /prepara  "frase 1"  "frase 2"  ...
      TD disegna le frasi e ne ricava le posizioni delle particelle.
      Va mandato una volta, prima di usarle.

  /mandala  petali  anelli  tonalita  seed
      TD genera le posizioni del mandala (calcolo puro, nessun disegno da
      campionare). Va mandato una volta, prima di mostrarlo.

  /scena  tipo  testo  durata
      Fa partire la transizione. tipo = 'volto', 'testo' oppure 'mandala'.

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
        regia._c['da_preparare_mandala'] = [float(a) for a in args]
        run("op('/project1/face_points_callbacks').module.prepara_mandala_in_coda()",
            delayFrames=1)

    elif address == '/scena':
        # se qualcuno comanda da fuori, TD smette di scorrere da solo
        regia.AUTOMATICO = False
        tipo = str(args[0]) if len(args) > 0 else 'volto'
        testo = str(args[1]) if len(args) > 1 else ''
        durata = float(args[2]) if len(args) > 2 else None
        regia.vai_a(tipo, testo, durata)

    return
