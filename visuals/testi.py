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

# Con 13.664 particelle una frase piu' lunga di cosi' diventa illeggibile.
MAX_CARATTERI = 34

# Usate se l'API non risponde. Devono funzionare per chiunque, senza sapere
# nulla di chi sta meditando.
RISERVA = {
    "frase_1": "QUELLO CHE SENTI E' GIA' TUO",
    "frase_2": "NON DEVI RISOLVERLO ADESSO",
    "concetto": "OGGI: RESTARE",
    "segnale_disagio": False,
}

ISTRUZIONI = """Sei la voce di un'installazione di meditazione. Una persona ti ha \
appena raccontato come si sente. Dalle sue parole ricavi il materiale della sua \
meditazione.

Devi produrre:
- due frasi brevi, che le verranno mostrate una dopo l'altra mentre si prepara
- un concetto finale su cui si impegnera' a meditare

Come devono essere:
- MOLTO brevi: massimo 34 caratteri ciascuna, perche' vengono disegnate con delle \
particelle e piu' lunghe diventano illeggibili
- tutto in MAIUSCOLO, senza punto finale
- rivolte a lei, dandole del tu
- concrete e legate a quello che ha raccontato, non massime generiche
- il concetto finale nella forma "OGGI: ..." seguito da una o due parole

Il tono: caldo, diretto, mai giudicante. Niente frasi da poster motivazionale, \
niente promesse che andra' tutto bene, niente imperativi che suonino come ordini. \
Non minimizzare quello che ha detto ("non e' niente", "passera'"): riconoscilo.

Se dalle sue parole emerge una sofferenza seria — pensieri di farsi del male, \
disperazione profonda, una crisi in corso — non rispondere con frasi \
motivazionali: sarebbero fuori luogo. Usa invece frasi che la riportino al \
presente e al corpo (il respiro, il peso, il posto in cui si trova), senza \
chiederle di risolvere nulla, e segnala il caso con segnale_disagio a true."""

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
    },
    "required": ["frase_1", "frase_2", "concetto", "segnale_disagio"],
    "additionalProperties": False,
}


def _troppo_lunga(materiale):
    return any(
        len(materiale[campo]) > MAX_CARATTERI
        for campo in ("frase_1", "frase_2", "concetto")
    )


def genera(racconto: str) -> dict:
    """Restituisce {frase_1, frase_2, concetto, segnale_disagio}.
    Non solleva mai eccezioni: in caso di problemi ritorna le frasi di riserva."""
    if not racconto.strip():
        return dict(RISERVA)

    try:
        client = anthropic.Anthropic()
        risposta = client.messages.create(
            model=MODELLO,
            max_tokens=MAX_TOKEN,
            system=ISTRUZIONI,
            output_config={
                "format": {"type": "json_schema", "schema": SCHEMA},
                "effort": IMPEGNO,
            },
            messages=[{"role": "user", "content": racconto}],
        )

        # Il modello puo' declinare la richiesta: in quel caso content e' vuoto
        # o parziale, quindi va controllato PRIMA di leggerlo.
        if risposta.stop_reason == "refusal":
            print("[testi] richiesta declinata dal modello, uso le frasi di riserva")
            return dict(RISERVA)

        testo = next(b.text for b in risposta.content if b.type == "text")
        materiale = json.loads(testo)

    except Exception as errore:
        print(f"[testi] generazione fallita ({errore}), uso le frasi di riserva")
        return dict(RISERVA)

    # Lo schema garantisce i campi, non la loro lunghezza: se il modello e' andato
    # lungo la scritta sarebbe illeggibile, quindi meglio le frasi di riserva.
    if _troppo_lunga(materiale):
        print("[testi] frasi troppo lunghe per le particelle, uso quelle di riserva")
        return dict(RISERVA)

    return materiale


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
    if materiale["segnale_disagio"]:
        print("\n  ⚠ il modello ha segnalato una possibile sofferenza seria")
