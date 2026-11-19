"""Envío de notificaciones al microservicio de Notificaciones (RF-NOT-01 a 03, RN21).

Igual que la auditoría, se envía en segundo plano para no frenar la operación principal.
"""
import logging
from concurrent.futures import ThreadPoolExecutor

_log = logging.getLogger("boleteria.notificar")
_pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="notificar")


def _enviar(datos: dict) -> None:
    from .clients import notificaciones
    try:
        notificaciones.post("/internal/notificaciones", datos)
    except Exception as exc:
        _log.warning("No se pudo registrar la notificación: %s", exc)


def notificar(id_usuario: int, tipo: str, id_referencia: int, mensaje: str) -> None:
    _pool.submit(_enviar, {"id_usuario": id_usuario, "tipo": tipo,
                           "id_referencia": id_referencia, "mensaje": mensaje[:255]})
