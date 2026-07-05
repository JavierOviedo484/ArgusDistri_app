#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────
# deploy-argus.sh — Despliega ARGUS en el servidor Artix
#
# Este script se ejecuta EN el servidor Artix (SSH).
# Pre-requisitos: git, docker, docker compose
#
# Uso:
#   1. Subir el código a GitHub
#   2. SSH al servidor: ssh javi1 (o ssh javier@192.168.100.22)
#   3. bash deploy-argus.sh
# ─────────────────────────────────────────────────────────────
set -e

REPO_URL="${1:-git@github.com:TU_USUARIO/distribuidor-pdfs.git}"
DOMINIO="${2:-argus.tudominio.com}"
APP_DIR="$HOME/argus"

echo "╔══════════════════════════════════════════════════╗"
echo "║   🚀 ARGUS — Deploy en servidor Artix           ║"
echo "╚══════════════════════════════════════════════════╝"

# 1. Clonar o actualizar repositorio
if [ -d "$APP_DIR" ]; then
    echo ""
    echo "1/6 Actualizando código..."
    cd "$APP_DIR"
    git pull
else
    echo ""
    echo "1/6 Clonando repositorio..."
    git clone "$REPO_URL" "$APP_DIR"
    cd "$APP_DIR"
fi

# 2. Crear .env si no existe
echo ""
echo "2/6 Configurando variables de entorno..."
if [ ! -f .env ]; then
    cp .env.example .env
    echo "   ⚠️  Archivo .env creado desde .env.example"
    echo "   ✏️  EDÍTALO ANTES DE CONTINUAR: nano .env"
    echo "   Cambia ARGUS_PASSWORD y las contraseñas de BD"
    exit 1
fi
echo "   ✅ .env encontrado"

# 3. Construir y levantar servicios
echo ""
echo "3/6 Construyendo imágenes Docker..."
docker compose build

echo ""
echo "4/6 Levantando servicios..."
docker compose up -d

# 4. Esperar a que los servicios respondan
echo ""
echo "5/6 Verificando servicios..."
for i in $(seq 1 30); do
    if curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/ 2>/dev/null | grep -q 200; then
        echo "   ✅ ARGUS responde en http://localhost:8000"
        break
    fi
    sleep 2
done

# Verificar Evolution
for i in $(seq 1 15); do
    if curl -s -o /dev/null http://localhost:8080/ 2>/dev/null; then
        echo "   ✅ Evolution API responde en http://localhost:8080"
        break
    fi
    sleep 2
done

# 5. Mostrar estado de WhatsApp
echo ""
echo "6/6 Estado de WhatsApp:"
ESTADO=$(curl -s http://localhost:8080/instance/connectionState/argus \
    -H "apikey: $(grep WHATSAPP_API_KEY .env | cut -d= -f2-)" 2>/dev/null | \
    python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('instance',{}).get('state','desconocido'))" 2>/dev/null || echo "verificando")
echo "   📱 WhatsApp: $ESTADO"

echo ""
echo "╔══════════════════════════════════════════════════╗"
echo "║  ✅ ARGUS desplegado                            ║"
echo "║                                                 ║"
echo "║  Local:   http://localhost:8000                  ║"
echo "║  Externo: https://$DOMINIO                   ║"
echo "║                                                 ║"
echo "║  Siguiente paso: configura Cloudflare Tunnel    ║"
echo "║  (ver tunel-argus.sh)                           ║"
echo "╚══════════════════════════════════════════════════╝"
