"""
Servicio de envío de email vía SMTP de Gmail.
Usa App Password de Gmail (requiere verificación en 2 pasos).
"""

import smtplib
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


def enviar_email(
    para: str,
    asunto: str,
    cuerpo: str,
    adjunto_pdf: Optional[Path] = None,
    smtp_host: str = "smtp.gmail.com",
    smtp_port: int = 587,
    smtp_user: Optional[str] = None,
    smtp_password: Optional[str] = None,
) -> dict:
    """
    Envía un email con PDF adjunto vía SMTP de Gmail.

    Args:
        para: Correo destinatario
        asunto: Asunto del mensaje
        cuerpo: Cuerpo HTML/Texto
        adjunto_pdf: Ruta al PDF a adjuntar (opcional)
        smtp_host: Servidor SMTP
        smtp_port: Puerto SMTP
        smtp_user: Usuario (correo Gmail)
        smtp_password: App Password de Gmail

    Returns:
        dict con {"ok": bool, "mensaje": str}
    """
    if not smtp_user or not smtp_password:
        return {"ok": False, "mensaje": "SMTP no configurado — falta email o App Password"}

    try:
        msg = MIMEMultipart()
        msg["From"] = smtp_user
        msg["To"] = para
        msg["Subject"] = asunto

        msg.attach(MIMEText(cuerpo, "plain", "utf-8"))

        # Adjuntar PDF
        if adjunto_pdf and adjunto_pdf.exists():
            with open(adjunto_pdf, "rb") as f:
                part = MIMEBase("application", "pdf")
                part.set_payload(f.read())
                encoders.encode_base64(part)
                part.add_header(
                    "Content-Disposition",
                    f"attachment; filename={adjunto_pdf.name}",
                )
                msg.attach(part)

        with smtplib.SMTP(smtp_host, smtp_port) as server:
            server.starttls()
            server.login(smtp_user, smtp_password)
            server.send_message(msg)

        logger.info(f"Email enviado a {para} — {asunto}")
        return {"ok": True, "mensaje": f"Email enviado a {para}"}

    except smtplib.SMTPAuthenticationError:
        return {"ok": False, "mensaje": "Error de autenticación SMTP — verifica el App Password"}
    except smtplib.SMTPRecipientsRefused:
        return {"ok": False, "mensaje": f"Destinatario rechazado: {para}"}
    except Exception as e:
        logger.error(f"Error enviando email: {e}")
        return {"ok": False, "mensaje": f"Error al enviar email: {str(e)}"}
