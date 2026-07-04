"""
Modelo: Configuración global del sistema.
Almacena pares clave/valor editables desde el dashboard.
"""

from sqlalchemy import Column, Integer, String, Text, DateTime, func
from app.core.database import Base


class Configuracion(Base):
    __tablename__ = "configuracion"

    id = Column(Integer, primary_key=True, autoincrement=True)
    clave = Column(String(100), unique=True, nullable=False, index=True)
    valor = Column(Text, nullable=False, default="")
    descripcion = Column(String(200), nullable=True)

    actualizado_en = Column(DateTime, server_default=func.now(), onupdate=func.now())

    def __repr__(self) -> str:
        return f"<Config {self.clave}={self.valor}>"

    def dict(self) -> dict:
        return {"clave": self.clave, "valor": self.valor, "descripcion": self.descripcion or ""}


CONFIG_DEFAULT = [
    ("email_sender", "javierparedes484@gmail.com", "Correo desde el que se envían las facturas"),
    ("gmail_app_password", "", "App Password de Gmail (16 chars, de myaccount.google.com/apppasswords)"),
    ("whatsapp_sender", "+593962911218", "Número de WhatsApp que envía los mensajes"),
    ("empresa_nombre", "ARGUS", "Nombre de la empresa"),
    ("whatsapp_api_url", "http://localhost:8080", "URL de Evolution API (con el Docker de la guía es http://localhost:8080)"),
    ("whatsapp_api_key", "argus-whatsapp-2026", "API Key de Evolution API (AUTHENTICATION_API_KEY del docker-compose)"),
    ("whatsapp_instance", "argus", "Nombre de la instancia de WhatsApp en Evolution API (crearla en el manager y escanear QR)"),
    ("sms_api_url", "", "URL del gateway SMS (ej: http://IP-del-telefono:8082 con la app Traccar SMS Gateway, o tu proveedor)"),
    ("sms_api_key", "", "API Key / token del gateway SMS"),
]
