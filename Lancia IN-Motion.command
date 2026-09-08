#!/bin/bash
# Double-clickable launcher for IN-Motion (macOS).
# Finder gives a minimal PATH — we must find a real Python with the deps.

DIR="$(cd "$(dirname "$0")" && pwd)"
BACKEND="$DIR/web/backend"
PORT=8080
LOG="/tmp/inmotion.log"
VERDE='\033[0;32m'; GIALLO='\033[1;33m'; ROSSO='\033[0;31m'; NC='\033[0m'

# Paths that Finder .command sessions often miss
export PATH="/Library/Frameworks/Python.framework/Versions/3.12/bin:/Library/Frameworks/Python.framework/Versions/Current/bin:/usr/local/bin:/opt/homebrew/bin:$PATH"

clear
echo ""
echo "  IN-Motion"
echo ""
echo "──────────────────────────────────────────────────────"
echo ""

# Prefer a Python that already has uvicorn (avoids the system 3.9 stub)
PYTHON=""
for candidate in \
    /Library/Frameworks/Python.framework/Versions/3.12/bin/python3 \
    /Library/Frameworks/Python.framework/Versions/Current/bin/python3 \
    /usr/local/bin/python3 \
    /opt/homebrew/bin/python3 \
    "$(command -v python3 2>/dev/null)"
do
    [ -n "$candidate" ] && [ -x "$candidate" ] || continue
    if "$candidate" -c "import uvicorn" &>/dev/null; then
        PYTHON="$candidate"
        break
    fi
done

if [ -z "$PYTHON" ]; then
    echo -e "${ROSSO}✗ Python con le dipendenze di IN-Motion non trovato.${NC}"
    echo "  Apri Terminale e lancia:"
    echo "    cd \"$BACKEND\""
    echo "    python3 -m pip install -r requirements.txt"
    echo ""
    read -r -p "  Premi Invio per chiudere..."
    exit 1
fi
echo -e "${VERDE}✓ $($PYTHON --version) ($PYTHON)${NC}"

# Install missing deps if needed
if ! "$PYTHON" -c "import fastapi, dotenv, anthropic" &>/dev/null; then
    echo -e "${GIALLO}⚠ Installo dipendenze...${NC}"
    "$PYTHON" -m pip install -r "$BACKEND/requirements.txt"
    if [ $? -ne 0 ]; then
        echo -e "${ROSSO}✗ Installazione fallita${NC}"
        read -r -p "Invio per chiudere..."
        exit 1
    fi
fi
echo -e "${VERDE}✓ Dipendenze OK${NC}"

# Load .env without breaking on special characters
if [ -f "$DIR/.env" ]; then
    set -a
    # shellcheck disable=SC1091
    source "$DIR/.env"
    set +a
    echo -e "${VERDE}✓ .env caricato${NC}"
fi

# Free the port if occupied
VECCHIO=$(lsof -ti :"$PORT" 2>/dev/null | tr '\n' ' ')
if [ -n "$VECCHIO" ]; then
    echo -e "${GIALLO}⚠ Fermo processo precedente sulla porta $PORT...${NC}"
    # shellcheck disable=SC2086
    kill -9 $VECCHIO 2>/dev/null
    sleep 0.5
fi

echo ""
echo "  Avvio server..."
cd "$BACKEND" || exit 1
: > "$LOG"
"$PYTHON" -m uvicorn server:app --host 0.0.0.0 --port "$PORT" >> "$LOG" 2>&1 &
SRV=$!

echo -n "  In attesa"
PRONTO=0
for _ in $(seq 1 60); do
    sleep 0.5
    echo -n "."
    CODE=$(curl -s -o /dev/null -w "%{http_code}" "http://127.0.0.1:$PORT/" 2>/dev/null || true)
    if [ "$CODE" = "200" ]; then
        PRONTO=1
        break
    fi
    if ! kill -0 "$SRV" 2>/dev/null; then
        echo ""
        echo -e "${ROSSO}✗ Il server si è fermato. Errore:${NC}"
        echo ""
        cat "$LOG"
        echo ""
        read -r -p "  Premi Invio per chiudere..."
        exit 1
    fi
done

if [ "$PRONTO" -eq 0 ]; then
    echo ""
    echo -e "${ROSSO}✗ Timeout. Errore:${NC}"
    cat "$LOG"
    kill "$SRV" 2>/dev/null
    read -r -p "  Premi Invio per chiudere..."
    exit 1
fi

echo ""
echo ""
echo -e "${VERDE}  ✓ Pronto su http://localhost:$PORT${NC}"
echo ""
sleep 0.3
open "http://localhost:$PORT"

echo "──────────────────────────────────────────────────────"
echo "  Tieni questa finestra aperta durante l'esperienza."
echo "  Premi Ctrl+C per fermare il server."
echo "──────────────────────────────────────────────────────"
echo ""

cleanup() {
    echo ""
    echo "  Arresto..."
    kill "$SRV" 2>/dev/null
    wait "$SRV" 2>/dev/null
    exit 0
}
trap cleanup INT TERM
tail -f "$LOG" &
TAIL=$!
wait "$SRV"
kill "$TAIL" 2>/dev/null
