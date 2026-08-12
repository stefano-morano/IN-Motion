"""
Genera il materiale della meditazione a partire da cio' che l'utente ha raccontato:
due frasi da mostrare durante la danza delle particelle e un concetto finale su cui
meditare.

Viene chiamato UNA VOLTA SOLA, prima che l'animazione cominci: mentre le particelle
si muovono non deve mai esserci una chiamata di rete in corso.

Se l'API non risponde (rete assente, chiave mancante, errore, rifiuto del modello)
si usano le frasi di riserva scritte a mano: l'esperienza non si ferma mai.
"""

import json
import os

import anthropic

MODELLO = "claude-opus-5"

# La generazione e' un compito breve e creativo, non un problema difficile:
# 'low' riduce l'attesa, che qui e' la cosa che pesa di piu' sull'esperienza.
IMPEGNO = "low"
MAX_TOKEN = 4000

# Quanto puo' essere lunga una frase prima di diventare illeggibile a
# particelle. Misurato guardando il render, non stimato: a 47 caratteri la
# scritta va su tre righe e si legge ancora, quindi 42 (la lunghezza delle
# scritte fisse gia' in uso) sta comodamente dentro.
MAX_CARATTERI = 42

# Se il modello sfora, gli si richiede UNA volta dicendogli cosa correggere.
# Un secondo tentativo mirato riesce quasi sempre, e costa molto meno che
# rinunciare a frasi scritte sul racconto vero.
TENTATIVI = 2

# Usate se l'API non risponde. Devono funzionare per chiunque, senza sapere
# nulla di chi sta meditando.
RISERVA = {
    "frase_1": "QUELLO CHE SENTI E' GIA' TUO",
    "frase_2": "NON DEVI RISOLVERLO ADESSO",
    "concetto": "OGGI: RESTARE",
    "segnale_disagio": False,
    "mandala_petali": 6,
    "mandala_anelli": 3,
    "mandala_tonalita": 200.0,   # un blu-verde neutro
}

ISTRUZIONI = """Sei la voce di un'installazione di meditazione. Una persona ti ha \
appena raccontato come si sente. Dalle sue parole ricavi il materiale della sua \
meditazione.

Devi produrre:
- due frasi brevi, che le verranno mostrate una dopo l'altra mentre si prepara
- un concetto finale su cui si impegnera' a meditare
- i tratti di base di un mandala che rappresenti il suo stato d'animo, che vedra' \
alla fine della sessione: quanti petali (simmetria), quanti anelli concentrici, \
e una tonalita' di colore

Come devono essere le frasi:
- MOLTO brevi: massimo 42 caratteri ciascuna, spazi inclusi. Vengono disegnate \
con delle particelle: piu' lunghe diventano illeggibili. Sono circa 6 parole \
corte. Conta i caratteri prima di rispondere, e se una frase sfora riscrivila \
piu' corta invece di consegnarla lunga: una frase troppo lunga viene scartata \
e la persona ricevera' una frase generica al posto della sua.
- tutto in MAIUSCOLO, senza punto finale
- rivolte a lei, dandole del tu
- concrete e legate a quello che ha raccontato, non massime generiche
- il concetto finale nella forma "OGGI: ..." seguito da una o due parole

Il tono: caldo, diretto, mai giudicante. Niente frasi da poster motivazionale, \
niente promesse che andra' tutto bene, niente imperativi che suonino come ordini. \
Non minimizzare quello che ha detto ("non e' niente", "passera'"): riconoscilo.

Come scegliere il mandala: e' la forma di base, non quella finale (la sessione di \
meditazione la arricchira' con altri dettagli, che non decidi tu). Scegli:
- mandala_petali: tra 5 e 9, piu' alto se il racconto suggerisce agitazione o \
molti pensieri contemporanei, piu' basso se suggerisce calma o un solo pensiero fisso
- mandala_anelli: tra 2 e 4, piu' alto se il racconto e' stratificato o di lunga data, \
piu' basso se e' un episodio semplice e isolato
- mandala_tonalita: un numero tra 0 e 359 (gradi di tonalita' colore), scelto per \
evocare l'emozione prevalente — non serve seguire convenzioni rigide (es. rosso=rabbia), \
scegli cio' che senti piu' giusto per il racconto specifico

Se dalle sue parole emerge una sofferenza seria — pensieri di farsi del male, \
disperazione profonda, una crisi in corso — non rispondere con frasi \
motivazionali: sarebbero fuori luogo. Usa invece frasi che la riportino al \
presente e al corpo (il respiro, il peso, il posto in cui si trova), senza \
chiederle di risolvere nulla, e segnala il caso con segnale_disagio a true. In \
questo caso scegli un mandala piu' semplice e una tonalita' piu' quieta."""

