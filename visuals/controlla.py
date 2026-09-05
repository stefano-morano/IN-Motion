"""
Controlla che tutto sia a posto PRIMA di lanciare l'esperienza.

Serve a chi prova il sistema per la prima volta su un altro computer: invece
di scoprire i problemi uno alla volta durante una sessione, li elenca tutti
subito, ognuno con la sua soluzione.

    python3 controlla.py

Chiede da solo i permessi di telecamera e microfono, che e' esattamente il
motivo per cui conviene lanciarlo in anticipo e non davanti a un pubblico:
la prima volta macOS mostra una richiesta, e finche' non si risponde il
programma non vede nulla.
"""

import importlib
import os
import subprocess
import sys

CARTELLA = os.path.dirname(os.path.abspath(__file__))

# modulo da importare -> (nome del pacchetto da installare, a cosa serve)
PACCHETTI = {
    "mediapipe": ("mediapipe", "riconoscere il volto"),
    "cv2": ("opencv-python", "leggere la webcam"),
    "numpy": ("numpy", "calcolare le posizioni delle particelle"),
    "pythonosc": ("python-osc", "parlare con TouchDesigner"),
    "anthropic": ("anthropic", "generare le frasi"),
    "faster_whisper": ("faster-whisper", "trascrivere la voce"),
    "sounddevice": ("sounddevice", "registrare dal microfono"),
    "PIL": ("pillow", "salvare il mandala come immagine"),
}

FILE_NECESSARI = {
    "face_landmarker.task": "il modello che riconosce il volto",
    "face_triangoli.txt": "la maglia di triangoli del viso",
    "visual_TD.toe": "il progetto TouchDesigner",
}

esiti = []


def esito(ok, titolo, dettaglio="", rimedio="", grave=True):
    esiti.append((ok, grave))
    segno = "  ok  " if ok else (" MANCA" if grave else " nota ")
    print(f"[{segno}] {titolo}")
    if dettaglio:
        print(f"          {dettaglio}")
    if not ok and rimedio:
        for riga in rimedio.split("\n"):
            print(f"          → {riga}")


def controlla_python():
    v = sys.version_info
    ok = v >= (3, 9)
    esito(ok, f"Python {v.major}.{v.minor}.{v.micro}",
          rimedio="serve Python 3.9 o superiore")


def controlla_pacchetti():
    mancanti = []
    for modulo, (pacchetto, uso) in PACCHETTI.items():
        try:
            importlib.import_module(modulo)
        except Exception:
            mancanti.append((pacchetto, uso))
    if mancanti:
        elenco = ", ".join(p for p, _ in mancanti)
        esito(False, f"Librerie mancanti: {elenco}",
              rimedio="pip3 install -r requirements.txt")
        for pacchetto, uso in mancanti:
            print(f"            {pacchetto}: serve per {uso}")
    else:
        esito(True, f"Tutte le {len(PACCHETTI)} librerie sono installate")


def controlla_file():
    for nome, descrizione in FILE_NECESSARI.items():
        percorso = os.path.join(CARTELLA, nome)
        presente = os.path.exists(percorso)
        esito(presente, f"{nome} ({descrizione})",
              rimedio="manca dal progetto: rifai 'git pull'")


def controlla_telecamera():
    try:
        import cv2
    except Exception:
        esito(False, "Telecamera", "impossibile provare: manca opencv-python")
        return

    trovata = None
    for indice in range(4):
        cap = cv2.VideoCapture(indice)
        aperta = cap.isOpened()
        letto = False
        if aperta:
            letto, _ = cap.read()
        cap.release()
        if letto:
            trovata = indice
            break

    esito(
        trovata is not None,
        "Telecamera",
        f"funziona (indice {trovata})" if trovata is not None else "nessuna telecamera leggibile",
        rimedio=("macOS chiede il permesso al primo accesso. Se non l'ha chiesto o hai\n"
                 "risposto no: Impostazioni di Sistema → Privacy e sicurezza → Fotocamera,\n"
                 "e attiva il programma da cui lanci lo script (Terminale, VS Code...).\n"
                 "Dopo averlo attivato il programma va CHIUSO E RIAPERTO."),
    )


def controlla_microfono():
    try:
        import sounddevice as sd
    except Exception:
        esito(False, "Microfono", "impossibile provare: manca sounddevice")
        return
    try:
        with sd.InputStream(samplerate=16000, channels=1, dtype="float32"):
            pass
        esito(True, "Microfono", "funziona")
    except Exception as errore:
        esito(
            False, "Microfono", str(errore)[:80],
            rimedio=("Impostazioni di Sistema → Privacy e sicurezza → Microfono,\n"
                     "attiva il programma da cui lanci lo script, poi chiudilo e riaprilo."),
        )


def controlla_modello_whisper():
    cache = os.path.expanduser("~/.cache/huggingface/hub")
    scaricato = os.path.isdir(cache) and any(
        "faster-whisper" in d for d in os.listdir(cache)
    )
    esito(
        scaricato, "Modello di trascrizione (Whisper)",
        "gia' scaricato" if scaricato else "non ancora scaricato",
        rimedio=("verra' scaricato da solo al primo avvio: circa 460 MB.\n"
                 "Fallo ORA con una buona connessione, non poco prima di una prova:\n"
                 "python3 -c \"from faster_whisper import WhisperModel; "
                 "WhisperModel('small', device='cpu', compute_type='int8')\""),
        grave=False,
    )


