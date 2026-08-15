"""
musica.py
---------
Plays the session's music, in parallel with the visual scene.

Like scena.py: NO function here blocks. The audio stream runs on its own
thread; the state machine only calls play() / fade_out() / stop().

The music is NOT generated on the fly (MuseMorphose takes minutes on CPU): it
is chosen from a pre-rendered library per emotion (musica_libreria/Q2/*.wav).
The personalized version, based on the user's actual story, is generated in the
background as a take-away gift -- exactly like the high-resolution mandala.
"""
import os, glob, random, threading, wave
import numpy as np

LIBRARY = "musica_libreria"
SAMPLE_RATE = 44100


def _load_wav(path):
    with wave.open(path, "rb") as w:
        ch, sr, n = w.getnchannels(), w.getframerate(), w.getnframes()
        raw = w.readframes(n)
    data = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    data = data.reshape(-1, ch) if ch > 1 else np.stack([data, data], axis=1)
    return data, sr


def _pick_file(emotion, library=LIBRARY):
    files = glob.glob(os.path.join(library, emotion, "*.wav"))
    if not files:                                   # fallback: any track
        files = glob.glob(os.path.join(library, "*", "*.wav"))
    return random.choice(files) if files else None


def generate_personalized(emotion, callback=None):
    """Take-away gift: generate, in the background, the piece based on the real
    story. Non-blocking, and not needed for THIS session's playback."""
    def work():
        try:
            import session
            wav = session.run(emotion)
            print(f"  your personalized music: {wav}")
            if callback:
                callback(wav)
        except Exception as e:
            print(f"  personalized music not generated ({e})")
    threading.Thread(target=work, daemon=True).start()


class Music:
    def __init__(self, library=LIBRARY):
        self.library = library
        self._stream = None
        self._data = None
        self._pos = 0
        self._loop = True
        self._gain = 0.0
        self._gain_target = 0.0
        self._gain_step = 0.0          # per-frame ramp (fade)
        self._lock = threading.Lock()

    def _callback(self, outdata, frames, time_info, status):
        with self._lock:
            if self._data is None:
                outdata.fill(0); return
            out = np.empty((frames, 2), dtype=np.float32)
            filled = 0
            while filled < frames:
                take = min(frames - filled, len(self._data) - self._pos)
                out[filled:filled + take] = self._data[self._pos:self._pos + take]
                self._pos += take; filled += take
                if self._pos >= len(self._data):
                    if self._loop:
                        self._pos = 0
                    else:
                        out[filled:].fill(0); break
            # gain ramp (fade in/out)
            if self._gain_step != 0.0:
                g = self._gain + self._gain_step * np.arange(1, frames + 1)
                lo, hi = sorted((self._gain, self._gain_target))
                g = np.clip(g, lo, hi).astype(np.float32)
                self._gain = float(g[-1])
                if abs(self._gain - self._gain_target) < 1e-4:
                    self._gain, self._gain_step = self._gain_target, 0.0
            else:
                g = np.full(frames, self._gain, dtype=np.float32)
            outdata[:] = out * g[:, None]

    def play(self, emotion, fade=3.0, loop=True):
        path = _pick_file(emotion, self.library)
        if not path:
            print("music: no track in library, skipping"); return None
        data, sr = _load_wav(path)
        with self._lock:
            self._data, self._pos, self._loop = data, 0, loop
            self._gain = 0.0 if fade > 0 else 1.0
            self._gain_target = 1.0
            self._gain_step = (1.0 / (fade * sr)) if fade > 0 else 0.0
        try:
            import sounddevice as sd
            self._stream = sd.OutputStream(samplerate=sr, channels=2,
                                           callback=self._callback)
            self._stream.start()
        except Exception as e:
            print(f"music: audio not available ({e})"); return None
        print(f"music: {os.path.basename(path)} ({emotion})")
        return path

    def fade_out(self, seconds=5.0):
        with self._lock:
            self._gain_target = 0.0
            self._gain_step = (-self._gain / (seconds * SAMPLE_RATE)) if seconds > 0 else 0.0
        def _stop_after():
            import time; time.sleep(seconds + 0.3); self.stop()
        threading.Thread(target=_stop_after, daemon=True).start()

    def stop(self):
        if self._stream:
            try:
                self._stream.stop(); self._stream.close()
            except Exception:
                pass
            self._stream = None
