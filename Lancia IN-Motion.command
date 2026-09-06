#!/bin/bash
DIR="$(cd "$(dirname "$0")" && pwd)"
BACKEND="$DIR/web/backend"
PORT=8080
VERDE='\033[0;32m'; GIALLO='\033[1;33m'; ROSSO='\033[0;31m'; NC='\033[0m'

clear
echo ""
echo "  IN-Motion"
echo ""
echo "──────────────────────────────────────────────────────"
echo ""

# Verifica Python 3
if ! command -v python3 &>/dev/null; then
    echo -e "${ROSSO}✗ Python 3 non trovato.${NC}"
    echo "  Installa da https://www.python.org/downloads/"
    read -p "  Premi Invio per chiudere..."
    exit 1
fi
echo -e "${VERDE}✓ $(python3 --version)${NC}"

# Installa dipendenze se mancanti
if ! python3 -c "import uvicorn" &>/dev/null; then
    echo -e "${GIALLO}⚠ Installo dipendenze...${NC}"
    python3 -m pip install -r "$BACKEND/requirements.txt"
    [ $? -ne 0 ] && { echo -e "${ROSSO}✗ Installazione fallita${NC}"; read -p "Invio per chiudere..."; exit 1; }
fi
echo -e "${VERDE}✓ Dipendenze OK${NC}"

# Carica .env se presente
if [ -f "$DIR/.env" ]; then
    export $(grep -v '^#' "$DIR/.env" | grep -v '^$' | xargs)
    echo -e "${VERDE}✓ .env caricato${NC}"
fi

# Libera la porta se occupata
VECCHIO=$(lsof -ti :$PORT 2>/dev/null)
[ -n "$VECCHIO" ] && { echo -e "${GIALLO}⚠ Fermo processo precedente sulla porta $PORT...${NC}"; kill -9 $VECCHIO 2>/dev/null; sleep 0.5; }

# Avvia il server
echo ""
echo "  Avvio server..."
cd "$BACKEND"
python3 -m uvicorn server:app --host 0.0.0.0 --port $PORT > /tmp/inmotion.log 2>&1 &
SRV=$!

# Aspetta che il server sia pronto (max 30s)
echo -n "  In attesa"
PRONTO=0
for i in $(seq 1 60); do
    sleep 0.5
    echo -n "."
    CODE=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:$PORT/ 2>/dev/null)
    if [ "$CODE" = "200" ]; then PRONTO=1; break; fi
    if ! kill -0 $SRV 2>/dev/null; then
        echo ""
        echo -e "${ROSSO}✗ Il server si è fermato. Errore:${NC}"
        echo ""
        cat /tmp/inmotion.log
        echo ""
        read -p "  Premi Invio per chiudere..."
        exit 1
    fi
done

if [ $PRONTO -eq 0 ]; then
    echo ""
    echo -e "${ROSSO}✗ Timeout. Errore:${NC}"
    cat /tmp/inmotion.log
    kill $SRV 2>/dev/null
    read -p "  Premi Invio per chiudere..."
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

trap "echo ''; echo '  Arresto...'; kill $SRV 2>/dev/null; exit 0" INT TERM
tail -f /tmp/inmotion.log & wait $SRV
