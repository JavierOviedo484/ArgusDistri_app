"""
Servicio de envío de SMS vía gateway HTTP genérico.

Funciona con cualquier gateway que acepte POST JSON {"to": ..., "message": ...}
con cabecera Authorization — por ejemplo la app Android "Traccar SMS Gateway"
(convierte un teléfono en gateway SMS gratuito en la red local) o un proveedor
comercial con esa forma de API. Se configura en Configuración:
  sms_api_url — URL del gateway (ej: http://192.168.100.50:8082)
  sms_api_key — token / API key del gateway
"""

import logging
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

# Los SMS no llevan adjunto: el texto debe ser corto y autocontenido.
# El aviso "si no le corresponde" va en la plantilla del canal sms.
MAX_LARGO_SMS = 480  # ~3 segmentos concatenados


def enviar_sms(
    numero: str,
    mensaje: str,
    api_url: Optional[str] = None,
    api_key: Optional[str] = None,
) -> dict:
    """
    Envía un SMS vía gateway HTTP.

    Args:
        numero: Número destino (ej: +593999999999)
        mensaje: Texto del SMS (se recorta a MAX_LARGO_SMS)
        api_url: URL del gateway SMS
        api_key: Token del gateway

    Returns:
        dict con {"ok": bool, "mensaje": str}
    """
    if not api_url or not api_key:
        return {"ok": False, "mensaje": "SMS no configurado — falta URL o API Key del gateway (pestaña Configuración)"}

    numero_limpio = numero.strip()
    if not numero_limpio.startswith("+"):
        solo_digitos = "".join(c for c in numero_limpio if c.isdigit())
        numero_limpio = "+" + solo_digitos

    texto = mensaje[:MAX_LARGO_SMS]

    try:
        resp = httpx.post(
            api_url.rstrip("/"),
            json={"to": numero_limpio, "message": texto},
            headers={
                "Content-Type": "application/json",
                "Authorization": api_key,
            },
            timeout=30,
        )

        if resp.status_code in (200, 201, 202):
            logger.info(f"SMS enviado a {numero_limpio}")
            return {"ok": True, "mensaje": f"SMS enviado a {numero_limpio}"}
        return {"ok": False, "mensaje": f"Error del gateway SMS ({resp.status_code}): {resp.text[:200]}"}

    except httpx.ConnectError:
        return {"ok": False, "mensaje": f"No se pudo conectar al gateway SMS: {api_url}"}
    except Exception as e:
        logger.error(f"Error enviando SMS: {e}")
        return {"ok": False, "mensaje": f"Error al enviar SMS: {str(e)}"}
