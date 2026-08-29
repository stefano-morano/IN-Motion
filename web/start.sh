#!/bin/sh
# Avvia il backend IN-Motion Web
cd "$(dirname "$0")/backend"
exec python3 -m uvicorn server:app --host 0.0.0.0 --port 8080 --reload
