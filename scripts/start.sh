#!/bin/sh
# Arranque de la app. Respeta la variable PORT que inyectan plataformas como
# Render; si no existe, usa 8000 (Docker local, Codespaces).
set -e

PORT="${PORT:-8000}"

# Siembra datos de ejemplo solo si la base está vacía.
python -m app.seed

echo "Iniciando servidor en el puerto $PORT"
exec python -m uvicorn app.api:app --host 0.0.0.0 --port "$PORT"
