"""
Attrezzo: scegli CHI legge.

    python3 voci.py                 le voci disponibili, con un campione
                                    da ascoltare per ognuna
    python3 voci.py cerca [parole]  cerca nella libreria pubblica, nella
                                    lingua dell'opera. Le parole filtrano:
                                    'cerca meditation calm'. Stampa un link
                                    per ognuna: si ascoltano dal browser,
                                    GRATIS, e si paga solo quella scelta
    python3 voci.py aggiungi <id>   aggiunge al tuo account una voce trovata
                                    con 'cerca'
    python3 voci.py scegli <nome>   fissa la voce dell'esperienza
    python3 voci.py prova [nome]    risintetizza il campione e lo suona
    python3 voci.py velocita [n...] la stessa frase a piu' velocita', in fila
    python3 voci.py confronta [chi] tre frasi vere dette da OGNI voce, con le
                                    impostazioni in uso. chi = female (di
                                    serie), male, tutte, oppure dei nomi:
                                    'confronta Lily George' ne rimette due
                                    a confronto senza risintetizzarle

La voce scelta finisce in voce_scelta.json, che voce.py legge all'avvio. Il
file tiene una scelta PER MOTORE: passare da ElevenLabs a Polly e tornare
indietro non cancella niente.

QUALE MOTORE. Lo decide VOCE_MOTORE (elevenlabs / polly); senza, vince il
primo configurato. Tutti i comandi qui sotto lavorano sul motore attivo —
tranne 'cerca' e 'aggiungi', che sono la libreria pubblica di ElevenLabs e
non hanno un corrispettivo in Polly (li' le voci italiane sono di serie, non
c'e' niente da aggiungere).

    VOCE_MOTORE=polly python3 voci.py       le voci italiane di Polly

PERCHE' UN ATTREZZO E NON UNA COSTANTE NEL CODICE. Le voci disponibili
dipendono dall'account, e quale sia "giusta" non si decide leggendo un nome:
si decide ascoltando. Percio' questo script non elenca e basta — sintetizza a
ciascuna candidata le FRASI VERE dell'opera, non un "buongiorno, questa e' una
prova". Una voce puo' essere bellissima su una frase di prova e sbagliata
sopra "chiudi gli occhi": e' il materiale a giudicarla.

Il campione costa crediti come tutto il resto, ma si fa una volta e resta in
voce_campioni/.
"""

import hashlib
import os
import sys

import voce as modulo_voce

CAMPIONI = os.path.join(modulo_voce.CARTELLA, "voce_campioni")
API = "https://api.elevenlabs.io/v1"

# Le frasi su cui si giudica. Sono quelle dell'opera, non un testo neutro:
# una e' un invito sussurrato, l'altra e' il concetto finale, secco.
PROVA = ["Close your eyes and tell me anything.", "Today: stay."]

# Le velocita' da confrontare col comando 'velocita'. Una sola frase, quattro
# letture: costa una cinquantina di crediti invece degli ottocento di una
# passata intera, ed e' l'unico modo onesto di scegliere questo numero —
# a orecchio, sul materiale vero.
VELOCITA_DA_PROVARE = (0.75, 0.85, 0.95, 1.0)
FRASE_VELOCITA = "Close your eyes and tell me anything."

# Il confronto vero fra voci non si fa su una frase: si fa su TRE, con in
# mezzo le pause dell'opera. Una voce puo' reggere benissimo un invito e
# cadere sul concetto finale, che e' secco e senza appigli.
ANTEPRIMA = [
    "Close your eyes and tell me anything.",
    "What you feel is already yours.",
    "Today: stay.",
]
PAUSA = 1.5      # come CODA_VOCE: si ascolta il ritmo, non solo il timbro


