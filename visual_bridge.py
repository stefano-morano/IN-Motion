import time
import math
from pythonosc import udp_client

class TouchDesignerBridge:
    def __init__(self, ip="127.0.0.1", port=8000):
        self.client = udp_client.SimpleUDPClient(ip, port)
        print(f"Connesso a TouchDesigner su {ip}:{port}")

    def send_emotion_coordinates(self, valence: float, arousal: float):
        """
        Invia le coordinate emotive normalizzate in scala [0.0, 1.0] a TouchDesigner.
        - valence: da -1.0 (molto negativo) a +1.0 (molto positivo)
        - arousal: da -1.0 (molto calmo) a +1.0 (molto agitato)
        """
        norm_valence = (valence + 1.0) / 2.0
        norm_arousal = (arousal + 1.0) / 2.0

        self.client.send_message("/emotion/valence", norm_valence)
        self.client.send_message("/emotion/arousal", norm_arousal)

    def test(self, speed=0.1, delay=0.1):
        """Genera e invia un flusso infinito di dati fittizi a TouchDesigner."""
        print("vvio modalità TEST (invio continuo a TouchDesigner)...")
        print("Premi Ctrl+C nel terminale per interrompere il test.\n")
        
        passo = 0
        try:
            while True:
                # Simula onde dinamiche sfalsate per Valence e Arousal
                v = math.sin(passo * speed)
                a = math.cos(passo * speed)
                
                self.send_emotion_coordinates(valence=v, arousal=a)
                
                print(f"Inviato -> Valence: {v:+.2f} | Arousal: {a:+.2f}", end="\r")
                
                passo += 1
                time.sleep(delay)  # Invia 10 aggiornamenti al secondo
                
        except KeyboardInterrupt:
            print("\n\n Test interrotto dall'utente.")


# ==========================================
# ESECUZIONE SCRIPT
# ==========================================
if __name__ == "__main__":
    bridge = TouchDesignerBridge()
    
    # Richiama la funzione di test continuo
    bridge.test()