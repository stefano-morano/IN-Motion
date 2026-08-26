"""
musica.py
---------
Plays the session's music, in parallel with the visual scene.

Like scena.py: NO function here blocks. The audio stream runs on its own
thread; the state machine only calls play() / fade_out() / stop().

The music is NOT generated on the fly (MuseMorphose takes minutes on CPU): it
is chosen from a pre-rendered library per emotion (musica_libreria/Q2/*.wav).
"""
import os, glob, random, sys, threading, time, wave
import numpy as np

# Ogni percorso e' ancorato a QUESTO file, non alla cartella da cui si lancia:
# con un percorso relativo la libreria spariva a seconda di dove ti trovavi
# col terminale, e la musica non partiva mai senza dire perche'.
CARTELLA = os.path.dirname(os.path.abspath(__file__))
LIBRARY = os.path.join(CARTELLA, "musica_libreria")

# Un blocco generoso da' respiro alla scheda audio. Mentre Whisper trascrive
# la CPU e' satura per qualche secondo, e con blocchi piccoli il flusso resta
# a secco: sono i click che si sentivano attorno a "preparo la tua meditazione".
BLOCCO = 2048
MOTORE = os.path.join(os.path.dirname(CARTELLA), "music")
SAMPLE_RATE = 44100


def _load_wav(path):
    with wave.open(path, "rb") as w:
        ch, sr, n = w.getnchannels(), w.getframerate(), w.getnframes()
        raw = w.readframes(n)
    data = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    data = data.reshape(-1, ch) if ch > 1 else np.stack([data, data], axis=1)
    return data, sr


CODA_CUCITURA = 3.0     # secondi di sovrapposizione per cucire il loop

# ---------- il tappeto: piu' rado, piu' grave, piu' morbido ----------
# Il motore genererebbe direttamente una versione cosi' (bastano polifonia e
# intensita' ritmica piu' basse), ma qui non puo' girare: mancano soundfont,
# pesi e FluidSynth. Si lavora quindi sull'audio gia' reso — e per fortuna
# RALLENTARE una traccia fa da solo tre delle quattro cose chieste: abbassa le
# note, dirada gli attacchi nel tempo e allunga i transienti.
RALLENTAMENTO = 0.40    # 0.75 = una quarta giusta sotto, e 25% piu' lento
TAGLIO_ALTE = 2600.0     # oltre questa frequenza si smorza: e' li' che vive
                         # lo schiocco del martelletto, cioe' l'attacco duro
LARGHEZZA_TAGLIO = 0.8   # quanto e' morbida la discesa oltre il taglio


def _rallenta(dati, fattore):
    """Riproduce piu' lentamente ricampionando. Non e' un time-stretch: la
    velocita' e l'altezza scendono INSIEME, ed e' proprio quello che serve —
    note piu' gravi e meno fitte con una sola operazione."""
    n_nuovo = int(len(dati) / fattore)
    vecchi = np.arange(len(dati), dtype=np.float64)
    nuovi = np.linspace(0.0, len(dati) - 1, n_nuovo)
    return np.stack(
        [np.interp(nuovi, vecchi, dati[:, c]) for c in range(dati.shape[1])],
        axis=1).astype(np.float32)


def _scurisci(dati, sr, taglio=TAGLIO_ALTE, larghezza=LARGHEZZA_TAGLIO):
    """Smorza le frequenze alte con una discesa morbida.

    Serve agli attacchi: la parte percussiva di una nota di pianoforte vive in
    alto, e togliendola le note sembrano entrare invece che colpire. Fatto in
    frequenza e non con un filtro campione per campione, che in Python puro
    su milioni di campioni sarebbe lentissimo."""
    n = len(dati)
    freq = np.fft.rfftfreq(n, 1.0 / sr)
    maschera = np.clip((taglio * (1.0 + larghezza) - freq) / (taglio * larghezza), 0.0, 1.0)
    maschera = (maschera ** 2).astype(np.float32)
    fuori = np.empty_like(dati)
    for c in range(dati.shape[1]):
        fuori[:, c] = np.fft.irfft(np.fft.rfft(dati[:, c]) * maschera, n=n)
    return fuori


def _ammorbidisci(dati, sr):
    """La voce del tappeto: piu' grave, piu' rada, con attacchi piu' lenti."""
    dati = _rallenta(dati, RALLENTAMENTO)
    dati = _scurisci(dati, sr)
    picco = float(np.abs(dati).max())
    if picco > 1e-6:
        dati *= 0.9 / picco      # il filtro cambia il livello: si rinormalizza
    return dati


def _densita_attacchi(dati, sr):
    """Quanti attacchi al secondo: serve a scegliere la traccia piu' rada."""
    mono = dati.mean(axis=1)
    n = int(sr * 0.02)
    finestre = len(mono) // n
    if finestre < 2:
        return 0.0
    energia = np.sqrt((mono[:finestre * n].reshape(finestre, n) ** 2).mean(axis=1))
    salti = np.diff(energia)
    return float((salti > energia.mean() * 0.35).sum()) / (len(mono) / sr)


