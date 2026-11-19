from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from common import auditoria
from common.errors import ErrorServicio, ServicioNoDisponible

from .clients import acceso_client
from .models import Usuario
from .schemas import ActualizarIn, RegistroIn


def _por_correo(db: Session, correo: str) -> Usuario | None:
    return db.scalar(select(Usuario).where(Usuario.correo == correo))


def registrar(db: Session, datos: RegistroIn) -> Usuario:
    """CU-01. Crea el usuario y, vía Control de Acceso, su credencial con rol 'usuario'.

    Como cada microservicio tiene su propia base, no hay una transacción única: si la
    credencial no se puede crear se compensa borrando el usuario recién creado, para no
    dejar usuarios sin forma de iniciar sesión.
    """
    if _por_correo(db, datos.correo):
        raise HTTPException(status.HTTP_409_CONFLICT, "El correo ya está registrado")
    if db.scalar(select(Usuario).where(Usuario.documento == datos.documento)):
        raise HTTPException(status.HTTP_409_CONFLICT, "El documento ya está registrado")

    usuario = Usuario(nombre=datos.nombre, apellido=datos.apellido, correo=datos.correo,
                      telefono=datos.telefono, documento=datos.documento)
    db.add(usuario)
    try:
        db.commit()
    except IntegrityError:  # condición de carrera con otro registro simultáneo
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "El correo o el documento ya están registrados")

    try:
        acceso_client.crear_credencial(usuario.id_usuario, datos.contrasena, "usuario")
    except (ServicioNoDisponible, ErrorServicio):
        db.delete(usuario)  # compensación (saga)
        db.commit()
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE,
                            "No se pudo completar el registro. Intenta de nuevo en unos minutos.")

    auditoria.registrar("REGISTRO_USUARIO", "USUARIO", usuario.id_usuario, usuario.id_usuario)
    return usuario


def actualizar(db: Session, id_usuario: int, datos: ActualizarIn) -> Usuario:
    """CU-02. Solo correo y teléfono; el correo nuevo debe seguir siendo único."""
    usuario = db.get(Usuario, id_usuario)
    if usuario is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Usuario no encontrado")

    if datos.correo is not None and datos.correo != usuario.correo:
        if _por_correo(db, datos.correo):
            raise HTTPException(status.HTTP_409_CONFLICT, "El correo ya pertenece a otro usuario")
        usuario.correo = datos.correo
    if datos.telefono is not None:
        usuario.telefono = datos.telefono
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "El correo ya pertenece a otro usuario")

    auditoria.registrar("ACTUALIZAR_USUARIO", "USUARIO", id_usuario, id_usuario)
    return usuario
