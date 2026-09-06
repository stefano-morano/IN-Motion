# IN-Motion

Un'esperienza di meditazione guidata. L'utente racconta a voce cosa lo affligge,
Claude ne ricava delle frasi su cui meditare, e tutto — volto, parole, mandala
finale — viene disegnato dalle stesse 13.664 particelle. Una voce le legge ad
alta voce mentre si formano.

**L'opera e' in inglese**: le scritte, la voce che le legge e il racconto di
chi partecipa. Questa documentazione resta in italiano — e' per chi ci lavora,
non per chi la guarda.

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
   fare altro. La finestra a schermo intero si apre da sola, **nera e muta**;
   poi immagine e musica salgono insieme e compare una nuvola di particelle
   sospese; dopo cinque secondi quelle particelle si raccolgono nel benvenuto.
   Portandosi in primo piano tiene anche l'orologio di TD alla velocita'
   giusta, che prima andava ricordato a mano.

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
musica scende dal 70% al 30%, suona una campana, e poi la musica risale.
Non a zero: nel silenzio assoluto la campana si sente come un'interruzione,
mentre un filo di musica sotto la tiene dentro il pezzo.

E' l'unica risposta possibile a chi ha gli occhi chiusi: a occhi chiusi lo
schermo non esiste, e il suono resta l'unico canale per dire "ti ho visto".
Due note diverse per i due versi — grave quando chiudi, una quinta sopra
quando riapri.

Alla fine il mandala viene salvato anche come **immagine da portare via**, in
`mandala/`, a 2400×2400 pixel. E' lo stesso disegno visto a schermo — stessi
petali, stessi anelli, stesso colore, stesso seme — ridisegnato con 260.000
particelle invece di 13.664, perche' li' non deve animarsi.

Due cose lo rendono personale: **Claude ne sceglie il carattere** (quanti
petali, quanti anelli, che colore) da cio' che hai raccontato, e **la
complessita' cresce con quanto sei rimasto in meditazione** — un livello di
dettaglio ogni 40 secondi.

## Il colore

Il blu delle prime fasi non e' il colore dell'opera: e' il colore di **prima
che l'opera sappia chi ha davanti**. La tinta che Claude ricava dal racconto
non aspetta il mandala per farsi vedere — entra appena esiste, e cresce fase
per fase:

| Fase | Colore |
|---|---|
| dall'apertura all'attesa | il blu di sempre |
| Danza | lo stesso blu, che comincia a scaricarsi |
| Meditazione | la tinta di chi medita, tenuta bassa |
| Mandala, dissoluzione, commiato | quella tinta, piena |

Fra la danza e la meditazione il colore passa per un grigio. E' voluto, ed e'
l'unica strada onesta: il blu sta a 212 gradi e le tinte personali stanno
spesso dall'altra parte della ruota, quindi **mediarle** farebbe passare il
colore per una TERZA tinta — con un'ancora ambra la meditazione resterebbe un
minuto su un verde che non c'entra niente. Invece la tonalita' non si sposta
mai: prima e' il blu che si scarica, poi e' la tinta personale che si carica.
Cio' che si vede non e' un colore intermedio, e' il blu che lascia la presa.

Le tre soste (`TINTA_DANZA`, `TINTA_MEDITAZIONE`, `TINTA_MANDALA` in
`esperienza.py`) stanno apposta **fuori** dal punto grigio: il grigio si
attraversa in movimento, dove non lo si nota.

Segue la stessa strada anche **l'alone di sfondo**, cosi' il colore non e'
addosso alle particelle ma nell'aria intorno. Dentro TD forma e colore
dell'alone sono due nodi separati (`sfondo` x `sfondo_tinta`): una tabella di
chiavi non si puo' riscrivere ad ogni fotogramma, un parametro con
un'espressione si rivaluta da solo.

