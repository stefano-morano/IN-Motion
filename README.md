# IN-Motion

Esperienza interattiva di meditazione guidata con intelligenza artificiale, visualizzazioni a particelle e riconoscimento vocale.

---

## Requisiti

- **macOS** 10.14 o superiore
- **Python 3.10+** — scaricabile da [python.org/downloads](https://python.org/downloads)
- **Connessione internet** alla prima installazione (~500 MB di dipendenze)
- Una **chiave API Anthropic** — ottenibile su [console.anthropic.com](https://console.anthropic.com)

---

## Installazione

### 1. Scarica il progetto
Assicurati di avere l'**intera cartella** `IN-Motion/` con `visuals/musica_libreria/`.

### 2. Configura la chiave API
Apri il file `.env` nella cartella principale:
```
ANTHROPIC_API_KEY=sk-ant-LA-TUA-CHIAVE-QUI
```

### 3. Avvia
Fai **doppio clic** su `Lancia IN-Motion.command`.

La prima volta installa tutto in automatico e scarica il modello vocale (~500 MB). Dalle volte successive è immediato.

> Se macOS blocca il file: **Impostazioni di Sistema → Privacy e sicurezza → Apri comunque**

---

## Come si usa

1. Scrivi nella casella ciò che ti affligge (una o due frasi), oppure parla dopo aver cliccato **Inizia**
2. Clicca **Inizia**
3. Segui le istruzioni sullo schermo — l'esperienza dura circa 10–15 minuti
4. Tieni la finestra Terminale aperta; **Ctrl+C** per fermare

> Per un'esperienza ottimale usa cuffie in uno spazio tranquillo.

---

## Avvio manuale

```bash
cd /percorso/IN-Motion/web/backend
python3 -m pip install -r requirements.txt   # solo la prima volta
python3 -m uvicorn server:app --host 0.0.0.0 --port 8080
```

Poi apri `http://localhost:8080`.

---

## Risoluzione problemi

| Problema | Soluzione |
|---|---|
| "Python 3 non trovato" | Installa da [python.org/downloads](https://python.org/downloads) |
| Il browser non si apre | Apri manualmente `http://localhost:8080` |
| Nessuna musica | Verifica `visuals/musica_libreria/` con i file WAV |
| Microfono non funziona | Concedi l'accesso al microfono nel browser |
| Errore API Anthropic | Verifica la chiave nel `.env` |