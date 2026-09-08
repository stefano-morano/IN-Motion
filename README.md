# IN-Motion

<p align="center">
  <img src="web/assets/logo%20white.png" alt="IN-Motion" width="280">
</p>

Interactive guided meditation experience with AI, particle visuals, facial and voice recognition.

Compatible with **Windows**, **macOS**, and **Linux**.

<p align="center">
  <img src="web/assets/simbols/Screenshot.png" alt="IN-Motion screenshot" width="720">
</p>

---

## Requirements

- **Windows**, **macOS**, or **Linux**
- **Python 3.10+** — [python.org/downloads](https://python.org/downloads)
- Internet connection (first install and cloud APIs)
- Modern browser with webcam and microphone access (Chrome / Edge / Firefox recommended)
- **Anthropic** API key — [console.anthropic.com](https://console.anthropic.com)
- **ElevenLabs** API key (voice) — [elevenlabs.io](https://elevenlabs.io)  
  Optional: **Firebase** for login and session history

---

## Setup and launch

### 1. Configure keys

Download the project `.env` from  
[https://workupload.com/file/v8XjpkuMRUb](https://workupload.com/file/v8XjpkuMRUb).

You need the download **password** (ask the project maintainer if you do not have it).  
Place the file in the **project root** as `.env` (same folder as `README.md`, `MacOs.command`, `Windows.bat`, and `Linux.sh`).

Alternatively, create `.env` yourself in the project root:

```
ANTHROPIC_API_KEY=sk-ant-...
ELEVENLABS_API_KEY=sk_...
```

(Optional: `FIREBASE_*` variables from the Firebase console.)

### 2. Start

Use the launcher for your OS (double-click or run from a terminal):

| OS | Launcher |
|---|---|
| **macOS** | `MacOs.command` |
| **Windows** | `Windows.bat` |
| **Linux** | `Linux.sh` (`chmod +x Linux.sh` once if needed) |

Or start the server manually:

```bash
cd /path/to/IN-Motion/web/backend
python3 -m pip install -r requirements.txt   # first time only
python3 -m uvicorn server:app --host 0.0.0.0 --port 8080
```

On Windows you can use `python` instead of `python3` if that is how Python is installed.

Then open **http://localhost:8080**.

The first run downloads dependencies and the Whisper model (~500 MB).  
Stop the server with **Ctrl+C** (or close the launcher window).

> **macOS:** if the system blocks `MacOs.command`, go to **System Settings → Privacy & Security → Open Anyway**.  
> **Windows:** if SmartScreen warns, choose **More info → Run anyway**.  
> **Linux:** grant execute permission with `chmod +x Linux.sh` if double-click does not run it.

---

## How to use

1. Sign in (if Firebase is configured) and complete your profile
2. Click **Start** and follow the on-screen guidance
3. Close your eyes and speak about what you carry; the experience guides you with voice, music, and particles (~10–15 min)
4. After the session: reflection, emotion charts, and history

> Use headphones in a quiet space; allow microphone and webcam in the browser. The webcam does not record video.

---

## APIs and tools

| Component | Role |
|---|---|
| **Anthropic Claude** | Generates phrases, mandala (petals/color), and emotion quadrant Q1–Q4 from the story; post-session emotion analysis |
| **ElevenLabs** | Guide voice synthesis |
| **faster-whisper** | Transcription of story / reflection (local) |
| **MediaPipe Face Landmarker** | 478 landmarks + 52 blend shapes; particle face mesh and valence/arousal estimate |
| **Three.js** | WebGL particle rendering (additive blending, bloom) |
| **Firebase** (optional) | Auth and session / calendar storage |
| **FastAPI + Uvicorn** | Backend and WebSocket to the browser |

Supporting stack: **NumPy**, **Pillow**, WAV music library in `visuals/musica_libreria/`.

---

## Troubleshooting

| Issue | Fix |
|---|---|
| "Python 3 not found" | Install from [python.org/downloads](https://python.org/downloads) and ensure it is on `PATH` |
| Browser does not open | Open `http://localhost:8080` manually |
| No music | Check `visuals/musica_libreria/` for WAV files |
| Microphone / webcam | Allow access in the browser |
| Anthropic / ElevenLabs API error | Check keys in `.env` |
| Linux script will not run | `chmod +x Linux.sh` then `./Linux.sh` |