Quanto i colori sono accesi lo decide una manopola sola, `INTENSITA_COLORE`.
Alza **solo la saturazione** — tonalita' e luminosita' restano quelle tarate.
Il tetto pratico e' 1.5: da li' in su le due tinte del gradiente arrivano
insieme alla saturazione piena e il mandala diventa una tinta unita invece di
un passaggio. Il valore e' duplicato in `td_face_points.py` e `mandala.py`,
come `GRADIENTE`: **se lo cambi, cambialo in tutti e due**, o l'immagine da
portare via non e' piu' quella che la persona ha visto.

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
| `voce.py` | la guida che legge le scritte (ElevenLabs) |
| `voci.py` | attrezzo: sceglie CHI legge, facendola parlare |
| `prepara_voce.py` | attrezzo: sintetizza in anticipo le scritte fisse |
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

**Python decide, TouchDesigner disegna.** Python manda nove soli messaggi OSC
sulla porta 8001 (`/prepara`, `/mandala`, `/tinta`, `/tinta_forza`, `/scena`,
`/finestra`, `/azzera`, `/buio`, `/accendi`); i punti del viso viaggiano a
parte sulla 8000. TD non sa
nulla dell'esperienza: sa solo come passare da una forma all'altra.

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

**Immagine e musica aprono insieme.** Il tappeto non entra col benvenuto:
sale nello stesso momento in cui lo schermo si accende, dallo stesso nero e
con la stessa identica curva. Non sono due dissolvenze sincronizzate a mano —
il volume audio usa la formula del Level TOP, e le due salite coincidono al
millesimo. La traccia viene pero' CARICATA prima, a sipario chiuso: leggerla e
filtrarla richiede circa un secondo e mezzo di lavoro che blocca il programma,
e farlo mentre l'immagine sale inchioderebbe la dissolvenza a meta'.

**La dissolvenza d'apertura non e' lineare.** L'occhio distingue molto meglio
le differenze in penombra che quelle in piena luce: con una rampa lineare
l'immagine "arriva" quasi subito e poi passa il resto del tempo a schiarire di
poco. Elevando l'avanzamento a una potenza (`CURVA_DISSOLVENZA`) il nero resta
nero piu' a lungo e la luce sale alla fine — a meta' tempo si e' al 22%, non al
50%. Si vede nascere invece che comparire.

**Un solo livello per tutta l'opera.** Qualunque cosa suoni — il tappeto o la
traccia della meditazione — suona al 70%: cambia la musica, non quanto e'
forte. Le due sole eccezioni sono funzionali: il tappeto scende al 30% mentre
la persona parla (altrimenti Whisper sente lui e non lei) e tace del tutto
durante la meditazione, per lasciare il campo alla traccia generata.

**Volume e attenuazione sono due numeri diversi.** Il volume dice quanto forte
va la musica in questa scena e lo decide la macchina a stati; l'attenuazione
dice quanto la stiamo abbassando adesso per far posto ad altro, e lo decide lo
stacco. Si moltiplicano. Con un valore solo i due si sovrascriverebbero a
vicenda — lo stacco riporterebbe su una musica che la scena voleva muta.

**Funziona anche quando qualcosa si rompe.** Senza chiave API, senza rete,
senza microfono, l'esperienza va avanti con frasi di riserva scritte a mano.

**La voce dice le stesse parole che le particelle disegnano.** Non e' un
narratore che commenta: e' la stessa frase detta due volte, con due mezzi. Per
questo entra quando la scritta si e' FORMATA, non quando comincia a formarsi —
durante la transizione le particelle si stanno ancora disponendo e non c'e'
niente da leggere; sentirsi dire una frase che non si vede ancora la
trasformerebbe in un annuncio. E per questo la scritta non se ne va finche' la
voce non ha finito: la permanenza a schermo non e' piu' un tempo fisso, e'
`max(tempo di lettura, durata della voce + un respiro)`.

**Le clip esistono prima dell'esperienza.** Nessuna sintesi avviene mentre
l'opera gira: le scritte fisse si preparano una volta con `prepara_voce.py` e
restano su disco (`voce_cache/`), le tre frasi personali si sintetizzano nello
stesso thread che le ha appena generate, mentre a schermo scorre "preparo la
tua meditazione". Tre ragioni, in ordine di peso: una chiamata di rete in
mezzo all'esperienza sarebbe un buco di due secondi; il piano gratuito da'
circa 10.000 caratteri al mese e risintetizzare ogni volta le stesse scritte
lo brucerebbe in una giornata di prove; in mostra la rete e' quella che e'. A
cache piena l'unica cosa che dipende da internet sono le frasi personali, che
hanno gia' il loro ripiego.