def controlla_chiave():
    presente = bool(os.environ.get("ANTHROPIC_API_KEY", "").strip())
    esito(
        presente, "Chiave API di Claude",
        "impostata" if presente else "assente",
        rimedio=("Senza chiave il sistema FUNZIONA LO STESSO: usa frasi di riserva\n"
                 "scritte a mano. Serve solo per generare frasi sul racconto vero.\n"
                 "Per impostarla:  export ANTHROPIC_API_KEY=\"...\"  nel terminale,\n"
                 "oppure la stessa riga in fondo a ~/.zshrc (poi apri un terminale nuovo).\n"
                 "MAI dentro un file del progetto: finirebbe su git."),
        grave=False,
    )


def controlla_voce():
    """La voce che legge le scritte. Tutto qui dentro e' facoltativo: senza,
    l'esperienza gira muta esattamente come gira con le frasi di riserva.

    Non controlla "la chiave di ElevenLabs": chiede al modulo quale fornitore
    ha scelto e se e' in piedi. Cosi' vale anche per Polly, e per il prossimo
    che si aggiungera'."""
    try:
        import voce as modulo_voce
        import prepara_voce
    except Exception as errore:
        esito(False, "Voce", str(errore)[:80],
              rimedio="pip3 install -r requirements.txt", grave=False)
        return

    try:
        importlib.import_module("soundfile")
    except Exception:
        esito(False, "Voce: qualita' audio", "manca soundfile",
              rimedio=("Senza soundfile la voce si scarica a 16 kHz invece che a\n"
                       "44.1 (ElevenLabs) o 24 (Polly), e si sente.\n"
                       "pip3 install soundfile"),
              grave=False)

    guida = modulo_voce.Voce()
    fornitore = guida.fornitore
    quale = fornitore.nome_motore

    if not fornitore.attivo:
        esito(
            False, f"Voce ({quale})", fornitore.motivo,
            rimedio=("Senza, l'esperienza FUNZIONA LO STESSO: le scritte restano mute.\n"
                     "Per darle voce ci sono due strade, e si scelgono con VOCE_MOTORE:\n"
                     "  elevenlabs  piu' calda; le voci italiane pero' stanno nella\n"
                     "              libreria pubblica, che il piano gratuito non usa\n"
                     "  polly       voci italiane di serie e quota molto piu' larga,\n"
                     "              ma audio a 24 kHz\n"
                     "Poi:  python3 voci.py  per scegliere chi legge.\n"
                     "Le chiavi vanno in ~/.zshrc, MAI in un file del progetto."),
            grave=False,
        )
        return

    dettaglio = getattr(fornitore, "motore", None) or modulo_voce.MODELLO
    esito(True, f"Voce ({quale})", f"legge {fornitore.voce_nome} — {dettaglio}")

    scritte = prepara_voce.tutte_le_scritte()
    mancanti = [t for t in scritte if not guida.pronta(t)]
    esito(
        not mancanti, "Voce: scritte fisse gia' sintetizzate",
        "tutte in cache" if not mancanti
        else f"ne mancano {len(mancanti)} su {len(scritte)}",
        rimedio=("python3 prepara_voce.py\n"
                 "Falle ORA, non poco prima di una prova: sintetizzarle durante la\n"
                 "sessione costerebbe crediti ad ogni giro e lascerebbe mute le\n"
                 "scritte che non fanno in tempo."),
        grave=False,
    )


def controlla_touchdesigner():
    try:
        elenco = subprocess.run(
            ["pgrep", "-f", "MacOS/TouchDesigner"], capture_output=True, text=True, timeout=10
        ).stdout.split()
    except Exception:
        elenco = []

    if len(elenco) == 1:
        esito(True, "TouchDesigner", "una sola istanza aperta, come dev'essere")
    elif len(elenco) == 0:
        esito(False, "TouchDesigner", "non e' aperto",
              rimedio="apri visual_TD.toe e lascialo in PRIMO PIANO durante la sessione",
              grave=False)
    else:
        esito(False, "TouchDesigner", f"{len(elenco)} istanze aperte",
              rimedio=("Chiudile TUTTE e riapri solo visual_TD.toe.\n"
                       "La prima istanza si prende le porte OSC e le altre non\n"
                       "ricevono piu' nulla: i nodi vanno in errore e sembra tutto rotto."))


def controlla_taratura():
    esito(True, "Soglia degli occhi", "da verificare a mano",
          rimedio="", grave=False)
    print("          La soglia in occhi.py e' stata misurata sul viso e sulla luce")
    print("          di chi ha scritto il progetto. Su un'altra persona puo' essere")
    print("          sbagliata: lancia  python3 taratura.py  e copia il valore.")


def main():
    print("\nCONTROLLO DEL SISTEMA IN-MOTION\n" + "=" * 60)
    controlla_python()
    controlla_pacchetti()
    controlla_file()
    controlla_telecamera()
    controlla_microfono()
    controlla_modello_whisper()
    controlla_chiave()
    controlla_voce()
    controlla_touchdesigner()
    controlla_taratura()

    gravi = [ok for ok, grave in esiti if grave and not ok]
    print("=" * 60)
    if gravi:
        print(f"\n{len(gravi)} problemi da risolvere prima di provare il sistema.\n")
        return 1
    print("\nTutto a posto. Puoi lanciare:")
    print('  python3 main.py "oggi mi sento agitato"\n')
    return 0


if __name__ == "__main__":
    sys.exit(main())
