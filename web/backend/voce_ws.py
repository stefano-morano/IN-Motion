"""
VoceWS — la guida vocale, sul web.

Non e' piu' uno stub muto. Riusa per intero visuals/voce.py — stessa cache su
disco, stessa scelta della voce, stessa firma — e cambia una cosa sola: invece
di suonare la clip su un flusso audio locale, ne manda l'indirizzo al browser.

PERCHE' ERA MUTO E PERCHE' NON BASTAVA. Finche' VoceWS rispondeva 0.0 a
durata(), non mancava solo la voce: spariva anche il RITMO dell'opera. In
esperienza.py quanto una scritta resta a schermo e' il tempo che la voce
impiega a dirla (vedi _permanenza), quindi senza clip ogni frase ricadeva sul
minimo leggibile e l'esperienza sfrecciava. La voce non e' un ornamento sopra
la sequenza: e' cio' che la detta.

LA CACHE FA IL GROSSO. Le scritte fisse sono gia' state sintetizzate una volta
e stanno in visuals/voce_cache/. Qui non si risintetizza niente che ci sia
gia', e le clip valgono per ENTRAMBE le versioni dell'opera: la stessa
impronta, lo stesso file.
"""

import queue as _q

import voce as _voce


class VoceWS(_voce.Voce):
    """Come Voce, ma il suono esce dal browser invece che dalla scheda audio.

    Si eredita invece di reimplementare perche' tutto quello che serve —
    trovare la clip in cache, misurarne la durata, sintetizzare quelle che
    mancano — non ha niente a che vedere con COME la si suona. Restano da
    sostituire solo i metodi che toccano il flusso audio locale.
    """

    def __init__(self, coda: _q.SimpleQueue, sorgenti_da_abbassare=(), **kw):
        super().__init__(sorgenti_da_abbassare=sorgenti_da_abbassare, **kw)
        self._coda = coda

    # ---- il flusso audio locale non serve: suona il browser ----

    def apri(self):
        return True

    def _abbassa_la_musica(self):
        pass

    def _rialza_la_musica(self):
        pass

    def aggiorna(self, ora=None):
        # Nella versione desktop qui si fa avanzare la coda delle clip. Sul web
        # la coda ce l'ha il browser, che sa da solo quando una clip e' finita.
        pass

    # ---- quello che cambia davvero ----

    def di(self, testo):
        """Manda al browser la clip da dire, e risponde quanto durera'.

        La durata la deve sapere anche il lato Python: e' quella che tiene la
        scritta a schermo finche' non e' stata letta per intero.
        """
        percorso, _ = self._percorso(testo)
        if not percorso:
            return 0.0
        durata = self.durata(testo)
        if not durata:
            # nessuna clip: si prosegue muti, esattamente come fa la versione
            # desktop quando manca la chiave o la rete
            return 0.0
        import os
        self._coda.put({
            "tipo": "voce",
            "azione": "di",
            "url": "/voce/" + os.path.basename(percorso),
            "durata": float(durata),
            # quanto abbassare la musica mentre parla. E' un moltiplicatore
            # SUO, separato da quello dello stacco: cosi' voce e stacco possono
            # capitare insieme e ognuno arriva dove voleva.
            "attenuazione": float(self.attenuazione),
            "volume": float(self.volume),
        })
        return durata

    def zittisci(self):
        """Tronca la clip in corso. Lo si fa prima di accendere il microfono:
        una frase ancora in bocca finirebbe nella registrazione."""
        self._coda.put({"tipo": "voce", "azione": "zittisci"})

    def stop(self):
        self.zittisci()
