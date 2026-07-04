"""
Servicio de envío de WhatsApp vía Evolution API.
Incluye disclaimer de chatbot en el mensaje.
"""

import json
import logging
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


def enviar_whatsapp(
    numero: str,
    mensaje: str,
    api_url: Optional[str] = None,
    api_key: Optional[str] = None,
) -> dict:
    """
    Envía un mensaje de WhatsApp vía Evolution API.

    Args:
        numero: Número destino (ej: +593999999999)
        mensaje: Texto del mensaje (se le añade disclaimer automáticamente)
        api_url: URL base de Evolution API (ej: http://localhost:8080)
        api_key: API Key de Evolution

    Returns:
        dict con {"ok": bool, "mensaje": str}
    """
    if not api_url or not api_key:
        return {"ok": False, "mensaje": "WhatsApp no configurado — falta URL o API Key de Evolution"}

    # Limpiar número: solo dígitos
    numero_limpio = "".join(c for c in numero if c.isdigit())

    texto_completo = mensaje + DISCLAIMER

    try:
        payload = {
            "number": numero_limpio,
            "text": texto_completo,
        }

        headers = {
            "Content-Type": "application/json",
            "apiKey": api_key,
        }

        # Evolution API: /message/sendText/{instance}
        # La instancia se obtiene de la URL o config
        resp = httpx.post(
            f"{api_url.rstrip('/')}/message/sendText/{api_key}",
            json=payload,
            headers=headers,
            timeout=30,
        )

        if resp.status_code in (200, 201):
            logger.info(f"WhatsApp enviado a {numero}")
            return {"ok": True, "mensaje": f"Mensaje enviado a {numero}"}
        else:
            logger.warning(f"Evolution API respondió {resp.status_code}: {resp.text}")
            return {"ok": False, "mensaje": f"Error Evolution API ({resp.status_code}): {resp.text[:200]}"}

    except httpx.ConnectError:
        return {"ok": False, "mensaje": f"No se pudo conectar a Evolution API: {api_url}"}
    except Exception as e:
        logger.error(f"Error enviando WhatsApp: {e}")
        return {"ok": False, "mensaje": f"Error al enviar WhatsApp: {str(e)}"}
