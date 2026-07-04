"""
Modelo: Envio (log).
Registro de cada vez que se envía un documento por WhatsApp o email.
"""

from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, func
from sqlalchemy.orm import relationship
from app.core.database import Base


class Envio(Base):
    __tablename__ = "envios"

    id = Column(Integer, primary_key=True, autoincrement=True)
    factura_id = Column(Integer, ForeignKey("facturas.id"), nullable=False, index=True)
    canal = Column(String(20), nullable=False)  # "whatsapp" | "email"
    destinatario = Column(String(200), nullable=False)  # teléfono o email
    estado = Column(String(20), nullable=False, default="pendiente")
    # Estados: pendiente, enviado, entregado, fallido, rebotado
    error_msg = Column(String(500), nullable=True)

    enviado_en = Column(DateTime, server_default=func.now())

    factura = relationship("Factura", backref="envios")

    def __repr__(self) -> str:
        return f"<Envio #{self.id}: {self.canal} → {self.destinatario} [{self.estado}]>"

    def dict(self) -> dict:
        return {
            "id": self.id,
            "factura_id": self.factura_id,
            "canal": self.canal,
            "destinatario": self.destinatario,
            "estado": self.estado,
            "error": self.error_msg,
            "enviado_en": self.enviado_en.isoformat() if self.enviado_en else None,
            "archivo": self.factura.archivo_original if self.factura else None,
            "colaborador": self.factura.colaborador.nombre if self.factura and self.factura.colaborador else None,
        }
