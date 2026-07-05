#!/bin/sh
# ─────────────────────────────────────────────────────────────
# Entrypoint de ARGUS en Docker
# ─────────────────────────────────────────────────────────────
set -e

# Reemplazar DATABASE_URL si viene por entorno (para usar PostgreSQL en producción)
if [ -n "$DATABASE_URL" ]; then
    export DATABASE_URL="$DATABASE_URL"
    echo "Usando DATABASE_URL desde entorno"
fi

# Ejecutar migraciones del esquema (init_db se llama en startup de FastAPI)
# pero forzamos aquí también para el primer arranque con BD vacía
echo "Iniciando ARGUS..."

# Arrancar servidor (con --forwarded-allow-ips para que funcione tras proxy/tunnel)
exec uvicorn main:app --host 0.0.0.0 --port 8000 --forwarded-allow-ips '*'
