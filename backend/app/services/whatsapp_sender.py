"""
Servicio de envío de WhatsApp vía Evolution API (v2).

Configuración (pestaña Configuración del dashboard):
  whatsapp_api_url   — URL donde corre Evolution API (ej: http://localhost:8080)
  whatsapp_api_key   — AUTHENTICATION_API_KEY de Evolution
  whatsapp_instance  — nombre de la instancia creada en el manager (ej: argus)

Ver GUIA_WHATSAPP.md en la raíz del proyecto para levantar Evolution API
con Docker y vincular el teléfono escaneando el QR.
"""

import base64
import logging
from pathlib import Path
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

# El aviso "si esta factura no le corresponde, comuníquese urgentemente" vive
# en la PLANTILLA del canal (editable desde el dashboard); aquí solo se marca
# que el mensaje es automático, para no duplicar el texto de contacto.
DISCLAIMER = (
    "\n\n—\n🤖 Mensaje generado automáticamente por el sistema "
    "de distribución de documentos ARGUS."
)


def normalizar_telefono(numero: str) -> str:
    """
    Normaliza un número telefónico a formato internacional sin '+' (Ecuador).

    Casos de entrada → salida:
      '0999999999'      → '593999999999'
      '+593 99 999 9999' → '593999999999'
      '0962911218'      → '593962911218'
      '593999999999'    → '593999999999'  (sin cambios)

    Evolution API espera este formato (código país + número, sin +, sin 0 inicial).
    """
    digitos = "".join(c for c in numero if c.isdigit())
    if digitos.startswith("00"):
        digitos = digitos[2:]
    if len(digitos) == 10 and digitos.startswith("09"):
        digitos = "593" + digitos[1:]          # celular local Ecuador
    elif len(digitos) == 9 and digitos.startswith("9"):
        digitos = "593" + digitos              # celular sin el 0 inicial
    return digitos


def enviar_whatsapp(
    numero: str,
    mensaje: str,
    api_url: Optional[str] = None,
    api_key: Optional[str] = None,
    instance: Optional[str] = None,
    adjunto_pdf: Optional[Path] = None,
) -> dict:
    """
    Envía un mensaje de WhatsApp (con el PDF adjunto si se proporciona).

    Returns:
        dict con {"ok": bool, "mensaje": str}
    """
    if not api_url or not api_key:
        return {"ok": False, "mensaje": "WhatsApp no configurado — falta URL o API Key de Evolution (pestaña Configuración)"}

    instancia = (instance or "argus").strip()
    numero_limpio = normalizar_telefono(numero)
    if len(numero_limpio) < 11:
        return {"ok": False, "mensaje": f"Número inválido para WhatsApp: '{numero}' (se esperaba celular con código de país, ej: +593 99 999 9999)"}

    texto_completo = mensaje + DISCLAIMER
    base = api_url.rstrip("/")
    headers = {"Content-Type": "application/json", "apikey": api_key}

    try:
        if adjunto_pdf and Path(adjunto_pdf).exists():
            # Enviar el PDF como documento con el texto como caption
            pdf = Path(adjunto_pdf)
            payload = {
                "number": numero_limpio,
                "mediatype": "document",
                "mimetype": "application/pdf",
                "fileName": pdf.name,
                "media": base64.b64encode(pdf.read_bytes()).decode(),
                "caption": texto_completo,
            }
            url = f"{base}/message/sendMedia/{instancia}"
        else:
            payload = {"number": numero_limpio, "text": texto_completo}
            url = f"{base}/message/sendText/{instancia}"

        resp = httpx.post(url, json=payload, headers=headers, timeout=60)

        if resp.status_code in (200, 201):
            con_pdf = " (con PDF adjunto)" if adjunto_pdf else ""
            logger.info(f"WhatsApp enviado a +{numero_limpio}{con_pdf}")
            return {"ok": True, "mensaje": f"WhatsApp enviado a +{numero_limpio}{con_pdf}"}
        if resp.status_code == 404:
            return {"ok": False, "mensaje": f"Evolution API: la instancia '{instancia}' no existe — créala en el manager y escanea el QR (ver GUIA_WHATSAPP.md)"}
        if resp.status_code == 401:
            return {"ok": False, "mensaje": "Evolution API: API Key incorrecta — revisa whatsapp_api_key en Configuración"}
        logger.warning(f"Evolution API respondió {resp.status_code}: {resp.text[:300]}")
        return {"ok": False, "mensaje": f"Error Evolution API ({resp.status_code}): {resp.text[:200]}"}

    except httpx.ConnectError:
        return {"ok": False, "mensaje": f"Evolution API no responde en {api_url} — ¿está encendida? (docker compose up -d, ver GUIA_WHATSAPP.md)"}
    except Exception as e:
        logger.error(f"Error enviando WhatsApp: {e}")
        return {"ok": False, "mensaje": f"Error al enviar WhatsApp: {str(e)}"}


def probar_conexion(
    api_url: Optional[str] = None,
    api_key: Optional[str] = None,
    instance: Optional[str] = None,
) -> dict:
    """
    Comprueba si Evolution API está encendida y la instancia vinculada a WhatsApp.

    Returns:
        dict con {"ok": bool, "estado": str, "mensaje": str}
    """
    if not api_url or not api_key:
        return {"ok": False, "estado": "sin_config",
                "mensaje": "Faltan whatsapp_api_url o whatsapp_api_key en Configuración"}

    instancia = (instance or "argus").strip()
    try:
        resp = httpx.get(
            f"{api_url.rstrip('/')}/instance/connectionState/{instancia}",
            headers={"apikey": api_key},
            timeout=10,
        )
        if resp.status_code == 404:
            return {"ok": False, "estado": "sin_instancia",
                    "mensaje": f"La instancia '{instancia}' no existe todavía — créala en el manager ({api_url}/manager) y escanea el QR"}
        if resp.status_code == 401:
            return {"ok": False, "estado": "auth",
                    "mensaje": "API Key incorrecta — debe ser la AUTHENTICATION_API_KEY de Evolution"}

        data = resp.json()
        estado = (data.get("instance") or {}).get("state") or data.get("state") or "desconocido"
        if estado == "open":
            return {"ok": True, "estado": "conectado",
                    "mensaje": f"Conectado ✓ — la instancia '{instancia}' está vinculada y lista para enviar"}
        return {"ok": False, "estado": estado,
                "mensaje": f"La instancia '{instancia}' está en estado '{estado}' — abre el manager ({api_url}/manager) y escanea el QR con el teléfono"}

    except httpx.ConnectError:
        return {"ok": False, "estado": "apagada",
                "mensaje": f"Evolution API no responde en {api_url} — enciéndela con: docker compose up -d (ver GUIA_WHATSAPP.md)"}
    except Exception as e:
        return {"ok": False, "estado": "error", "mensaje": f"Error probando conexión: {str(e)}"}
