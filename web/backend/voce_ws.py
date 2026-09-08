"""
VoceWS — the spoken guide, on the web.

No longer a silent stub. It reuses visuals/voce.py entirely — same on-disk
cache, same voice selection, same signature — and changes one thing only:
instead of playing the clip on a local audio stream, it sends the URL to
the browser.

WHY IT WAS MUTE AND WHY THAT WASN'T ENOUGH. While VoceWS answered 0.0 from
durata(), it wasn't only the voice that was missing: the RHYTHM of the piece
disappeared too. In esperienza.py how long a line stays on screen is the time
the voice takes to say it (see _permanenza), so without clips every phrase
fell back to the minimum readable duration and the experience raced ahead.
Voice is not ornament on top of the sequence: it is what paces it.

THE CACHE DOES THE HEAVY LIFTING. Fixed lines have already been synthesized
once and live in visuals/voce_cache/. Nothing already present is
re-synthesized here, and the clips work for BOTH versions of the piece: the
same fingerprint, the same file.
"""

import queue as _q

import voce as _voce


class VoceWS(_voce.Voce):
    """Like Voce, but sound comes from the browser instead of the audio card.

    Inherit rather than reimplement because everything that matters —
    finding the clip in cache, measuring its duration, synthesizing missing
    ones — has nothing to do with HOW it is played. Only the methods that
    touch the local audio stream need replacing.
    """

    def __init__(self, coda: _q.SimpleQueue, sorgenti_da_abbassare=(), **kw):
        super().__init__(sorgenti_da_abbassare=sorgenti_da_abbassare, **kw)
        self._coda = coda

    # ---- local audio stream is unused: the browser plays ----

    def apri(self):
        return True

    def _abbassa_la_musica(self):
        pass

    def _rialza_la_musica(self):
        pass

    def aggiorna(self, ora=None):
        # On desktop this advances the clip queue. On the web the browser owns
        # the queue and knows on its own when a clip has finished.
        pass

    # ---- what actually changes ----

    def di(self, testo):
        """Send the browser the clip to speak, and return how long it will last.

        Python needs the duration too: it is what keeps the line on screen
        until it has been fully read.
        """
        percorso, _ = self._percorso(testo)
        if not percorso:
            return 0.0
        durata = self.durata(testo)
        if not durata:
            # no clip: continue muted, exactly as the desktop version does
            # when the key or the network is missing
            return 0.0
        import os
        self._coda.put({
            "tipo": "voce",
            "azione": "di",
            "url": "/voce/" + os.path.basename(percorso),
            "durata": float(durata),
            # how much to duck the music while speaking. Its OWN multiplier,
            # separate from the stacco one: so voice and stacco can overlap
            # and each still ends up where it intended.
            "attenuazione": float(self.attenuazione),
            "volume": float(self.volume),
        })
        return durata

    def zittisci(self):
        """Cut the clip in progress. Done before opening the mic:
        a phrase still being spoken would end up in the recording."""
        self._coda.put({"tipo": "voce", "azione": "zittisci"})

    def stop(self):
        self.zittisci()