def _chiedi(percorso, corpo=None):
    """Una richiesta alla libreria pubblica. (chiave, dati) oppure (chiave, None).

    Passa da httpx e non da urllib, che pure basterebbe: urllib usa i
    certificati di sistema, e su macOS un Python installato da python.org non
    ne ha nessuno — la richiesta muore in CERTIFICATE_VERIFY_FAILED prima
    ancora di partire. httpx arriva con la libreria elevenlabs, che qui c'e'
    di sicuro, e si porta dietro i suoi."""
    chiave = _chiave()
    if not chiave:
        return None
    import httpx
    testa = {"xi-api-key": chiave}
    try:
        if corpo is None:
            risposta = httpx.get(API + percorso, headers=testa, timeout=30)
        else:
            risposta = httpx.post(API + percorso, headers=testa, json=corpo,
                                  timeout=30)
        risposta.raise_for_status()
        return risposta.json()
    except Exception as errore:
        codice = getattr(getattr(errore, "response", None), "status_code", None)
        if codice == 401:
            print("\nLa chiave non ha i permessi per questa operazione.")
            print("Su elevenlabs.io → API Keys → Edit, accendi 'Voices' "
                  "(read e write).\n")
        else:
            print(f"\nla libreria pubblica non risponde ({codice or errore}).")
            print("Puoi sfogliarla dal sito: elevenlabs.io/voice-library\n")
        return None


def _chiave():
    chiave = os.environ.get("ELEVENLABS_API_KEY", "").strip()
    if not chiave:
        print("\nELEVENLABS_API_KEY non e' impostata.")
        print('  export ELEVENLABS_API_KEY="..."   nel terminale,')
        print("  oppure la stessa riga in fondo a ~/.zshrc\n")
    return chiave


def _giovane_femminile(v):
    return ("female" in (v["genere"] or "").lower()
            and "young" in (v["eta"] or "").lower())


def _suona(percorso):
    try:
        import sounddevice as sd
        dati, sr = modulo_voce.modulo_musica._load_wav(percorso)
        sd.play(dati, sr)
        sd.wait()
    except Exception as errore:
        print(f"    (non riesco a suonarlo: {errore}) — apri {percorso}")


def _campione(guida, v, suona=False):
    """Sintetizza le frasi di prova con quella voce e ritorna il file."""
    os.makedirs(CAMPIONI, exist_ok=True)
    # Il nome porta con se' anche le FRASI di prova, non solo la voce. Senza,
    # cambiando PROVA — o la lingua dell'opera — si risentiva il campione
    # vecchio credendo di sentire quello nuovo: il file c'era, e nessuno
    # aveva motivo di sospettarlo.
    corto = v["nome"].split(" - ")[0].strip().replace(" ", "_")
    firma = hashlib.sha1("|".join(PROVA).encode("utf-8")).hexdigest()[:6]
    percorso = os.path.join(CAMPIONI, f"{corto}-{firma}.wav")
    if not os.path.exists(percorso):
        fornitore = guida.fornitore
        indietro = fornitore.voce_id
        fornitore.voce_id = v["id"]
        try:
            pezzi = [fornitore.sintetizza(f) for f in PROVA]
        finally:
            fornitore.voce_id = indietro
        pezzi = [p for p in pezzi if p is not None]
        if not pezzi:
            return None
        import numpy as np
        silenzio = np.zeros((int(0.7 * modulo_voce.SAMPLE_RATE), 2), dtype="float32")
        insieme = np.concatenate([x for p in pezzi for x in (p, silenzio)])
        modulo_voce._salva_wav(percorso, insieme)
    if suona:
        _suona(percorso)
    return percorso


# ---------- i comandi ----------

def elenca(con_campione=True):
    guida = modulo_voce.Voce()
    if not guida.disponibile:
        print(f"\nvoce non disponibile: {guida.fornitore.motivo}\n")
        return 1
    voci = guida.fornitore.voci()
    if not voci:
        print("\nNessuna voce sull'account.\n")
        return 1

    scelta = guida.fornitore.voce_id
    print(f"\nmotore: {guida.fornitore.nome_motore}")
    print(f"{len(voci)} voci disponibili. In uso ora: "
          f"{guida.fornitore.voce_nome}\n")
    candidate = [v for v in voci if _giovane_femminile(v)] or voci
    for v in voci:
        segno = "→" if v["id"] == scelta else " "
        corto = v["nome"].split(" - ")[0].strip()
        tratti = ", ".join(t for t in (v["genere"], v["eta"], v["accento"]) if t)
        print(f" {segno} {corto:<14} {tratti}")

    if con_campione:
        print(f"\nSintetizzo un campione per {len(candidate)} candidate "
              "(femminili giovani).")
        print("Le senti una alla volta; poi scegli con: python3 voci.py scegli <nome>\n")
        for v in candidate:
            print(f"  {v['nome']}...")
            _campione(guida, v, suona=True)
        print(f"\nI campioni restano in {CAMPIONI}\n")
    return 0


