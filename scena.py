"""
La scena: manda a TouchDesigner i comandi su cosa mostrare.

Quattro messaggi, sulla porta 8001:
  /prepara  "frase" "frase" ...        -> TD disegna le scritte e ne ricava le posizioni
  /mandala  petali anelli tonalita seed emozione -> TD genera le posizioni del mandala
  /scena    tipo testo durata          -> TD parte con la transizione
                                           (tipo = volto / testo / mandala /
                                            polvere / dissoluzione)
  /finestra 1|0                        -> apre o chiude la finestra a schermo intero
  /azzera                              -> riporta la scena all'inizio, senza transizione
  /buio  /accendi durata               -> schermo nero, e risalita dal nero

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

    def azzera(self):
        """Riporta TouchDesigner all'inizio, senza transizione.

        Da mandare per PRIMA cosa, prima ancora di aprire la finestra: TD
        resta acceso fra una sessione e l'altra e si ricorda l'ultima
        schermata di chi c'e' stato prima. Senza questo, chi rilancia il
        programma si trova davanti il "GRAZIE, A PRESTO" del commiato
        precedente per tutti i secondi che servono a caricare Whisper."""
        self.client.send_message("/azzera", [])
        print("scena: azzerata")

    def buio(self):
        """Spegne l'immagine: schermo nero. Ci resta finche' non si accende.

        Da chiamare PRIMA di aprire la finestra: cosi' il primo fotogramma
        che lo spettatore vede e' nero, non la scena gia' accesa."""
        self.client.send_message("/buio", [])

    def accendi(self, durata=4.0):
        """Fa salire l'immagine dal nero, in 'durata' secondi."""
        self.client.send_message("/accendi", [float(durata)])
        print(f"scena: accendo in {durata}s")

    def finestra(self, apri=True):
        """Apre (o chiude) la finestra di uscita a schermo intero.

        Non e' uno streaming: e' la stessa immagine che TouchDesigner sta gia'
        calcolando, mostrata senza l'editor intorno. Nessuna ricompressione,
        nessun ritardo aggiunto.

        Ha anche un effetto utile di sponda: con la finestra aperta TD e'
        l'applicazione in primo piano, che e' la condizione in cui il suo
        orologio va alla velocita' giusta. Prima bisognava ricordarsi di
        portarcelo a mano."""
        self.client.send_message("/finestra", [1 if apri else 0])
        print(f"scena: finestra {'aperta' if apri else 'chiusa'}")

    def prepara_mandala(self, petali, anelli, tonalita, seed, emozione="Q2"):
        """Come prepara(), ma per il mandala: niente da disegnare, solo
        numeri — TD lo genera per calcolo puro.

        L'emozione viaggia con gli altri parametri perche' e' lei a decidere
        quanto il colore si apre in gradiente (vedi GRADIENTE in mandala.py)."""
        self.client.send_message(
            "/mandala",
            [int(petali), int(anelli), float(tonalita), int(seed), str(emozione)],
        )
        print(f"scena: preparo il mandala ({petali} petali, {anelli} anelli, {emozione})")

    def polvere(self, transizione=0.0):
        """Le particelle sparse a caso: la nuvola dell'apertura.

        E' una forma come le altre, quindi ci si arriva e la si lascia con le
        stesse transizioni. Di norma la si mette senza transizione (a sipario
        chiuso) e la si lascia con una lunga: e' quel passaggio, dalla polvere
        alle prime parole, l'inizio vero dell'opera."""
        self.client.send_message("/scena", ["polvere", "", float(transizione)])

    def volto(self, transizione=4.0):
        self.client.send_message("/scena", ["volto", "", float(transizione)])

    def testo(self, frase, transizione=4.0):
        self.client.send_message("/scena", ["testo", frase, float(transizione)])

    def dissolvi(self, transizione=0.0):
        """Le particelle smettono di inseguire una forma e diventano materia
        che il naso dell'utente puo' colpire.

        Con una transizione, le particelle si ricompongono nel mandala mentre
        la dissoluzione e' GIA' attiva: si puo' spingerle via fin dal primo
        istante, invece di aspettare che la forma sia completa."""
        self.client.send_message("/scena", ["dissoluzione", "", float(transizione)])
        print("  -> dissoluzione")

    def mostra(self, tipo, contenuto="", transizione=4.0):
        if tipo == "volto":
            self.volto(transizione)
        elif tipo == "dissoluzione":
            self.dissolvi()
            return
        elif tipo == "polvere":
            self.polvere(transizione)
        elif tipo == "mandala":
            self.client.send_message("/scena", ["mandala", "", float(transizione)])
        else:
            self.testo(contenuto, transizione)
        print(f"  -> {contenuto or tipo}")