**Mentre la voce parla la musica si fa da parte.** Non e' lo stacco — quello
annuncia un passaggio di stato, questo fa spazio a delle parole — e non deve
litigarci: usa un moltiplicatore suo (`attenua_per_voce`). Cosi' i due
possono capitare insieme, che succede ogni volta che si riaprono gli occhi
mentre una frase e' ancora in bocca, e ognuno rilascia la musica quando ha
finito lui.

**Il fornitore e' sostituibile, il resto no.** Tutto il dialogo con
ElevenLabs o con Polly sta dentro una classe che espone sei cose: se e'
attiva, perche' no, chi legge, la sua firma, l'elenco delle voci, e come si
sintetizza una frase. Sopra quella riga non c'e' un solo `if` sul fornitore —
cache, tempi, code, attenuazione della musica non sanno da dove arrivi
l'audio. E' quello che ha permesso di aggiungere Polly senza toccare la
macchina a stati, ed e' anche il motivo per cui le clip dei due convivono: la
firma entra nell'impronta del file, quindi cambiare motore non cancella
niente e tornare indietro non ripaga niente.

**Senza voce l'opera resta intera.** Niente chiave, niente rete, niente
libreria, cache fredda: le scritte restano mute e i tempi tornano esattamente
quelli di prima, perche' `voce.durata()` vale zero e la permanenza ricade
sulle costanti. E' la stessa scelta delle frasi di riserva.

**La privacy e' una scelta di progetto.** Il volto diventa coordinate e l'audio
viene trascritto in locale: a TouchDesigner non arriva mai il video, e l'audio
non lascia il computer. Esce solo il testo, e solo verso Claude.

**La resa grafica e' codice, non nodi cliccati.** Colore per particella, fusione
additiva e la catena bagliore → sfondo (forma × tinta) → vignetta → grana sono
costruiti da `td_estetica.py`. Il `.toe` e' binario: se la resa vivesse solo li' dentro,
sarebbe invisibile a git e irrecuperabile in caso di guaio. Per ricostruirla,
dentro TouchDesigner:

```python
exec(open('/percorso/di/visuals/td_estetica.py', encoding='utf-8').read())
```

`encoding='utf-8'` non e' facoltativo: il Python dentro TouchDesigner apre i
file in ascii e si ferma sul primo trattino lungo o accento — e questi file ne
sono pieni. Stesso discorso per `td_ripristina.py`, che rimette dentro TD
tutti e tre i file di questa cartella in un colpo solo.

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
python3 voci.py         # scegli CHI legge: te le fa sentire una per una
python3 prepara_voce.py # sintetizza le scritte fisse, una volta per tutte
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

### Le chiavi API

Sono due, `ANTHROPIC_API_KEY` per le frasi e `ELEVENLABS_API_KEY` per la voce,
e **nessuna delle due serve a tutti.** Senza la prima il sistema usa frasi di
riserva scritte a mano; senza la seconda le scritte restano mute. Chi lavora
sui visual, sull'audio o sui tempi non ha nulla da configurare.

Valgono per entrambe le stesse due regole. Una chiave si manda **a voce o in
un messaggio privato**, si mette nell'ambiente (`export ANTHROPIC_API_KEY="..."`
in `~/.zshrc`), e **mai in un file del progetto** — finirebbe su git al primo
push. E conviene impostare un tetto di spesa nella console: una chiave
condivisa non si puo' attribuire a nessuno, e revocarla la toglie a tutti
insieme.

### La voce

**Con l'opera in inglese, ElevenLabs gratis basta e avanza.** E non e' un
dettaglio di budget: e' il motivo per cui la lingua e' stata scelta cosi'. Le
voci di serie di ElevenLabs sono NATIVE inglesi — Sarah, Lily, Jessica, Alice
— e sono le migliori che abbia. In italiano invece le native esistono solo
nella libreria pubblica, che il piano gratuito non puo' usare via API (`402`):
gratis, in italiano, si parlava con l'accento americano. L'inglese ha tolto di
mezzo l'accento, l'abbonamento e la dipendenza da un fornitore a pagamento
tutti insieme.

