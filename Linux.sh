#!/usr/bin/env bash
# Launcher for IN-Motion on Linux.
# Run:  ./Linux.sh   or double-click if your file manager allows executing scripts.

DIR="$(cd "$(dirname "$0")" && pwd)"
BACKEND="$DIR/web/backend"
PORT=8080
LOG="${TMPDIR:-/tmp}/inmotion.log"
VERDE='\033[0;32m'; GIALLO='\033[1;33m'; ROSSO='\033[0;31m'; NC='\033[0m'

export PATH="$HOME/.local/bin:/usr/local/bin:$PATH"

clear 2>/dev/null || true
echo ""
echo "  IN-Motion"
echo ""
echo "──────────────────────────────────────────────────────"
echo ""

_python_ok() {
    local py="$1"
    [ -n "$py" ] && [ -x "$py" ] || return 1
    "$py" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)' 2>/dev/null
}

PYTHON=""
for candidate in \
    "$HOME/.local/bin/python3" \
    /usr/local/bin/python3 \
    /usr/bin/python3 \
    "$(command -v python3 2>/dev/null)" \
    "$(command -v python 2>/dev/null)"
do
    if _python_ok "$candidate"; then
        PYTHON="$candidate"
        break
    fi
done

if [ -z "$PYTHON" ]; then
    echo -e "${ROSSO}✗ Python 3.10+ not found.${NC}"
    echo "  Install Python 3.10+ then run this again."
    echo ""
    read -r -p "  Press Enter to close..."
    exit 1
fi
echo -e "${VERDE}✓ $($PYTHON --version) ($PYTHON)${NC}"

if ! "$PYTHON" -c "import uvicorn, fastapi, dotenv, anthropic" &>/dev/null; then
    echo -e "${GIALLO}⚠ Installing dependencies (first run may take a few minutes)...${NC}"
    "$PYTHON" -m pip install -r "$BACKEND/requirements.txt"
    if [ $? -ne 0 ]; then
        echo -e "${ROSSO}✗ Install failed${NC}"
        read -r -p "Press Enter to close..."
        exit 1
    fi
fi
echo -e "${VERDE}✓ Dependencies OK${NC}"

if [ -f "$DIR/.env" ]; then
    set -a
    # shellcheck disable=SC1091
    source "$DIR/.env"
    set +a
    echo -e "${VERDE}✓ .env loaded${NC}"
fi

# Free the port if occupied
if command -v fuser &>/dev/null; then
    if fuser "${PORT}/tcp" &>/dev/null; then
        echo -e "${GIALLO}⚠ Stopping previous process on port $PORT...${NC}"
        fuser -k "${PORT}/tcp" &>/dev/null || true
        sleep 0.5
    fi
elif command -v lsof &>/dev/null; then
    VECCHIO=$(lsof -ti :"$PORT" 2>/dev/null | tr '\n' ' ')
    if [ -n "$VECCHIO" ]; then
        echo -e "${GIALLO}⚠ Stopping previous process on port $PORT...${NC}"
        # shellcheck disable=SC2086
        kill -9 $VECCHIO 2>/dev/null || true
        sleep 0.5
    fi
fi

echo ""
echo "  Starting server..."
cd "$BACKEND" || exit 1
: > "$LOG"
"$PYTHON" -m uvicorn server:app --host 0.0.0.0 --port "$PORT" >> "$LOG" 2>&1 &
SRV=$!

echo -n "  Waiting"
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
        echo -e "${ROSSO}✗ Server stopped. Error:${NC}"
        echo ""
        cat "$LOG"
        echo ""
        read -r -p "  Press Enter to close..."
        exit 1
    fi
done

if [ "$PRONTO" -eq 0 ]; then
    echo ""
    echo -e "${ROSSO}✗ Timeout. Error:${NC}"
    cat "$LOG"
    kill "$SRV" 2>/dev/null
    read -r -p "  Press Enter to close..."
    exit 1
fi

echo ""
echo ""
echo -e "${VERDE}  ✓ Ready at http://localhost:$PORT${NC}"
echo ""
sleep 0.3

if command -v xdg-open &>/dev/null; then
    xdg-open "http://localhost:$PORT" >/dev/null 2>&1 || true
elif command -v sensible-browser &>/dev/null; then
    sensible-browser "http://localhost:$PORT" >/dev/null 2>&1 || true
else
    echo "  Open http://localhost:$PORT in your browser."
fi

echo "──────────────────────────────────────────────────────"
echo "  Keep this window open during the experience."
echo "  Press Ctrl+C to stop the server."
echo "──────────────────────────────────────────────────────"
echo ""

cleanup() {
    echo ""
    echo "  Stopping..."
    kill "$SRV" 2>/dev/null
    wait "$SRV" 2>/dev/null
    exit 0
}
trap cleanup INT TERM
tail -f "$LOG" &
TAIL=$!
wait "$SRV"
kill "$TAIL" 2>/dev/null
