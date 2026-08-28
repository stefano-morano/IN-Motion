"""
Lo stacco: la musica si fa da parte, la campana, il ritorno.

Ad ogni cambio di scena guidato dagli occhi la musica si abbassa, suona la
campana, e poi la musica risale. E' il gesto che in radio si chiama proprio
"stacco", e serve a una cosa sola: rendere il passaggio UN EVENTO invece di un
dettaglio.

PERCHE' NON BASTAVA SOVRAPPORRE. Una campana suonata SOPRA la musica a pieno
volume e' un suono in piu' fra i tanti: l'orecchio la registra come parte del
tessuto, non come un annuncio. E' il contrasto a fare la firma, non la
campana. Lo stesso principio per cui un attore abbassa la voce per farsi
ascoltare.

MA NEMMENO IL SILENZIO. Portare la musica a zero funziona troppo bene: la
campana suona in un vuoto assoluto e il passaggio si sente come
un'interruzione, come se qualcosa si fosse rotto. Sotto resta percio' un filo
di musica — abbastanza da tenere la campana dentro il pezzo, poca abbastanza
da lasciarle il primo piano.

TRE TEMPI, e nessuno dei tre blocca il ciclo principale:

    discesa   la musica scende al filo           ~2.2 s
    respiro   la campana, sopra quel filo        ~1.4 s
    ritorno   la musica risale da sola           ~2.2 s

Il ritorno comincia mentre la coda della campana e' ancora viva (dura 3.6 s):
la musica rientra SOTTO il suono che si sta spegnendo, invece di aspettare
che sia finito. Aspettare il silenzio completo darebbe un buco, e un buco in
una meditazione si sente come un guasto.

COME SI INTRECCIA CON LA SCENA. Lo stacco non sa e non deve sapere a che
volume tornera' la musica: usa attenua(), che e' un MOLTIPLICATORE. Abbassa a
una frazione e poi rimette 1.0, e nel frattempo la macchina a stati e'
liberissima di cambiare il volume di scena — magari proprio perche' quel
cambio di scena e' la ragione dello stacco. I due valori si moltiplicano e
ognuno arriva dove voleva.
"""

import campanella

DISCESA = 2.2      # secondi per abbassare la musica
RESPIRO = 1.4      # secondi di sola campana, prima che la musica rientri
RITORNO = 2.2      # secondi per riportare la musica dov'era

# Discesa e ritorno durano uguale di proposito: la musica se ne va con la
# stessa calma con cui torna. A 0.8 secondi la discesa si sentiva come uno
# strappo — troppo vicina a un taglio per leggersi come un gesto.

# Quanto resta della musica sotto la campana, come MOLTIPLICATORE del volume
# di scena. Chi costruisce lo Stacco puo' passarne un altro: e' lui a sapere
# fra quali due livelli assoluti si sta muovendo, non questo modulo.
ATTENUAZIONE = 0.43

DURATA = DISCESA + RESPIRO + RITORNO


class Stacco:
    """Coordina discesa, campana e ritorno su una o piu' sorgenti musicali.

    Da chiamare ad ogni fotogramma con aggiorna(): come la macchina a stati
    grande, questa non dorme e non aspetta. Se dormisse, per tutta la durata
    dello stacco le particelle resterebbero immobili."""

    def __init__(self, sorgenti, sr=44100, attenuazione=ATTENUAZIONE,
                 discesa=DISCESA, respiro=RESPIRO, ritorno=RITORNO):
        self.sorgenti = tuple(sorgenti)
        self.attenuazione = attenuazione
        self.discesa = discesa
        self.respiro = respiro
        self.ritorno = ritorno

        # le due campane si calcolano una volta sola, adesso: sintetizzarle al
        # momento del cambio aggiungerebbe un ritardo proprio dove serve
        # immediatezza
        self.campana_chiusura, self.campana_apertura = campanella.coppia(sr)

        self._fase = None
        self._t_fase = 0.0
        self._campana = None

    # ---------- comandi ----------

    def avvia(self, ora, chiusura):
        """Fa partire lo stacco. chiusura=True suona la campana grave.

        Se uno stacco e' gia' in corso questo lo sostituisce dall'inizio: due
        stacchi sovrapposti darebbero due campane insieme e due dissolvenze
        che si contraddicono."""
        self._campana = (self.campana_chiusura if chiusura
                         else self.campana_apertura)
        for sorgente in self.sorgenti:
            sorgente.attenua(self.attenuazione, fade=self.discesa)
        self._fase = "discesa"
        self._t_fase = ora

    def annulla(self, ora=None):
        """Riporta subito la musica com'era e dimentica lo stacco in corso.

        Serve a fine sessione: uno stacco interrotto a meta' lascerebbe la
        musica abbassata per sempre."""
        if self._fase is None:
            return
        for sorgente in self.sorgenti:
            sorgente.attenua(1.0, fade=0.3)
        self._fase = None

    # ---------- il ciclo lo chiama ad ogni fotogramma ----------

    def aggiorna(self, ora):
        if self._fase is None:
            return
        trascorso = ora - self._t_fase

        if self._fase == "discesa":
            if trascorso >= self.discesa:
                # la musica e' scesa: adesso la campana ha il primo piano
                self.sorgenti[0].suona_campione(self._campana)
                self._fase, self._t_fase = "respiro", ora

        elif self._fase == "respiro":
            if trascorso >= self.respiro:
                for sorgente in self.sorgenti:
                    sorgente.attenua(1.0, fade=self.ritorno)
                self._fase, self._t_fase = "ritorno", ora

        elif self._fase == "ritorno":
            if trascorso >= self.ritorno:
                self._fase = None

    # ---------- stato ----------

    @property
    def attivo(self):
        return self._fase is not None

    @property
    def fase(self):
        return self._fase