**Resta comunque un secondo motore**, Amazon Polly, e si sceglie con
`VOCE_MOTORE` (`elevenlabs` o `polly`); lasciando la variabile vuota vince il
primo configurato. Serve a due cose: non dipendere da un solo fornitore, e
avere una via d'uscita se un giorno il pezzo tornasse in italiano, dove Polly
ha le voci native di serie.

| | ElevenLabs | Amazon Polly |
|---|---|---|
| voci native inglesi | **di serie** (Sarah, Lily, Jessica...) | di serie (Danielle, Ruth...) |
| voci native italiane | solo libreria, a pagamento | **di serie** (Beatrice, Bianca) |
| gratis al mese | 10.000 caratteri | 1.000.000 (neural), 5.000.000 (standard) |
| qualita' | piu' calda, piu' respirata | piu' piatta |
| frequenza | 44.1 kHz | 24 kHz |
| configurazione | una chiave | account AWS, utente IAM, due chiavi |

Il consumo di questo pezzo e' ~800 caratteri una volta piu' ~110 a sessione:
su ElevenLabs sono ottanta sessioni al mese, su Polly diecimila.

La cache tiene conto di chi parla, quindi **i due convivono**: si provano tutti
e due sulle frasi vere e si torna indietro senza ripagare nulla.

**La lingua sta in quattro posti**, e sono tutti dichiarati: le scritte in
`esperienza.py`, il prompt in `testi.py`, `LINGUA` in `ascolto.py` (cosa
ascolta Whisper) e `LINGUA` in `voce.py` (quali voci preferire, e se
rimettere gli accenti italiani). Cambiarla non tocca nient'altro.

#### ElevenLabs

Serve un account su [elevenlabs.io](https://elevenlabs.io). Il piano gratuito
basta per lavorare: da' circa **10.000 crediti al mese, e un credito e' un
carattere**. Il conto e' questo: tutte le scritte fisse, varianti comprese,
sono 731 caratteri — si pagano **una volta sola**; ogni sessione poi ne costa
circa 110, che sono le tre frasi personali. Fanno una ottantina di sessioni al
mese. Se invece si risintetizzasse tutto ad ogni giro sarebbero meno di dieci,
ed e' esattamente il motivo per cui la cache esiste. (Il piano gratuito non da'
l'uso commerciale e chiede di citare ElevenLabs: per una tesi o
un'installazione non commerciale va bene, per qualunque altra cosa serve il
piano da 5$.)

Poi, dal terminale:

```bash
export ELEVENLABS_API_KEY="..."   # meglio in fondo a ~/.zshrc
pip3 install elevenlabs soundfile
python3 voci.py                  # elenca le voci e le fa parlare
```

Le voci di serie sono gia' quelle giuste per l'opera in inglese: non serve
la libreria pubblica, e quindi non serve nessun abbonamento.

