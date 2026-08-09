# IN-Motion — Prototipo 1

Pipeline: segnale emotivo (valence/arousal, per ora simulato) → agente Claude → TouchDesigner via OSC,
più un primo prototipo funzionante del sistema di particelle "volto ↔ forma astratta" dentro TD stesso.

## Componenti Python (in questa cartella)

- `visual_bridge.py` — invia `/emotion/valence` e `/emotion/arousal` a TD via OSC (dati simulati con onde sinusoidali).
  Se costruito con un `ClaudeVisualAgent`, invia in aggiunta `/scene/*` (palette, intensity, motion_speed, caption).
- `claude_agent.py` — `ClaudeVisualAgent`: chiede a Claude i parametri di scena in modo non bloccante (async, throttled).

## Setup

```bash
pip install anthropic python-osc
export ANTHROPIC_API_KEY="sk-ant-..."   # opzionale, solo per le decisioni di regia AI
python visual_bridge.py
```

## Prototipo TouchDesigner — `/prototype1`

Componente isolato dentro `NewProject.toe`, non tocca `/local`, `/mcp_webserver_base`, `/noise1`, `/oscin1` esistenti.

**Catena di generazione**
- `webcam` (Video Device In TOP) → `cam_avg` → `cam_avg_chop`: misura la luminosità media della webcam.
- `fallback_noise`: pattern procedurale animato usato quando la webcam non è disponibile.
- `face_source` (Switch TOP): sceglie automaticamente webcam reale o fallback in base alla luminosità rilevata (soglia 0.015) — nessun intervento manuale necessario.
- `posA_face` (GLSL): converte l'immagine sorgente in una texture di posizione 96×96 (griglia di punti, profondità = luminanza).
- `posB_abstract` (GLSL): genera proceduralmente una forma astratta (toroide deformato da rumore), stessa risoluzione.
- `control_chop` → `control_tex`: canali `morph` (0=volto, 1=astratto) e `turb` (intensità turbolenza), letti dal morph engine come texture invece che come uniform diretti (vedi nota tecnica sotto).
- `morph_engine` (GLSL): cross-fade tra le due texture di posizione + turbolenza (curl noise) scalata da `turb`.
- `particles` (Geometry COMP, GPU instancing su `morph_engine`, 9216 particelle) → `particle_mat` (colore legato alla valence) → `render_cam` / `render_light` → `render_out` (TOP finale).

**Orchestrazione**
- `phase_wave` (Wave CHOP, triangolare, periodo 14s, 0→1→0): pilota `control_chop.morph` — il ciclo automatico volto↔astratto.
- `control_chop.turb` è collegato a `/oscin1['emotion/arousal']`.
- `particle_mat` (colore) è collegato a `/oscin1['emotion/valence']` (blu freddo → oro caldo).

## Come eseguire il prototipo

1. Apri `NewProject.toe` in TouchDesigner e **porta la finestra in primo piano** — TD riduce il frame rate quando è in background/non a fuoco, e senza cook attivo il ciclo non anima (lezione imparata durante il debug: i parametri si aggiornano ma non si vedono finché TD non torna a cookare a piena velocità).
2. Se non l'hai già fatto, concedi il permesso camera a TouchDesigner in Preferenze di Sistema → Privacy → Fotocamera (in questa sessione il permesso risultava già concesso: la webcam reale viene già usata al posto del fallback).
3. Lancia `python visual_bridge.py` da questa cartella per avere lo stream di valence/arousal simulato su `/oscin1`.
4. Guarda `/prototype1/render_out` nel viewer di TD: la nuvola di particelle cicla automaticamente tra il point-cloud del tuo volto (dalla webcam) e il toroide astratto, con turbolenza legata all'arousal e colore legato alla valence.

## Note tecniche (limitazioni note del Prototipo 1)

- **Volto**: per ora è un rilievo di punti dalla luminanza dell'immagine webcam (griglia 96×96), non un vero landmark facciale ML — coerente con la scelta di partenza discussa ("anche semplice, non ancora ML in produzione"). Il passo successivo naturale è sostituire `posA_face` con landmark reali (es. Mediapipe) o point cloud LiDAR.
- **Uniform custom nel GLSL TOP**: la pagina "Const" del GLSL TOP si è rivelata inaffidabile in questo ambiente (i valori non arrivavano allo shader in modo consistente). I parametri dinamici (`morph`, `turb`) vengono quindi passati come texture 2×1 via CHOP→TOP invece che come uniform diretti — più verboso ma verificato funzionare in modo affidabile.
- **Regia Claude**: il collegamento tra le decisioni di `ClaudeVisualAgent` (palette/preset) e i nodi TD non è ancora cablato in `/prototype1` — per ora l'orchestrazione è puramente TD-nativa (Wave CHOP + OSC diretto), come da roadmap concordata (step 7 del piano).
