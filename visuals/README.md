# IN-Motion

Un'esperienza di meditazione guidata. L'utente racconta a voce cosa lo affligge,
Claude ne ricava delle frasi su cui meditare, e tutto — volto, parole, mandala
finale — viene disegnato dalle stesse 13.664 particelle.

**Non si tocca mai la tastiera**: l'esperienza si comanda chiudendo e riaprendo
gli occhi.

## Come si esegue

1. Apri `visual_TD.toe` in TouchDesigner. Assicurati che ci sia **una sola
   istanza di TD aperta**: una seconda si prende le porte OSC e la prima non
   riceve piu' nulla.
2. Lancia:

   ```bash
   python3 main.py "racconto di ripiego"
   ```

   Il testo fra virgolette serve solo se il microfono non e' disponibile o non
   sente nulla.
3. **Mettiti davanti alla telecamera** e aspetta qualche secondo. Non devi
   fare altro. La finestra a schermo intero si apre da sola, **nera**; poi
   l'immagine sale piano e compare una nuvola di particelle sospese; dopo
   cinque secondi quelle particelle si raccolgono nel benvenuto. Portandosi in
   primo piano tiene anche l'orologio di TD alla velocita' giusta, che prima
   andava ricordato a mano.

   L'attesa e' voluta. Fra un lancio e l'altro TouchDesigner resta acceso e
   **congelato sull'ultima immagine di chi c'e' stato prima**: ricalcola solo
   quando ricomincia a ricevere punti dalla webcam, quindi azzerare la scena
   da Python non basta a scongelarlo. Percio' prima si aspetta di aver visto
   un volto, poi TD disegna le scritte, poi le particelle si sparpagliano — e
   solo a quel punto si apre la finestra. Chi guarda trova la scena gia'
   montata, e il primo movimento che vede e' gia' l'opera.

Si ferma con `Ctrl+C`, e la finestra si richiude da sola. `Esc` la chiude in
qualunque momento. Per lavorare dentro l'editor invece che a schermo intero:
`FINESTRA_A_SCHERMO_INTERO = False` in cima a `main.py`.

## Il filo dell'esperienza

| Fase | Cosa vedi | Come si passa oltre |
|---|---|---|
| Apertura | dal nero a una nuvola sospesa, che si raccoglie nel benvenuto | a tempo |
| Invito | l'invito a raccontare | **chiudi gli occhi** |
| Ascolto | il tuo volto | parli; **riapri gli occhi** |
| Attesa | "preparo la tua meditazione" | quando Claude ha risposto |
| Danza | frasi e volto che si alternano | a tempo |
| Meditazione | il tuo volto | **chiudi gli occhi**, mediti, **riapri** |
| Mandala | il mandala della tua sessione | dopo 40 secondi |

Gli occhi vanno tenuti chiusi (o aperti) **2 secondi** perche' il cambiamento
conti: sotto quella soglia e' un battito di ciglia, non una scelta.

Ogni volta che il cambiamento viene accettato si sente uno **stacco**: la
musica scende a zero, suona una campana, e la musica della scena nuova
rientra. E' l'unica risposta possibile a chi ha gli occhi chiusi — a occhi
chiusi lo schermo non esiste, e il suono resta l'unico canale per dire "ti ho
visto". Due note diverse per i due versi: grave quando chiudi, una quinta
sopra quando riapri.

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
| `movimento.py` | dal naso, quanta energia c'e' nel gesto |
| `scena.py` | i comandi verso TD |
| `esperienza.py` | **decide cosa succede e quando** |
| `musica.py` | il motore audio: tracce, volumi, dissolvenze |
| `campanella.py` | sintetizza le due campane (nessun file audio) |
| `stacco.py` | musica giu' → campana → musica su, ad ogni cambio |
| `mandala.py` | disegna il mandala ad alta risoluzione, da portare via |
| `taratura.py` | attrezzo: misura la soglia degli occhi sul tuo viso |
| `controlla.py` | attrezzo: verifica che tutto sia a posto |
| `td_face_points.py` | copia di riferimento del motore grafico dentro TD |
| `td_controllo_osc.py` | copia di riferimento del ricevitore OSC dentro TD |
| `td_estetica.py` | ricostruisce dentro TD tutta la resa grafica |
| `td_ripristina.py` | rimette dentro TD tutti e tre i file qui sopra |

`esperienza.py` e' il file da aprire per cambiare le scritte o i tempi: sono
tutte costanti in cima.

## Come e' fatto

**Python decide, TouchDesigner disegna.** Python manda sette soli messaggi OSC
sulla porta 8001 (`/prepara`, `/mandala`, `/scena`, `/finestra`, `/azzera`,
`/buio`, `/accendi`); i punti del viso viaggiano a parte sulla 8000. TD non sa nulla dell'esperienza: sa solo
come passare da una forma all'altra.

**Niente blocca il ciclo.** `esperienza.py` non aspetta mai: ad ogni fotogramma
le si chiede "e adesso?". Le chiamate lente (Claude, Whisper) girano in thread
separati. E' la condizione perche' il sistema possa accorgersi degli occhi che
si chiudono mentre sta facendo altro.

**Un flusso audio si apre una volta sola.** Microfono, tappeto e traccia della
meditazione si aprono tutti all'avvio e restano aperti fino alla fine: aprire o
chiudere un flusso mentre un altro suona fa riconfigurare la scheda audio, e si
sente come un click. Quello che si accende e si spegne e' solo un interruttore.
Per lo stesso motivo la campana non ha un flusso suo: si somma dentro quello
del tappeto.

**La dissolvenza d'apertura non e' lineare.** L'occhio distingue molto meglio
le differenze in penombra che quelle in piena luce: con una rampa lineare
l'immagine "arriva" quasi subito e poi passa il resto del tempo a schiarire di
poco. Elevando l'avanzamento a una potenza (`CURVA_DISSOLVENZA`) il nero resta
nero piu' a lungo e la luce sale alla fine — a meta' tempo si e' al 22%, non al
50%. Si vede nascere invece che comparire.

**Volume e attenuazione sono due numeri diversi.** Il volume dice quanto forte
va la musica in questa scena e lo decide la macchina a stati; l'attenuazione
dice quanto la stiamo abbassando adesso per far posto ad altro, e lo decide lo
stacco. Si moltiplicano. Con un valore solo i due si sovrascriverebbero a
vicenda — lo stacco riporterebbe su una musica che la scena voleva muta.

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
4. **Se lavori dentro l'editor** invece che a schermo intero
   (`FINESTRA_A_SCHERMO_INTERO = False`), ricordati di tenere TouchDesigner in
   primo piano: quando non e' la finestra attiva il suo orologio rallenta e le
   transizioni restano immobili. Con la finestra a schermo intero il problema
   non si pone, perche' e' lei a stare davanti.
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
