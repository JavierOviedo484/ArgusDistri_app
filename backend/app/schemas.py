"""
Schemas Pydantic para validación de datos de la API.
"""

from pydantic import BaseModel, field_validator
from typing import Optional


class ColaboradorCreate(BaseModel):
    identificador: str
    nombre: str
    email: Optional[str] = None
    telefono: Optional[str] = None
    activo: bool = True

    @field_validator("telefono")
    @classmethod
    def normalizar_telefono(cls, v: Optional[str]) -> Optional[str]:
        if not v or v == "sin correo":
            return v
        from app.services.whatsapp_sender import normalizar_telefono as _norm
        return _norm(v)


class EnvioItem(BaseModel):
    factura_id: int


class EnvioConfirm(BaseModel):
    envios: list[EnvioItem]


class PlantillaUpdate(BaseModel):
    canal: Optional[str] = None
    nombre: Optional[str] = None
    asunto: Optional[str] = None
    cuerpo: Optional[str] = None
    descripcion: Optional[str] = None


class ConfigUpdate(BaseModel):
    clave: str
    valor: str
