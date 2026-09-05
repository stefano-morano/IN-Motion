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
    "frase_1": "WHAT YOU FEEL IS ALREADY YOURS",
    "frase_2": "YOU DON'T HAVE TO SOLVE IT NOW",
    "concetto": "TODAY: STAY",
    "segnale_disagio": False,
    "mandala_petali": 6,
    "mandala_anelli": 3,
    "mandala_tonalita": 200.0,   # un blu-verde neutro
    # Q2 (teso-agitato) e' il ripiego piu' sicuro: la sua musica va incontro
    # all'energia di chi ascolta e poi la accompagna giu'. Se non sappiamo
    # nulla della persona, e' il viaggio che funziona per piu' gente.
    "emozione": "Q2",
}

# Il prompt e' in inglese perche' in inglese sono le frasi che deve produrre:
# chiedere in una lingua e farsi rispondere in un'altra funziona, ma aggiunge
# un passaggio dove non serve. I nomi dei campi restano italiani — sono
# l'interfaccia con esperienza.py, non testo che qualcuno legge.
ISTRUZIONI = """You are the voice of a meditation installation. Someone has \
just told you how they feel. From their words you draw the material of their \
meditation.

You must produce:
- two short lines, shown to them one after the other while they settle
- a final thought they will commit to meditating on
- the basic traits of a mandala representing their state of mind, which they \
will see at the end of the session: how many petals (symmetry), how many \
concentric rings, and a colour hue

How the lines must be:
- VERY short: at most 42 characters each, spaces included. They are drawn with \
particles: any longer and they become illegible. That is roughly 6 short \
words. Count the characters before answering, and if a line runs over, rewrite \
it shorter instead of delivering it long: a line that is too long gets \
discarded and the person receives a generic one instead of their own.
- ALL CAPITALS, no full stop at the end
- addressed to them directly, as "you"
- concrete and tied to what they said, not generic maxims
- the final thought in the form "TODAY: ..." followed by one or two words

The tone: warm, direct, never judging. No motivational-poster lines, no \
promises that everything will be fine, no imperatives that sound like orders. \
Do not minimise what they said ("it's nothing", "it will pass"): acknowledge it.

A line is also SPOKEN ALOUD by a guiding voice while the particles form it. \
Write words that sound right said slowly, out loud, to someone with their eyes \
closed — not words that only read well.

How to choose the mandala: it is the basic form, not the final one (the \
meditation session will enrich it with further detail, which you do not \
decide). Choose:
- mandala_petali: between 5 and 9, higher if the account suggests agitation or \
many simultaneous thoughts, lower if it suggests calm or a single fixed thought
- mandala_anelli: between 2 and 4, higher if the account is layered or \
long-standing, lower if it is a simple, isolated episode
- mandala_tonalita: a number between 0 and 359 (colour hue degrees), chosen to \
evoke the prevailing emotion — no need to follow rigid conventions \
(e.g. red=anger), choose what feels right for this particular account

If serious suffering emerges from their words — thoughts of self-harm, deep \
despair, a crisis under way — do not answer with motivational lines: they \
would be out of place. Use instead lines that bring them back to the present \
and to the body (the breath, their weight, the place they are in), without \
asking them to solve anything, and flag the case with segnale_disagio set to \
true. In that case choose a simpler mandala and a quieter hue."""

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
        # (errore 400 "For 'integer' type, properties maximum, minimum are not
        # supported"). I limiti sono scritti nelle istruzioni e, se il modello
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
        "emozione": {
            "type": "string",
            "enum": ["Q1", "Q2", "Q3", "Q4"],
            "description": (
                "lo stato dell'utente dal suo racconto: "
                "Q1 felice-attivo, Q2 teso-agitato, Q3 triste-spento, Q4 calmo"
            ),
        },
    },
    "required": [
        "frase_1", "frase_2", "concetto", "segnale_disagio",
        "mandala_petali", "mandala_anelli", "mandala_tonalita",
        "emozione",
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
        f'- {campo}: "{testo}" ({lunghezza} characters)'
        for campo, testo, lunghezza in sforate
    )
    return (
        "The previous attempt is unusable: these lines exceed "
        f"{MAX_CARATTERI} characters and would be drawn illegible.\n"
        f"{elenco}\n"
        "Rewrite them shorter, keeping the same meaning, and check again that "
        "ALL of them fit within the limit."
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
        racconto = input("Tell me how you feel: ")

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
