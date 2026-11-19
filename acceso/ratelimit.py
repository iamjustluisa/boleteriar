"""Límite de intentos de login fallidos por (IP, correo). En memoria: vale para una sola
instancia del servicio; con varias réplicas habría que moverlo a Redis o a la base."""
import threading
import time


class LimiteIntentos:
    def __init__(self, maximo: int, ventana_seg: int) -> None:
        self.maximo, self.ventana = maximo, ventana_seg
        self._fallos: dict[str, list[float]] = {}
        self._lock = threading.Lock()

    def _podar(self, clave: str, ahora: float) -> list[float]:
        vivos = [t for t in self._fallos.get(clave, []) if ahora - t < self.ventana]
        if vivos:
            self._fallos[clave] = vivos
        else:
            self._fallos.pop(clave, None)
        return vivos

    def segundos_restantes(self, clave: str) -> int:
        """0 si puede intentar; si no, segundos hasta que se libere."""
        ahora = time.monotonic()
        with self._lock:
            vivos = self._podar(clave, ahora)
            if len(vivos) >= self.maximo:
                return max(1, int(self.ventana - (ahora - vivos[0])))
        return 0

    def fallo(self, clave: str) -> None:
        with self._lock:
            self._fallos.setdefault(clave, []).append(time.monotonic())

    def exito(self, clave: str) -> None:
        with self._lock:
            self._fallos.pop(clave, None)
