"""Datos base: roles y permisos (idempotente). Corre al iniciar el servicio."""
from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Permiso, Rol

PERMISOS = {
    "consultar_eventos": "Consultar eventos y su disponibilidad",
    "reservar_asientos": "Reservar asientos de un evento",
    "comprar_boletas": "Comprar los asientos de una reserva",
    "consultar_historial_propio": "Ver reservas, compras y boletas propias",
    "gestionar_escenarios": "Crear, editar y consultar escenarios",
    "gestionar_eventos": "Crear, editar y cancelar eventos",
    "gestionar_localidades": "Administrar localidades de un escenario",
    "gestionar_asientos": "Administrar asientos de una localidad",
    "gestionar_roles": "Asignar roles y permisos",
    "listar_usuarios": "Listar usuarios registrados",
    "consultar_auditoria": "Consultar la auditoría con filtros",
    "consultar_indicadores": "Consultar indicadores y ejecutar el ETL del Data Warehouse",
}
PERMISOS_USUARIO = ["consultar_eventos", "reservar_asientos", "comprar_boletas",
                    "consultar_historial_propio"]

ROLES = {
    "usuario": ("Comprador de boletas", PERMISOS_USUARIO),
    "administrador": ("Administra escenarios, eventos, roles y auditoría", list(PERMISOS)),
}


def sembrar(db: Session) -> None:
    permisos = {}
    for nombre, desc in PERMISOS.items():
        p = db.scalar(select(Permiso).where(Permiso.nombre == nombre))
        if p is None:
            p = Permiso(nombre=nombre, descripcion=desc)
            db.add(p)
        permisos[nombre] = p
    db.flush()
    for nombre, (desc, lista) in ROLES.items():
        rol = db.scalar(select(Rol).where(Rol.nombre == nombre))
        if rol is None:
            rol = Rol(nombre=nombre, descripcion=desc)
            db.add(rol)
        actuales = {p.nombre for p in rol.permisos}
        for pn in lista:
            if pn not in actuales:
                rol.permisos.append(permisos[pn])
    db.commit()
