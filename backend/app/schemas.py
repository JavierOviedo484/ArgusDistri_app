"""
Schemas Pydantic para validación de datos de la API.
"""

from pydantic import BaseModel
from typing import Optional


class ColaboradorCreate(BaseModel):
    identificador: str
    nombre: str
    email: Optional[str] = None
    telefono: Optional[str] = None
    activo: bool = True


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