**Attenzione a come crei la chiave.** ElevenLabs propone di default una chiave
*ristretta*, con tutti i permessi spenti: e' valida, ma risponde **401 esattamente
come una chiave sbagliata**, e si finisce per rigenerarne tre o quattro — tutte
ugualmente ristrette. Servono almeno **Text to Speech** e **Voices: read**
(piu' **Voices: write** per `voci.py aggiungi`). Si accendono su elevenlabs.io →
API Keys → Edit, senza doverla rifare. Se il messaggio dice *"alla chiave mancano
dei permessi"*, e' questo.

`voci.py` non elenca e basta: fa dire a ogni candidata femminile e giovane le
**frasi vere dell'opera**, non un testo di prova. Una voce puo' essere
bellissima su "buongiorno, questa e' una prova" e sbagliata sopra "chiudi gli
occhi": e' il materiale a giudicarla. Quando ne hai una:

```bash
python3 voci.py scegli Alice     # la scrive in voce_scelta.json
python3 prepara_voce.py          # sintetizza tutte le scritte fisse
```

Le voci di serie parlano italiano con l'accento della lingua in cui sono nate.
Per una voce italiana vera c'e' la libreria pubblica:

```bash
python3 voci.py cerca            # femminili, giovani, in italiano
python3 voci.py aggiungi <id>    # la copia nel tuo account
```

**Ma serve un piano a pagamento.** Sul piano gratuito una voce della libreria
si aggiunge all'account e compare negli elenchi, e sembra tutto a posto: e' la
SINTESI a rifiutarla, con un `402`. Il piano Starter (5$) la sblocca, insieme
all'uso commerciale. Restando gratuiti si sceglie fra le voci di serie, che
l'italiano lo dicono con l'accento della lingua in cui sono nate — su una
meditazione, dove a occhi chiusi la voce e' l'unico canale rimasto, si sente.

Cambiando voce le clip in cache non valgono piu' (l'impronta del file tiene
conto di chi parla, del modello e della velocita'): si rilancia
`prepara_voce.py` e le vecchie restano li' senza dare fastidio.

#### Amazon Polly

Le voci italiane qui sono di serie: **Beatrice** (motore `generative`, il piu'
naturale) e **Bianca** (anche `neural` e `standard`). Nessuna libreria a
pagamento di mezzo.

Serve un account AWS, un utente IAM con la policy `AmazonPollyReadOnlyAccess`,
e la sua coppia di chiavi. Poi:

```bash
pip3 install boto3
export AWS_ACCESS_KEY_ID="..."          # in ~/.zshrc, come le altre
export AWS_SECRET_ACCESS_KEY="..."
export VOCE_MOTORE=polly
python3 voci.py                         # le voci italiane della region
python3 prepara_voce.py
```

La region conta: **le voci `generative` non esistono ovunque.** Se quella
configurata non le ha, il codice scende da solo a `neural` e lo dice, invece
di fallire in faccia al primo avvio. Si forza con `VOCE_POLLY_REGIONE`.

Un dettaglio che si paga in silenzio se non lo si sa: **il motore `generative`
non accetta SSML**, quindi con Beatrice la velocita' di lettura non si puo'
rallentare — il suo passo naturale e' gia' posato, ma e' quello e basta. Con
`neural` e `standard` il rallentamento c'e' (`POLLY_VELOCITA`).

#### Le manopole

Come suona, in cima a `voce.py`:

| | cosa fa |
|---|---|
| `VELOCITA` | 0.88. Sotto 1 rallenta la dizione. ElevenLabs accetta 0.7–1.2 |
| `STABILITA` | 0.65. Alta = lettura posata; in meditazione l'espressivita' e' un difetto |
| `SOMIGLIANZA` | 0.80. Quanto resta aderente al timbro originale della voce |
| `STILE` | 0.0. Enfasi interpretativa: qui non ne serve |
| `VOLUME` | 0.95. La voce sta davanti, e' lei che guida |
| `POLLY_VELOCITA` | "90%". Vale solo su `neural` e `standard`: `generative` non accetta SSML |

Come respira, in `esperienza.py`:

| | cosa fa |
|---|---|
| `CODA_VOCE` | 1.2 s di silenzio dopo l'ultima parola, prima di cambiare scritta |
| `LEGGIBILE` | 2.0 s, il minimo a schermo. Vince il piu' lungo fra questo e la voce |

**La velocita' non si sceglie leggendo un numero.** 0.85 non vuol dire niente
finche' non lo senti accanto a 0.95, e provarlo cambiando la costante
costerebbe una passata intera di sintesi a ogni tentativo — la velocita' entra
nell'impronta della cache, quindi cambiarla rifa' tutte le clip. Per questo c'e':

```bash
python3 voci.py velocita              # 0.75, 0.85, 0.95, 1.0 in fila
python3 voci.py velocita 0.8 0.9      # o i valori che vuoi
```

Una frase sola, letta a piu' velocita', una cinquantina di crediti invece di
ottocento. Quella che convince si scrive in `VELOCITA` e poi si rilancia
`prepara_voce.py`.