def _solo_elevenlabs():
    """True se si puo' procedere. La libreria pubblica e' roba di ElevenLabs."""
    if modulo_voce.MOTORE == "polly":
        print("\nLa libreria pubblica e' di ElevenLabs, e con VOCE_MOTORE=polly")
        print("non serve: le voci italiane di Polly sono di serie. Elencale con")
        print("  VOCE_MOTORE=polly python3 voci.py\n")
        return False
    return True


def cerca(parole=None):
    """La libreria pubblica: li' ci sono voci ITALIANE vere, mentre quelle di
    serie di ElevenLabs parlano italiano con l'accento della lingua in cui
    sono nate."""
    if not _solo_elevenlabs():
        return 1
    import urllib.parse
    filtri = {"language": modulo_voce.LINGUA, "page_size": "24",
              "sort": "trending"}
    if parole:
        filtri["search"] = " ".join(parole)
    dati = _chiedi("/shared-voices?" + urllib.parse.urlencode(filtri))
    if dati is None:
        return 1
    voci = dati.get("voices", [])
    if not voci:
        print("\nNessun risultato. Prova dal sito: elevenlabs.io/voice-library\n")
        return 0
    print("\nLe voci della libreria si SINTETIZZANO solo dai piani a pagamento")
    print("(sul gratuito la sintesi risponde 402), ma i link qui sotto si")
    print("aprono nel browser e si ascoltano GRATIS. Conviene decidere cosi',")
    print("e pagare solo quando si e' gia' scelto.\n")
    lingua = modulo_voce.LINGUA
    print(f"{len(voci)} voci in lingua '{lingua}'"
          + (f", filtrate per: {' '.join(parole)}" if parole else "") + ":\n")
    for v in voci:
        print(f"  {v.get('name', '?'):<20} {v.get('voice_id')}")
        descrizione = (v.get("description") or "").strip().replace("\n", " ")
        if descrizione:
            print(f"    {descrizione[:90]}")
        if v.get("preview_url"):
            print(f"    ascolta: {v['preview_url']}")
    print("\nPer aggiungerne una al tuo account:")
    print("  python3 voci.py aggiungi <voice_id>\n")
    return 0


def aggiungi(voce_id):
    """Copia una voce della libreria pubblica nel proprio account: prima di
    quel passaggio non e' utilizzabile dall'API."""
    if not _solo_elevenlabs():
        return 1
    dati = _chiedi(f"/shared-voices?language={modulo_voce.LINGUA}&page_size=100")
    if dati is None:
        return 1
    voci = dati.get("voices", [])

    trovata = next((v for v in voci if v.get("voice_id") == voce_id), None)
    if not trovata:
        print(f"\n{voce_id} non e' fra i risultati di 'cerca'.")
        print("Aggiungila dal sito (elevenlabs.io/voice-library), poi rilancia")
        print("  python3 voci.py\n")
        return 1

    proprietario = trovata.get("public_owner_id")
    nome = trovata.get("name", "voce")
    esito = _chiedi(f"/voices/add/{proprietario}/{voce_id}",
                    corpo={"new_name": nome})
    if esito is None:
        return 1
    corto = nome.split(" - ")[0].strip()
    print(f"\n'{nome}' aggiunta al tuo account.")
    print(f"  python3 voci.py scegli {corto}\n")
    return 0


