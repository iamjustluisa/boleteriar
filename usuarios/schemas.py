import re
from typing import Annotated

from pydantic import (BaseModel, ConfigDict, EmailStr, Field, StringConstraints,
                      field_validator, model_validator)

Nombre = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)]
Telefono = Annotated[str, StringConstraints(strip_whitespace=True, pattern=r"^\+?[0-9 ]{7,20}$")]
Documento = Annotated[str, StringConstraints(strip_whitespace=True, pattern=r"^[A-Za-z0-9]{5,20}$")]


def _validar_contrasena(v: str) -> str:
    # bcrypt solo procesa los primeros 72 bytes: se rechaza en lugar de truncar en silencio.
    if len(v.encode("utf-8")) > 72:
        raise ValueError("La contraseña no puede superar 72 bytes")
    if not (re.search(r"[A-Za-z]", v) and re.search(r"[0-9]", v)):
        raise ValueError("La contraseña debe incluir al menos una letra y un número")
    return v


class RegistroIn(BaseModel):
    """RF-USR-01: todos los campos son obligatorios."""
    model_config = ConfigDict(extra="forbid")

    nombre: Nombre
    apellido: Nombre
    correo: EmailStr = Field(max_length=120)
    telefono: Telefono
    documento: Documento
    contrasena: str = Field(min_length=8)

    @field_validator("correo")
    @classmethod
    def _correo_minusculas(cls, v: str) -> str:
        return v.strip().lower()

    @field_validator("contrasena")
    @classmethod
    def _contrasena_valida(cls, v: str) -> str:
        return _validar_contrasena(v)


class ActualizarIn(BaseModel):
    """RF-USR-02: solo datos de contacto. El documento no se puede modificar."""
    model_config = ConfigDict(extra="forbid")

    correo: EmailStr | None = Field(default=None, max_length=120)
    telefono: Telefono | None = None

    @field_validator("correo")
    @classmethod
    def _correo_minusculas(cls, v: str | None) -> str | None:
        return v.strip().lower() if v else v

    @model_validator(mode="after")
    def _al_menos_uno(self):
        if self.correo is None and self.telefono is None:
            raise ValueError("Indica al menos correo o teléfono")
        return self


class UsuarioOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id_usuario: int
    nombre: str
    apellido: str
    correo: str
    telefono: str
    documento: str


class UsuarioConRolOut(UsuarioOut):
    rol: str | None = None


class UsuarioInternoOut(BaseModel):
    """Lo mínimo que Control de Acceso necesita para autenticar."""
    model_config = ConfigDict(from_attributes=True)

    id_usuario: int
    correo: str