SCHEMA = {
    "type": "object",
    "properties": {
        "frase_1": {"type": "string"},
        "frase_2": {"type": "string"},
        "concetto": {"type": "string"},
        "segnale_disagio": {
            "type": "boolean",
            "description": (
                "true se dal racconto emerge sofferenza seria e l'esperienza "
                "dovrebbe cambiare tono"
            ),
        },
        # Niente minimum/maximum qui: gli output strutturati non li accettano
        # (errore 400). I limiti sono scritti nelle istruzioni e, se il modello
        # sfora lo stesso, li rimettiamo in riga noi con _entro_limiti().
        "mandala_petali": {
            "type": "integer",
            "description": "numero di petali del mandala, da 5 a 9",
        },
        "mandala_anelli": {
            "type": "integer",
            "description": "numero di anelli concentrici, da 2 a 4",
        },
        "mandala_tonalita": {
            "type": "number",
            "description": "tonalita' del colore in gradi, da 0 a 359",
        },
    },
    "required": [
        "frase_1", "frase_2", "concetto", "segnale_disagio",
        "mandala_petali", "mandala_anelli", "mandala_tonalita",
    ],
    "additionalProperties": False,
}


CAMPI_TESTO = ("frase_1", "frase_2", "concetto")


def _sforate(materiale):
    """Le frasi troppo lunghe per le particelle, con la loro lunghezza."""
    return [
        (campo, materiale[campo], len(materiale[campo]))
        for campo in CAMPI_TESTO
        if len(materiale[campo]) > MAX_CARATTERI
    ]


def _correzione(sforate):
    """Il messaggio da rimandare al modello: gli si dice esattamente cosa non
    andava, invece di richiedere la stessa cosa e sperare."""
    elenco = "\n".join(
        f'- {campo}: "{testo}" ({lunghezza} caratteri)'
        for campo, testo, lunghezza in sforate
    )
    return (
        "Il tentativo precedente non e' utilizzabile: queste frasi superano i "
        f"{MAX_CARATTERI} caratteri e verrebbero disegnate illeggibili.\n"
        f"{elenco}\n"
        "Riscrivile piu' corte mantenendo lo stesso senso, e ricontrolla che "
        "TUTTE stiano nel limite."
    )


def _entro_limiti(materiale):
    """Riporta i parametri del mandala dentro l'intervallo utile. Un valore
    sballato viene corretto, non fatto fallire: non vale la pena buttare via
    delle frasi buone perche' il modello ha scritto 12 petali invece di 9."""
    materiale["mandala_petali"] = max(5, min(9, int(materiale["mandala_petali"])))
    materiale["mandala_anelli"] = max(2, min(4, int(materiale["mandala_anelli"])))
    materiale["mandala_tonalita"] = float(materiale["mandala_tonalita"]) % 360.0
    return materiale


def _chiedi(client, racconto, correzione=None):
    """Una singola richiesta al modello. Ritorna il materiale grezzo, oppure
    None se il modello ha declinato."""
    contenuto = racconto if correzione is None else f"{racconto}\n\n{correzione}"
    risposta = client.messages.create(
        model=MODELLO,
        max_tokens=MAX_TOKEN,
        system=ISTRUZIONI,
        output_config={
            "format": {"type": "json_schema", "schema": SCHEMA},
            "effort": IMPEGNO,
        },
        messages=[{"role": "user", "content": contenuto}],
    )

    # Il modello puo' declinare la richiesta: in quel caso content e' vuoto
    # o parziale, quindi va controllato PRIMA di leggerlo.
    if risposta.stop_reason == "refusal":
        return None

    testo = next(b.text for b in risposta.content if b.type == "text")
    return json.loads(testo)


def genera(racconto: str) -> dict:
    """Restituisce {frase_1, frase_2, concetto, segnale_disagio, mandala_*}.
    Non solleva mai eccezioni: in caso di problemi ritorna le frasi di riserva."""
    if not racconto.strip():
        return dict(RISERVA)

    correzione = None
    try:
        client = anthropic.Anthropic()
        for tentativo in range(1, TENTATIVI + 1):
            materiale = _chiedi(client, racconto, correzione)
            if materiale is None:
                print("[testi] richiesta declinata dal modello, uso le frasi di riserva")
                return dict(RISERVA)

            # Lo schema garantisce i campi, non la loro lunghezza: quella si
            # controlla qui, e se sfora si richiede dicendo cosa correggere.
            sforate = _sforate(materiale)
            if not sforate:
                return _entro_limiti(materiale)

            for campo, testo, lunghezza in sforate:
                print(f'[testi] "{testo}" e\' lunga {lunghezza} (max {MAX_CARATTERI})')
            if tentativo < TENTATIVI:
                print("[testi] richiedo frasi piu' corte...")
                correzione = _correzione(sforate)

    except Exception as errore:
        print(f"[testi] generazione fallita ({errore}), uso le frasi di riserva")
        return dict(RISERVA)

    print("[testi] frasi ancora troppo lunghe, uso quelle di riserva")
    return dict(RISERVA)


if __name__ == "__main__":
    import sys

    racconto = " ".join(sys.argv[1:])
    if not racconto:
        racconto = input("Racconta come ti senti: ")

    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("Attenzione: ANTHROPIC_API_KEY non e' impostata.\n")

    materiale = genera(racconto)
    print()
    print(f"  frase 1:  {materiale['frase_1']}")
    print(f"  frase 2:  {materiale['frase_2']}")
    print(f"  concetto: {materiale['concetto']}")
    print(
        f"  mandala:  {materiale['mandala_petali']} petali, "
        f"{materiale['mandala_anelli']} anelli, tonalita' {materiale['mandala_tonalita']:.0f}°"
    )
    if materiale["segnale_disagio"]:
        print("\n  ⚠ il modello ha segnalato una possibile sofferenza seria")
