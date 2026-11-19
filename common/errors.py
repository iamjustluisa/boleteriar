class ServicioNoDisponible(Exception):
    """El otro microservicio no respondió (caído, timeout, red)."""


class ErrorServicio(Exception):
    """El otro microservicio respondió con un error de negocio."""

    def __init__(self, status: int, detalle, servicio: str | None = None):
        self.datos = detalle if isinstance(detalle, dict) else None
        texto = detalle.get("mensaje", str(detalle)) if isinstance(detalle, dict) else str(detalle)
        super().__init__(texto)
        self.status = status
        self.detalle = texto
        self.servicio = servicio
