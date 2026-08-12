"""
La scena: manda a TouchDesigner i comandi su cosa mostrare.

Due soli messaggi, sulla porta 8001:
  /prepara  "frase" "frase" ...   -> TD disegna le scritte e ne ricava le posizioni
  /scena    tipo testo durata     -> TD parte con la transizione

Nessuna funzione qui aspetta: le attese sono compito della macchina a stati,
perche' un'attesa dentro questo modulo bloccherebbe anche la webcam.
"""

from pythonosc import udp_client

TD_IP = "127.0.0.1"
PORTA_CONTROLLO = 8001

# Quanto ci mette TD a disegnare le scritte e ricavarne le particelle.
# Chi comanda deve lasciar passare questo tempo prima di mostrarle.
TEMPO_DI_PREPARAZIONE = 0.6


class Scena:
    def __init__(self, ip=TD_IP, porta=PORTA_CONTROLLO):
        self.client = udp_client.SimpleUDPClient(ip, porta)
        print(f"scena: collegata a TouchDesigner su {ip}:{porta}")

    def prepara(self, frasi):
        """Chiede a TD di preparare in anticipo delle scritte. Da fare sempre
        prima di mostrarle: prepararle mentre le particelle si muovono le
        farebbe scattare."""
        frasi = [f for f in frasi if f]
        if not frasi:
            return
        self.client.send_message("/prepara", list(frasi))
        print(f"scena: preparo {len(frasi)} scritte")

    def volto(self, transizione=4.0):
        self.client.send_message("/scena", ["volto", "", float(transizione)])

    def testo(self, frase, transizione=4.0):
        self.client.send_message("/scena", ["testo", frase, float(transizione)])

    def mostra(self, tipo, contenuto="", transizione=4.0):
        if tipo == "volto":
            self.volto(transizione)
        else:
            self.testo(contenuto, transizione)
        print(f"  -> {contenuto or tipo}")
