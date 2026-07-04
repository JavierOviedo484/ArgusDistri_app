"""
Modelo: Factura.
Cada PDF procesado, vinculado a un colaborador por su identificador (RUC/RUT).
"""

from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, func
from sqlalchemy.orm import relationship
from app.core.database import Base


class Factura(Base):
    __tablename__ = "facturas"

    id = Column(Integer, primary_key=True, autoincrement=True)
    colaborador_id = Column(String(20), ForeignKey("colaboradores.identificador"), nullable=True, index=True)
    archivo_original = Column(String(255), nullable=False)
    periodo = Column(String(100), nullable=True)
    monto = Column(String(50), nullable=True)
    ruta_pdf = Column(String(500), nullable=True)

    # Flags de envío
    enviado_email = Column(Integer, default=0)
    enviado_whatsapp = Column(Integer, default=0)

    procesado_en = Column(DateTime, server_default=func.now())

    # Relación
    colaborador = relationship("Colaborador", backref="facturas")

    def __repr__(self) -> str:
        return f"<Factura {self.id}: {self.archivo_original} → {self.colaborador_id or '?'}>"

    def dict(self) -> dict:
        return {
            "id": self.id,
            "colaborador_id": self.colaborador_id,
            "archivo_original": self.archivo_original,
            "periodo": self.periodo,
            "monto": self.monto,
            "procesado_en": self.procesado_en.isoformat() if self.procesado_en else None,
            "colaborador_nombre": self.colaborador.nombre if self.colaborador else None,
        }
