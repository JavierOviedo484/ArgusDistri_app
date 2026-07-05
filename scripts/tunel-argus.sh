#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────
# tunel-argus.sh — Añade ARGUS al Cloudflare Tunnel existente
#
# Requisitos: cloudflared ya instalado y un tunnel activo
# (el mismo que usas para MedicDerma o uno nuevo)
#
# Uso: Ejecutar en el servidor Artix
#   bash scripts/tunel-argus.sh
# ─────────────────────────────────────────────────────────────
set -e

DOMINIO="${1:-argus.tudominio.com}"
TUNNEL_NAME="${2:-medicderma-tunel}"

echo "╔══════════════════════════════════════════════════╗"
echo "║  🔒 Configurando Cloudflare Tunnel para ARGUS   ║"
echo "╚══════════════════════════════════════════════════╝"

# Verificar que cloudflared existe
if ! command -v cloudflared &>/dev/null; then
    echo "❌ cloudflared no está instalado en este servidor."
    echo "   Instálalo: https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/"
    exit 1
fi

echo ""
echo "1/3 Verificando tunnel existente..."
cloudflared tunnel list 2>/dev/null | grep -q "$TUNNEL_NAME" || {
    echo "   ⚠️  Tunnel '$TUNNEL_NAME' no encontrado."
    echo "   Creando nuevo tunnel..."
    cloudflared tunnel create "$TUNNEL_NAME"
}

echo ""
echo "2/3 Editando config del tunnel..."
CONFIG_FILE="$HOME/.cloudflared/$TUNNEL_NAME.yml"

# Crear o añadir entrada al config
if [ -f "$CONFIG_FILE" ]; then
    # Verificar si ya existe la entrada de argus
    if grep -q "argus" "$CONFIG_FILE" 2>/dev/null; then
        echo "   ✅ Ya existe entrada para ARGUS en el config"
    else
        echo "" >> "$CONFIG_FILE"
        echo "  - hostname: $DOMINIO" >> "$CONFIG_FILE"
        echo "    service: http://localhost:8000" >> "$CONFIG_FILE"
        echo "   ✅ Añadida entrada para $DOMINIO → http://localhost:8000"
    fi
else
    echo "   Creando archivo de configuración..."
    cat > "$CONFIG_FILE" << 'CFG'
tunnel: TUNNEL_ID
credentials-file: /home/javier/.cloudflared/TUNNEL_ID.json

ingress:
  - hostname: DOMINIO_PLACEHOLDER
    service: http://localhost:8000
  - service: http_status:404
CFG
    sed -i "s/TUNNEL_ID/$(cloudflared tunnel list | grep "$TUNNEL_NAME" | awk '{print $1}')/" "$CONFIG_FILE"
    sed -i "s/DOMINIO_PLACEHOLDER/$DOMINIO/" "$CONFIG_FILE"
    echo "   ✅ Configuración creada"
fi

echo ""
echo "3/3 Configurando DNS..."
echo "   Asegúrate de tener un registro CNAME en Cloudflare:"
echo "   $DOMINIO → $(cloudflared tunnel list | grep "$TUNNEL_NAME" | awk '{print $2}').cfargotunnel.com"

echo ""
echo "╔══════════════════════════════════════════════════╗"
echo "║  ✅ Tunnel configurado                          ║"
echo "║                                                 ║"
echo "║  Luego de tener el DNS listo, reinicia el       ║"
echo "║  tunnel con:                                    ║"
echo "║                                                 ║"
echo "║  sudo cloudflared tunnel run $TUNNEL_NAME       ║"
echo "║                                                 ║"
echo "║  O si usas systemd:                             ║"
echo "║  sudo systemctl restart cloudflared             ║"
echo "║                                                 ║"
echo "║  (En Artix con OpenRC es diferente)             ║"
echo "╚══════════════════════════════════════════════════╝"
