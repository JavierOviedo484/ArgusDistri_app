"""
Modelo: Plantilla de mensaje.
Cada plantilla define el texto que se envía por WhatsApp o email.

Variables disponibles en las plantillas:
  {nombre}     — Nombre del colaborador
  {periodo}    — Período de la factura (ej. MARZO 2026)
  {monto}      — Monto de la factura (ej. 300.00)
  {ruc}        — RUC/cédula del colaborador
  {archivo}    — Nombre del archivo PDF
"""

from sqlalchemy import Column, Integer, String, Text, DateTime, func
from app.core.database import Base


class Plantilla(Base):
    __tablename__ = "plantillas"

    id = Column(Integer, primary_key=True, autoincrement=True)
    canal = Column(String(20), nullable=False)  # "whatsapp" | "email"
    nombre = Column(String(100), nullable=False)  # identificador interno
    asunto = Column(String(200), nullable=True)   # solo para email
    cuerpo = Column(Text, nullable=False)
    descripcion = Column(String(200), nullable=True)
    activo = Column(Integer, default=1)

    creado_en = Column(DateTime, server_default=func.now())

    def __repr__(self) -> str:
        return f"<Plantilla {self.canal}: {self.nombre}>"

    def dict(self) -> dict:
        return {
            "id": self.id,
            "canal": self.canal,
            "nombre": self.nombre,
            "asunto": self.asunto or "",
            "cuerpo": self.cuerpo,
            "descripcion": self.descripcion or "",
            "activo": bool(self.activo),
        }


# ─── Plantillas por defecto ──────────────────────────────────────

# Aviso que acompaña a todos los canales. OJO: texto literal, sin {placeholders}
# nuevos — las plantillas se renderizan con .format(nombre=, periodo=, monto=).
AVISO_NO_CORRESPONDE = (
    "\n\n⚠️ IMPORTANTE: si esta factura NO le corresponde o los datos no "
    "coinciden con su identidad, por favor comuníquese URGENTEMENTE con la "
    "empresa ARGUS al correo javierparedes484@gmail.com para reportarlo."
)

PLANTILLAS_DEFAULT = [
    {
        "canal": "whatsapp",
        "nombre": "factura",
        "asunto": "",
        "descripcion": "Mensaje WhatsApp al enviar factura",
        "cuerpo": (
            "Hola {nombre},\n\n"
            "ARGUS te comparte tu factura correspondiente al "
            "período {periodo} por un valor de ${monto}.\n\n"
            "Adjunto encontrarás el documento PDF.\n\n"
            "Saludos cordiales,\n"
            "Equipo ARGUS"
            + AVISO_NO_CORRESPONDE
        ),
    },
    {
        "canal": "email",
        "nombre": "factura",
        "asunto": "Factura {periodo} — ARGUS",
        "descripcion": "Correo electrónico al enviar factura",
        "cuerpo": (
            "Estimado/a {nombre},\n\n"
            "Recibe un cordial saludo de parte de ARGUS.\n\n"
            "Adjuntamos a este correo tu factura correspondiente "
            "al período {periodo} por un valor de ${monto}.\n\n"
            "Quedamos atentos a cualquier consulta.\n\n"
            "Atentamente,\n"
            "Equipo ARGUS"
            + AVISO_NO_CORRESPONDE
        ),
    },
    {
        "canal": "sms",
        "nombre": "factura",
        "asunto": "",
        "descripcion": "SMS al enviar factura (sin adjunto; el PDF llega por email/WhatsApp)",
        "cuerpo": (
            "ARGUS: Hola {nombre}, se emitio su factura del periodo {periodo} "
            "por ${monto}. El PDF llega a su correo/WhatsApp. Si esta factura "
            "NO le corresponde, comuniquese URGENTE con la empresa: "
            "javierparedes484@gmail.com"
        ),
    },
]
