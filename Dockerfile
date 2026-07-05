# ─────────────────────────────────────────────────────────────
# ARGUS - Distribuidor de Documentos
# FastAPI + Uvicorn en Docker (multi-etapa para tamaño mínimo)
# ─────────────────────────────────────────────────────────────
FROM python:3.12-slim AS builder

WORKDIR /app
COPY backend/requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# ─── Imagen final ──────────────────────────────────────────
FROM python:3.12-slim

WORKDIR /app

# Solamente lo que necesitamos en runtime: python y libs
COPY --from=builder /root/.local /root/.local
ENV PATH=/root/.local/bin:$PATH

# Código de la app
COPY backend/ .
COPY backend/app/templates ./templates
COPY backend/static ./static

# Script de entrada
COPY docker-entrypoint.sh /docker-entrypoint.sh
RUN chmod +x /docker-entrypoint.sh

EXPOSE 8000

ENTRYPOINT ["/docker-entrypoint.sh"]
