"""
Rimette dentro TouchDesigner tutto cio' che vive nei file di questa cartella:
il motore delle particelle e la resa grafica. Poi salva.

DA ESEGUIRE dentro TD (Textport, oppure un Text DAT con tasto destro > Run):

    # encoding esplicito: senza, il Python dentro TD apre in ascii e si ferma
    # sul primo trattino lungo o accento di questo file
    exec(open('/percorso/di/visuals/td_ripristina.py', encoding='utf-8').read())

Serve dopo aver riaperto visual_TD.toe, o ogni volta che si modificano
td_face_points.py / td_controllo_osc.py / td_estetica.py fuori da TD.

E' sicuro rieseguirlo: non duplica nodi, rimette solo tutto a posto.
"""

import os

CARTELLA = os.path.dirname(os.path.abspath(__file__)) if '__file__' in dir() else project.folder


def _carica(nome_file, percorso_nodo):
    """Copia il contenuto di un file dentro un DAT di TouchDesigner."""
    # encoding esplicito: senza, Python dentro TD puo' aprire in ascii invece
    # che utf-8 (dipende dalla macchina), e questi file hanno caratteri come
    # '—' e le lettere accentate che in ascii non esistono.
    with open(os.path.join(CARTELLA, nome_file), encoding='utf-8') as f:
        testo = f.read()
    # la copia di riferimento porta un'intestazione che spiega cos'e':
    # va tolta, dentro TD sarebbe solo rumore
    if testo.startswith('# COPIA DI RIFERIMENTO'):
        righe = testo.split('\n')
        for i, riga in enumerate(righe):
            if riga.strip() == '' and i > 3:
                testo = '\n'.join(righe[i + 1:])
                break
    op(percorso_nodo).text = testo
    return "%s -> %s" % (nome_file, percorso_nodo)


def ripristina():
    passi = []

    # 1. il motore: dove sta ogni particella e di che colore
    passi.append(_carica('td_face_points.py', '/project1/face_points_callbacks'))

    # 2. il ricevitore dei comandi da Python
    passi.append(_carica('td_controllo_osc.py', '/project1/controllo_osc_callbacks'))

    # 3. la resa grafica: colore per istanza, fusione additiva, post-produzione
    with open(os.path.join(CARTELLA, 'td_estetica.py'), encoding='utf-8') as f:
        exec(f.read(), {'__file__': os.path.join(CARTELLA, 'td_estetica.py')})
    passi.append('td_estetica.py -> nodi della resa')

    # 4. un giro di cottura per far comparire tutto
    for nome in ('face_points', 'face_geo', 'face_render', 'sfondo', 'bagliore',
                 'composito', 'vignetta_mappa', 'vignetta', 'grana', 'grana_mix', 'finale'):
        nodo = op('/project1/' + nome)
        if nodo:
            nodo.cook(force=True)

    errori = {}
    for nome in ('face_points', 'face_render', 'bagliore', 'composito', 'vignetta', 'finale'):
        nodo = op('/project1/' + nome)
        if nodo and nodo.errors():
            errori[nome] = nodo.errors()

    # 5. e SALVA: e' il passo che l'ultima volta e' rimasto a meta'
    project.save(os.path.join(CARTELLA, 'visual_TD.toe'))
    passi.append('progetto salvato')

    return "\n".join(passi) + ("\nERRORI: %s" % errori if errori else "\nnessun errore")


print(ripristina())