def scegli(chi):
    guida = modulo_voce.Voce()
    if not guida.disponibile:
        print(f"\nvoce non disponibile: {guida.fornitore.motivo}\n")
        return 1
    voci = guida.fornitore.voci()
    trovata = modulo_voce.cerca_voce(voci, chi)
    if not trovata:
        print(f"\n'{chi}' non e' fra le voci del tuo account. Elencale con:")
        print("  python3 voci.py\n")
        return 1

    modulo_voce.salva_scelta(guida.fornitore.nome_motore,
                             trovata["id"], trovata["nome"])
    print(f"\nOra legge {trovata['nome']} "
          f"(motore {guida.fornitore.nome_motore}).")
    print("Le clip gia' in cache erano dette da un'altra: risintetizzale con")
    print("  python3 prepara_voce.py\n")
    return 0


def prova(chi=None):
    guida = modulo_voce.Voce()
    if not guida.disponibile:
        print(f"\nvoce non disponibile: {guida.fornitore.motivo}\n")
        return 1
    voci = guida.fornitore.voci()
    if chi:
        v = modulo_voce.cerca_voce(voci, chi)
        if not v:
            print(f"\n'{chi}' non c'e'.\n")
            return 1
    else:
        v = {"id": guida.fornitore.voce_id, "nome": guida.fornitore.voce_nome}
    print(f"\n{v['nome']}:")
    for frase in PROVA:
        print(f'  "{frase}"')
    _campione(guida, v, suona=True)
    print()
    return 0


def velocita(valori=None):
    """La stessa frase a piu' velocita', una dietro l'altra.

    Serve perche' la velocita' e' l'unica manopola che non si puo' giudicare
    da sola: 0.85 non vuol dire niente finche' non lo senti accanto a 0.95.
    E provarla cambiando la costante in voce.py costerebbe una passata intera
    di sintesi a ogni tentativo, perche' la velocita' entra nell'impronta
    della cache."""
    guida = modulo_voce.Voce()
    if not guida.disponibile:
        print(f"\nvoce non disponibile: {guida.fornitore.motivo}\n")
        return 1
    fornitore = guida.fornitore
    if not hasattr(fornitore, "velocita"):
        print("\nQuesto motore non regola la velocita'.\n")
        return 1

    valori = valori or VELOCITA_DA_PROVARE
    partenza = fornitore.velocita
    os.makedirs(CAMPIONI, exist_ok=True)
    print(f'\n{fornitore.voce_nome} dice "{FRASE_VELOCITA}"')
    print(f"(quella in uso ora e' {partenza})\n")
    try:
        for valore in valori:
            fornitore.velocita = valore
            nome = str(valore).replace(".", "_")
            percorso = os.path.join(CAMPIONI, f"velocita-{nome}.wav")
            if not os.path.exists(percorso):
                dati = fornitore.sintetizza(FRASE_VELOCITA)
                if dati is None:
                    continue
                modulo_voce._salva_wav(percorso, dati)
            print(f"  {valore}")
            _suona(percorso)
    finally:
        fornitore.velocita = partenza

    print("\nQuella che ti convince va messa in VELOCITA, in cima a voce.py")
    print("(POLLY_VELOCITA se usi Polly). Poi  python3 prepara_voce.py  :")
    print("cambiando la velocita' cambia l'impronta, e le clip si rifanno.\n")
    return 0


def _anteprima(fornitore, voce, suona=False):
    """Le tre frasi dette da questa voce, con le impostazioni IN USO ORA.

    Il nome del file porta la firma del fornitore — voce, modello, velocita',
    stabilita' — piu' le frasi: cambiando una qualunque di queste cose il
    campione si rifa' invece di ingannare chi ascolta."""
    import numpy as np
    os.makedirs(CAMPIONI, exist_ok=True)
    indietro = fornitore.voce_id
    fornitore.voce_id = voce["id"]
    try:
        corto = voce["nome"].split(" - ")[0].strip().replace(" ", "_")
        firma = hashlib.sha1(
            (fornitore.firma + "|".join(ANTEPRIMA)).encode("utf-8")
        ).hexdigest()[:6]
        percorso = os.path.join(CAMPIONI, f"anteprima-{corto}-{firma}.wav")
        if not os.path.exists(percorso):
            silenzio = np.zeros((int(PAUSA * modulo_voce.SAMPLE_RATE), 2),
                                dtype="float32")
            pezzi = []
            for frase in ANTEPRIMA:
                dati = fornitore.sintetizza(frase)
                if dati is None:
                    return None
                pezzi += [dati, silenzio]
            modulo_voce._salva_wav(percorso, np.concatenate(pezzi))
    finally:
        fornitore.voce_id = indietro
    if suona:
        _suona(percorso)
    return percorso


