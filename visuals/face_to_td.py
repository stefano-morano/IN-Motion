"""
Cattura il volto con MediaPipe (come face_landmarks.py) e manda i 478 punti
a TouchDesigner via OSC, un unico messaggio per fotogramma su /face/landmarks
(x0,y0,z0, x1,y1,z1, ...). Tiene anche una finestra di anteprima per continuare
a vedere dal vivo che il rilevamento funziona.

Si ferma con 'q' nella finestra di anteprima o Ctrl+C nel terminale.
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

SCRIPT_DIR = Path(__file__).resolve().parent
MODEL_PATH = str(SCRIPT_DIR / "face_landmarker.task")
MAX_CAMERE_DA_PROVARE = 5
FRAME_DI_PROVA_PER_CAMERA = 20

TD_IP = "127.0.0.1"
TD_PORT = 8000
OSC_ADDRESS = "/face/landmarks"


def trova_camera_con_volto(model_path):
    """Prova le camere disponibili (indice 0,1,2...) finche' non trova un
    volto vero. Cosi' non serve sapere in anticipo quale indice corrisponde
    alla webcam giusta: si adatta a qualunque Mac, anche con OBS/iPhone
    collegati che spostano la numerazione."""
    probe_options = FaceLandmarkerOptions(
        base_options=BaseOptions(model_asset_path=model_path),
        running_mode=RunningMode.IMAGE,
        num_faces=1,
    )
    probe_landmarker = FaceLandmarker.create_from_options(probe_options)

    primo_indice_apribile = None
    trovato = None

    for index in range(MAX_CAMERE_DA_PROVARE):
        cap = cv2.VideoCapture(index)
        if not cap.isOpened():
            cap.release()
            continue
        if primo_indice_apribile is None:
            primo_indice_apribile = index

        print(f"Provo indice {index}...")
        for _ in range(FRAME_DI_PROVA_PER_CAMERA):
            ok, frame = cap.read()
            if not ok:
                time.sleep(0.03)
                continue
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
            result = probe_landmarker.detect(mp_image)
            if result.face_landmarks:
                trovato = index
                break

        if trovato is not None:
            cap.release()
            break
        cap.release()

    probe_landmarker.close()

    if trovato is not None:
        print(f"Volto rilevato sulla camera indice {trovato}, la uso.")
        return trovato
    if primo_indice_apribile is not None:
        print(
            f"Nessun volto rilevato durante la ricerca, uso la prima camera "
            f"disponibile (indice {primo_indice_apribile}) come ripiego."
        )
        return primo_indice_apribile
    return None


def main():
    camera_index = trova_camera_con_volto(MODEL_PATH)
    if camera_index is None:
        print("Nessuna webcam trovata sul sistema.")
        return

    options = FaceLandmarkerOptions(
        base_options=BaseOptions(model_asset_path=MODEL_PATH),
        running_mode=RunningMode.VIDEO,
        num_faces=1,
    )
    landmarker = FaceLandmarker.create_from_options(options)

    client = udp_client.SimpleUDPClient(TD_IP, TD_PORT)
    print(f"Invio a TouchDesigner su {TD_IP}:{TD_PORT}{OSC_ADDRESS}")

    cap = cv2.VideoCapture(camera_index)
    if not cap.isOpened():
        print(f"Impossibile aprire la webcam (indice {camera_index}).")
        return

    start = time.time()
    frame_count = 0
    sent_count = 0
    last_status_print = 0.0
    consecutive_failures = 0

    print("In esecuzione. Premi 'q' nella finestra di anteprima (o Ctrl+C qui) per fermarti.")

    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                consecutive_failures += 1
                if consecutive_failures > 60:
                    print("Troppi frame falliti di fila, interrompo.")
                    break
                time.sleep(0.05)
                continue
            consecutive_failures = 0
            frame_count += 1

            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
            timestamp_ms = int((time.time() - start) * 1000)
            result = landmarker.detect_for_video(mp_image, timestamp_ms)

            if result.face_landmarks:
                landmarks = result.face_landmarks[0]
                flat = []
                for lm in landmarks:
                    flat.extend([lm.x, lm.y, lm.z])
                client.send_message(OSC_ADDRESS, flat)
                sent_count += 1

                h, w, _ = frame.shape
                for lm in landmarks:
                    x, y = int(lm.x * w), int(lm.y * h)
                    cv2.circle(frame, (x, y), 1, (0, 255, 0), -1)

            now = time.time()
            if now - last_status_print > 1.0:
                fps = frame_count / (now - start)
                print(f"frame: {frame_count}  inviati: {sent_count}  fps~{fps:.1f}", end="\r")
                last_status_print = now

            cv2.imshow("Face to TD - premi 'q' per uscire", frame)
            if cv2.waitKey(1) & 0xFF == ord("q"):
                break
    except KeyboardInterrupt:
        pass
    finally:
        cap.release()
        cv2.destroyAllWindows()
        print(f"\nFermato. Frame totali: {frame_count}, messaggi OSC inviati: {sent_count}")


if __name__ == "__main__":
    main()
