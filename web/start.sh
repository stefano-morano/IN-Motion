#!/bin/sh
# Start the IN-Motion web backend (dev helper).
# Opens http://localhost:8080 — do NOT use http://0.0.0.0:8080 in the browser:
# cameras are blocked outside a secure context (localhost / https).

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BACKEND="$ROOT/web/backend"
PORT=8080

cd "$BACKEND" || exit 1

# Load .env from project root (same as MacOs.command / Windows.bat / Linux.sh)
if [ -f "$ROOT/.env" ]; then
    set -a
    # shellcheck disable=SC1091
    . "$ROOT/.env"
    set +a
fi

echo ""
echo "  IN-Motion"
echo "  Server:  http://localhost:$PORT"
echo "  (use localhost — not 0.0.0.0 — so the webcam is allowed)"
echo ""

# Open the browser to localhost once the port answers (macOS / Linux)
(
    for _ in 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16 17 18 19 20; do
        if curl -sf -o /dev/null "http://127.0.0.1:$PORT/" 2>/dev/null; then
            if command -v open >/dev/null 2>&1; then
                open "http://localhost:$PORT"
            elif command -v xdg-open >/dev/null 2>&1; then
                xdg-open "http://localhost:$PORT" >/dev/null 2>&1 || true
            fi
            break
        fi
        sleep 0.5
    done
) &

exec python3 -m uvicorn "server:app" --host 0.0.0.0 --port "$PORT"