def _rendi_ciclabile(dati, sr, secondi=CODA_CUCITURA):
    """Prepara una traccia perche' possa girare in loop senza che si senta.

    Due passaggi. Prima si TAGLIA il silenzio finale: queste tracce sfumano a
    zero perche' sono nate per essere ascoltate una volta sola, e ripetendole
    si sentirebbe un buco seguito da una ripartenza di colpo. Poi si CUCE la
    coda sulla testa con una dissolvenza incrociata, cosi' la fine scivola
    dentro l'inizio invece di sbatterci contro."""
    livello = np.abs(dati).max(axis=1)
    if livello.max() <= 0:
        return dati
    acceso = np.nonzero(livello > livello.max() * 0.01)[0]
    if acceso.size:
        dati = dati[acceso[0]:acceso[-1] + 1]

    n = int(secondi * sr)
    if n < 1 or n * 2 >= len(dati):
        return dati
    rampa = np.linspace(0.0, 1.0, n, dtype=np.float32)[:, None]
    testa = dati[:n] * rampa + dati[-n:] * (1.0 - rampa)
    return np.concatenate([testa, dati[n:-n]])


def _pick_file(emotion, library=LIBRARY, piu_rada=False):
    files = glob.glob(os.path.join(library, emotion, "*.wav"))
    if not files:                                   # fallback: any track
        files = glob.glob(os.path.join(library, "*", "*.wav"))
    if not files:
        return None
    if piu_rada:
        # per il tappeto si sceglie la traccia con MENO attacchi: fra le
        # quattro del quadrante la differenza e' piu' del doppio, e sotto le
        # scritte deve stare la piu' silenziosa, non una a caso
        return min(files, key=lambda f: _densita_attacchi(*_load_wav(f)))
    return random.choice(files)


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

    def play(self, emotion, fade=3.0, loop=True, volume=1.0, morbido=False):
        """morbido=True e' la voce del tappeto: piu' grave, piu' rada, con
        attacchi piu' lenti. La traccia della meditazione resta com'e'."""
        path = _pick_file(emotion, self.library, piu_rada=morbido)
        if not path:
            print("music: no track in library, skipping"); return None
        data, sr = _load_wav(path)
        if morbido:
            data = _ammorbidisci(data, sr)
        if loop:
            data = _rendi_ciclabile(data, sr)
        with self._lock:
            self._data, self._pos, self._loop = data, 0, loop
            self._gain = 0.0 if fade > 0 else volume
            self._gain_target = float(volume)
            self._gain_step = (float(volume) / (fade * sr)) if fade > 0 else 0.0
        if not self.apri(sr):
            return None
        print(f"music: {os.path.basename(path)} ({emotion})"
              + (" [tappeto ammorbidito]" if morbido else ""))
        return path

    def apri(self, sr=SAMPLE_RATE):
        """Apre il flusso audio, se non lo e' gia'.

        Aprire e chiudere un flusso mentre un altro suona fa riconfigurare la
        scheda audio, e si sente come un click. Per questo il flusso si apre
        una volta sola e resta aperto per tutta la sessione, anche quando non
        ha nulla da suonare: a quel punto il callback riempie di silenzio."""
        if self._stream is not None:
            return True
        try:
            import sounddevice as sd
            self._stream = sd.OutputStream(samplerate=sr, channels=2,
                                           blocksize=BLOCCO, latency="high",
                                           callback=self._callback)
            self._stream.start()
            return True
        except Exception as e:
            print(f"music: audio not available ({e})")
            self._stream = None
            return False

    def volume(self, livello, fade=2.0):
        """Porta il volume a un livello qualsiasi, con una rampa.

        E' cosi' che il tappeto si abbassa quando l'utente deve parlare e
        risale dopo: la rampa e' contata in campioni dentro il callback audio,
        quindi non dipende dal ritmo del ciclo principale e non produce scatti."""
        livello = float(max(0.0, min(1.0, livello)))
        with self._lock:
            self._gain_target = livello
            if fade > 0:
                self._gain_step = (livello - self._gain) / (fade * SAMPLE_RATE)
            else:
                self._gain, self._gain_step = livello, 0.0

    def fade_out(self, seconds=5.0):
        """Sfuma fino al silenzio, ma NON chiude il flusso.

        Chiuderlo qui faceva riconfigurare la scheda audio mentre il tappeto
        stava ancora suonando, e si sentiva un click qualche secondo dopo la
        fine della meditazione. Un flusso muto non costa nulla: si chiude
        tutto insieme a fine sessione."""
        self.volume(0.0, fade=seconds)

    def stop(self, dissolvenza=0.06):
        """Chiude il flusso. La rampa di pochi centesimi non si sente come una
        dissolvenza, ma evita il taglio netto sull'onda — che invece si sente
        eccome, come uno schiocco."""
        if self._stream is None:
            return
        if dissolvenza > 0:
            self.volume(0.0, fade=dissolvenza)
            time.sleep(dissolvenza + 0.04)
        try:
            self._stream.stop(); self._stream.close()
        except Exception:
            pass
        self._stream = None
