# IN-Motion

Un'esperienza di meditazione guidata. L'utente racconta a voce cosa lo affligge,
Claude ne ricava delle frasi su cui meditare, e tutto — volto, parole, mandala
finale — viene disegnato dalle stesse 13.664 particelle.

**Non si tocca mai la tastiera**: l'esperienza si comanda chiudendo e riaprendo
gli occhi.

## Come si esegue

1. Apri `visual_TD.toe` in TouchDesigner e **lascialo in primo piano** — quando
   TD non e' la finestra attiva il suo orologio rallenta e le transizioni
   restano immobili. Assicurati che ci sia **una sola istanza di TD aperta**:
   una seconda si prende le porte OSC e la prima non riceve piu' nulla.
2. Lancia:

   ```bash
   python3 main.py "racconto di ripiego"
   ```

   Il testo fra virgolette serve solo se il microfono non e' disponibile o non
   sente nulla.
3. Passa a TouchDesigner entro il conto alla rovescia e segui le scritte.

Si ferma con `Ctrl+C`, o premendo `q` sulla finestra della webcam.

## Il filo dell'esperienza

| Fase | Cosa vedi | Come si passa oltre |
|---|---|---|
| Saluto e invito | benvenuto, poi l'invito a raccontare | **chiudi gli occhi** |
| Ascolto | il tuo volto | parli; **riapri gli occhi** |
| Attesa | "preparo la tua meditazione" | quando Claude ha risposto |
| Danza | frasi e volto che si alternano | a tempo |
| Meditazione | il tuo volto | **chiudi gli occhi**, mediti, **riapri** |
| Mandala | il mandala della tua sessione | dopo 40 secondi |

Gli occhi vanno tenuti chiusi (o aperti) **2 secondi** perche' il cambiamento
conti: sotto quella soglia e' un battito di ciglia, non una scelta.

## I file

| File | Cosa fa |
|---|---|
| `main.py` | avvia, tiene il ciclo, ferma tutto |
| `volto.py` | webcam e punti del viso → TD |
| `occhi.py` | da quanto sono aperti gli occhi a "aperti / chiusi" |
| `ascolto.py` | microfono e trascrizione (Whisper, in locale) |
| `testi.py` | frasi e carattere del mandala, da Claude |
| `scena.py` | i comandi verso TD |
| `esperienza.py` | **decide cosa succede e quando** |
| `taratura.py` | attrezzo: misura la soglia degli occhi sul tuo viso |
| `td_*.py` | copie di riferimento degli script che girano dentro TD |

`esperienza.py` e' il file da aprire per cambiare le scritte o i tempi: sono
tutte costanti in cima.

## Come e' fatto

**Python decide, TouchDesigner disegna.** Python manda tre soli messaggi OSC
sulla porta 8001 (`/prepara`, `/mandala`, `/scena`); i punti del viso viaggiano
a parte sulla 8000. TD non sa nulla dell'esperienza: sa solo come passare da
una forma all'altra.

**Niente blocca il ciclo.** `esperienza.py` non aspetta mai: ad ogni fotogramma
le si chiede "e adesso?". Le chiamate lente (Claude, Whisper) girano in thread
separati. E' la condizione perche' il sistema possa accorgersi degli occhi che
si chiudono mentre sta facendo altro.

**Funziona anche quando qualcosa si rompe.** Senza chiave API, senza rete,
senza microfono, l'esperienza va avanti con frasi di riserva scritte a mano.

**La privacy e' una scelta di progetto.** Il volto diventa coordinate e l'audio
viene trascritto in locale: a TouchDesigner non arriva mai il video, e l'audio
non lascia il computer. Esce solo il testo, e solo verso Claude.

## Prima volta

```bash
pip install -r requirements.txt
export ANTHROPIC_API_KEY="sk-ant-..."   # senza, si usano le frasi di riserva
python3 taratura.py                      # misura la soglia degli occhi
```

La chiave va nell'ambiente, **mai in un file del progetto**: finirebbe su git.
Chi sviluppa senza chiave non ha nulla da configurare — le frasi di riserva
tengono in piedi tutto il resto.

Al primo avvio Whisper scarica il suo modello (~460 MB), una volta sola.
