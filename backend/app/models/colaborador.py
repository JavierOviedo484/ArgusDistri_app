"""
Modelo: Colaborador.
Cada persona que recibe documentos.
El RUC/cédula es el ID único (extraído del PDF).
"""

from sqlalchemy import Column, String, Boolean, DateTime, func
from app.core.database import Base


class Colaborador(Base):
    __tablename__ = "colaboradores"

    # El RUC o cédula es el identificador único que viene en la factura
    identificador = Column(String(20), primary_key=True, index=True)
    nombre = Column(String(200), nullable=False, index=True)
    email = Column(String(200), nullable=True)
    telefono = Column(String(20), nullable=True)
    activo = Column(Boolean, default=True)

    creado_en = Column(DateTime, server_default=func.now())
    actualizado_en = Column(DateTime, server_default=func.now(), onupdate=func.now())

    def __repr__(self) -> str:
        return f"<Colaborador {self.identificador}: {self.nombre}>"

    def dict(self) -> dict:
        return {
            "identificador": self.identificador,
            "nombre": self.nombre,
            "email": self.email,
            "telefono": self.telefono,
            "activo": self.activo,
        }
