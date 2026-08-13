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

Alla fine il mandala viene salvato anche come **immagine da portare via**, in
`mandala/`, a 2400×2400 pixel. E' lo stesso disegno visto a schermo — stessi
petali, stessi anelli, stesso colore, stesso seme — ridisegnato con 260.000
particelle invece di 13.664, perche' li' non deve animarsi.

Due cose lo rendono personale: **Claude ne sceglie il carattere** (quanti
petali, quanti anelli, che colore) da cio' che hai raccontato, e **la
complessita' cresce con quanto sei rimasto in meditazione** — un livello di
dettaglio ogni 40 secondi.

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
| `mandala.py` | disegna il mandala ad alta risoluzione, da portare via |
| `taratura.py` | attrezzo: misura la soglia degli occhi sul tuo viso |
| `td_face_points.py` | copia di riferimento del motore grafico dentro TD |
| `td_controllo_osc.py` | copia di riferimento del ricevitore OSC dentro TD |
| `td_estetica.py` | ricostruisce dentro TD tutta la resa grafica |

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

**La resa grafica e' codice, non nodi cliccati.** Colore per particella, fusione
additiva e la catena bagliore → sfondo → vignetta → grana sono costruiti da
`td_estetica.py`. Il `.toe` e' binario: se la resa vivesse solo li' dentro,
sarebbe invisibile a git e irrecuperabile in caso di guaio. Per ricostruirla,
dentro TouchDesigner:

```python
exec(open('/percorso/di/visuals/td_estetica.py').read())
```

## Prima volta, su un computer nuovo

```bash
pip3 install -r requirements.txt
python3 controlla.py
```

`controlla.py` verifica tutto — librerie, file, telecamera, microfono, modello
di trascrizione, chiave API, TouchDesigner — e per ogni cosa che manca dice
**cosa fare esattamente**. Lancialo prima, non poco prima di una prova: e' lui
a far comparire le richieste di permesso di macOS, e finche' non rispondi il
programma non vede e non sente nulla.

Poi:

```bash
python3 taratura.py     # misura la soglia degli occhi sul TUO viso
```

### I cinque intoppi tipici

1. **Permessi di telecamera e microfono.** macOS li concede al *programma da
   cui lanci* (Terminale, VS Code...), non allo script. Se hai risposto no una
   volta, non te lo richiede piu': Impostazioni di Sistema → Privacy e
   sicurezza → Fotocamera / Microfono. **Dopo averlo attivato, chiudi e riapri
   quel programma**, altrimenti il permesso non ha effetto.
2. **Il modello di Whisper**: ~460 MB scaricati al primo avvio. Falli scaricare
   in anticipo, con una connessione decente.
3. **Due TouchDesigner aperti**: il primo si prende le porte OSC e il secondo
   non riceve piu' nulla — i nodi vanno in errore e sembra tutto rotto. Deve
   essercene **uno solo**.
4. **TouchDesigner deve restare la finestra in primo piano**, altrimenti il suo
   orologio rallenta e le transizioni restano immobili.
5. **La soglia degli occhi e' personale.** Il valore in `occhi.py` e' stato
   misurato su un viso e una luce precisi: su un'altra persona puo' sbagliare.
   `taratura.py` la rimisura in trenta secondi.

### La chiave API

**Non serve a tutti.** Senza chiave il sistema funziona lo stesso, con frasi di
riserva scritte a mano: chi lavora sui visual, sull'audio o sui tempi non ha
nulla da configurare. Serve solo a chi vuole provare la generazione sul
racconto vero.

Se una chiave viene condivisa nel gruppo: si manda **a voce o in un messaggio
privato**, si mette nell'ambiente (`export ANTHROPIC_API_KEY="..."` in
`~/.zshrc`), e **mai in un file del progetto** — finirebbe su git al primo
push. Conviene anche impostare un tetto di spesa nella console di Anthropic:
una chiave condivisa non si puo' attribuire a nessuno, e revocarla la toglie a
tutti insieme.