def _di_genere(elenco, chi):
    """Le voci del genere chiesto. L'etichetta di ElevenLabs e' 'male' e
    'female', e la seconda CONTIENE la prima: un filtro fatto con 'in' invece
    che con '==' restituisce tutte le donne insieme agli uomini, e non se ne
    accorge nessuno finche' non si contano."""
    if chi == "tutte":
        return list(elenco)
    return [v for v in elenco if (v["genere"] or "").lower() == chi]


def confronta(chi="female", suona=True, nomi=None):
    """Ogni voce dice le stesse tre frasi, di fila.

    Con le impostazioni in uso, non con quelle di serie: una voce si giudica
    a quella velocita' e a quella stabilita' li', non in astratto."""
    guida = modulo_voce.Voce()
    if not guida.disponibile:
        print(f"\nvoce non disponibile: {guida.fornitore.motivo}\n")
        return 1
    fornitore = guida.fornitore
    elenco = fornitore.voci()
    if nomi:
        # Il ballottaggio: due o tre voci rimesse una accanto all'altra. E'
        # il momento in cui si decide davvero, e non costa niente perche' le
        # clip ci sono gia' — a patto che le impostazioni non siano cambiate,
        # e se sono cambiate e' giusto che si rifacciano.
        femminili = [v for v in (modulo_voce.cerca_voce(elenco, n) for n in nomi) if v]
        mancanti = [n for n in nomi if not modulo_voce.cerca_voce(elenco, n)]
        if mancanti:
            print(f"\nnon trovate: {', '.join(mancanti)}")
        chi = ", ".join(v["nome"].split(" - ")[0].strip() for v in femminili)
    else:
        femminili = _di_genere(elenco, chi)
    if not femminili:
        print(f"\nnessuna voce '{chi}'\n")
        return 1

    dettaglio = getattr(fornitore, "velocita", "?")
    print(f"\n{len(femminili)} voci ({chi}), velocita' {dettaglio}, "
          f"stabilita' {getattr(fornitore, 'stabilita', '?')}")
    for frase in ANTEPRIMA:
        print(f'  "{frase}"')
    print()

    rifiutate = []
    for voce in femminili:
        corto = voce["nome"].split(" - ")[0].strip()
        print(f"  {corto}")
        if _anteprima(fornitore, voce, suona=suona) is None:
            rifiutate.append(corto)
    if rifiutate:
        print(f"\nnon sintetizzabili: {', '.join(rifiutate)}")
        print("(le voci prese dalla libreria pubblica non funzionano sul "
              "piano gratuito)")
    print(f"\nRestano in {CAMPIONI}: risentirle e' gratis.")
    print("Quando hai deciso:  python3 voci.py scegli <nome>\n")
    return 0


def main():
    argomenti = sys.argv[1:]
    if not argomenti:
        return elenca()
    comando, resto = argomenti[0], argomenti[1:]
    if comando == "cerca":
        return cerca(resto or None)
    if comando == "aggiungi" and resto:
        return aggiungi(resto[0])
    if comando == "scegli" and resto:
        return scegli(" ".join(resto))
    if comando == "prova":
        return prova(" ".join(resto) if resto else None)
    if comando == "confronta":
        chi = (resto[0].lower() if resto else "female")
        if chi in ("female", "male", "tutte"):
            return confronta(chi)
        return confronta(nomi=resto)
    if comando == "velocita":
        try:
            return velocita([float(v) for v in resto] or None)
        except ValueError:
            print("\nle velocita' sono numeri, es: python3 voci.py velocita 0.8 0.9\n")
            return 1
    print(__doc__)
    return 1


if __name__ == "__main__":
    sys.exit(main())
