import re

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


class LoginIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    correo: EmailStr
    contrasena: str = Field(min_length=1, max_length=200)

    @field_validator("correo")
    @classmethod
    def _min(cls, v: str) -> str:
        return v.strip().lower()


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expira_en: int = Field(description="Segundos de vigencia de la sesión")
    id_usuario: int
    rol: str


class SesionOut(BaseModel):
    id_usuario: int
    rol: str
    permisos: list[str]


class AsignarRolIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    rol: str = Field(min_length=1, max_length=30)


class RolOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id_rol: int
    nombre: str
    descripcion: str | None
    permisos: list[str] = []


class PermisoOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id_permiso: int
    nombre: str
    descripcion: str | None


# ---- internos ----
class CredencialInternaIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id_usuario: int
    contrasena: str = Field(min_length=8, max_length=72)
    rol: str = "usuario"


class TokenInternoIn(BaseModel):
    token: str


class SesionInternaOut(BaseModel):
    id_sesion: int
    id_usuario: int
    rol: str
    permisos: list[str]
