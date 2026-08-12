"""
Il volto: apre la webcam, ne estrae i punti con MediaPipe e li manda a
TouchDesigner via OSC.

Non decide nulla — si limita a guardare e a riferire. Chi decide cosa
succede e' esperienza.py.
"""

import time
from pathlib import Path

import cv2
import mediapipe as mp
from mediapipe.tasks.python import BaseOptions
from mediapipe.tasks.python.vision import (
    FaceLandmarker,
    FaceLandmarkerOptions,
    RunningMode,
)
from pythonosc import udp_client

CARTELLA = Path(__file__).resolve().parent
MODELLO = str(CARTELLA / "face_landmarker.task")

TD_IP = "127.0.0.1"
PORTA_VOLTO = 8000
INDIRIZZO_OSC = "/face/landmarks"

MAX_CAMERE_DA_PROVARE = 5
FRAME_DI_PROVA_PER_CAMERA = 20


def trova_camera(percorso_modello):
    """Prova le camere disponibili finche' non trova un volto vero. Cosi' non
    serve sapere in anticipo quale indice sia quello giusto: si adatta a
    qualunque computer, anche con altre camere collegate."""
    opzioni = FaceLandmarkerOptions(
        base_options=BaseOptions(model_asset_path=percorso_modello),
        running_mode=RunningMode.IMAGE,
        num_faces=1,
    )
    rilevatore = FaceLandmarker.create_from_options(opzioni)

    primo_apribile = None
    trovata = None

    for indice in range(MAX_CAMERE_DA_PROVARE):
        cap = cv2.VideoCapture(indice)
        if not cap.isOpened():
            cap.release()
            continue
        if primo_apribile is None:
            primo_apribile = indice

        for _ in range(FRAME_DI_PROVA_PER_CAMERA):
            ok, fotogramma = cap.read()
            if not ok:
                time.sleep(0.03)
                continue
            rgb = cv2.cvtColor(fotogramma, cv2.COLOR_BGR2RGB)
            immagine = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
            if rilevatore.detect(immagine).face_landmarks:
                trovata = indice
                break

        cap.release()
        if trovata is not None:
            break

    rilevatore.close()

    if trovata is not None:
        print(f"volto: uso la camera {trovata}")
        return trovata
    if primo_apribile is not None:
        print(f"volto: nessun volto in fase di ricerca, uso la camera {primo_apribile}")
        return primo_apribile
    return None


class Volto:
    """Cattura la webcam e manda i punti del viso a TouchDesigner."""

    def __init__(self, anteprima=True):
        self.anteprima = anteprima
        self.client = udp_client.SimpleUDPClient(TD_IP, PORTA_VOLTO)

        indice = trova_camera(MODELLO)
        if indice is None:
            raise RuntimeError("nessuna webcam disponibile")

        self.cap = cv2.VideoCapture(indice)
        if not self.cap.isOpened():
            raise RuntimeError(f"impossibile aprire la camera {indice}")

        self.rilevatore = FaceLandmarker.create_from_options(
            FaceLandmarkerOptions(
                base_options=BaseOptions(model_asset_path=MODELLO),
                running_mode=RunningMode.VIDEO,
                num_faces=1,
            )
        )

        self.inizio = time.time()
        self.fallimenti = 0
        self.uscita = False

    def aggiorna(self):
        """Legge un fotogramma, manda i punti a TD e li restituisce.
        Ritorna None se in questo istante non si vede un volto."""
        ok, fotogramma = self.cap.read()
        if not ok:
            self.fallimenti += 1
            if self.fallimenti > 60:
                raise RuntimeError("la webcam ha smesso di rispondere")
            return None
        self.fallimenti = 0

        rgb = cv2.cvtColor(fotogramma, cv2.COLOR_BGR2RGB)
        immagine = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
        millisecondi = int((time.time() - self.inizio) * 1000)
        esito = self.rilevatore.detect_for_video(immagine, millisecondi)

        punti = None
        if esito.face_landmarks:
            punti = esito.face_landmarks[0]
            piatto = []
            for p in punti:
                piatto.extend([p.x, p.y, p.z])
            self.client.send_message(INDIRIZZO_OSC, piatto)

            if self.anteprima:
                h, w, _ = fotogramma.shape
                for p in punti:
                    cv2.circle(
                        fotogramma, (int(p.x * w), int(p.y * h)), 1, (0, 255, 0), -1
                    )

        if self.anteprima:
            cv2.imshow("IN-Motion — premi 'q' per uscire", fotogramma)
            if cv2.waitKey(1) & 0xFF == ord("q"):
                self.uscita = True

        return punti

    def uscita_richiesta(self):
        return self.uscita

    def chiudi(self):
        self.cap.release()
        if self.anteprima:
            cv2.destroyAllWindows()
