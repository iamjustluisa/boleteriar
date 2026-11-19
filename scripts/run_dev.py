"""Levanta todo para desarrollo sin Docker: los 13 microservicios (8001-8013) y el gateway con el
frontend (8080). Necesita una base de datos (MySQL local o la de la nube configurada en .env).

Uso:  python -m scripts.run_dev          (Ctrl+C para detener todo)
"""
import os
import subprocess
import sys
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
from common.config import SERVICIOS  # noqa: E402

GATEWAY = os.getenv("GATEWAY_PORT", "8080")


def main() -> None:
    env = {**os.environ, "PYTHONUNBUFFERED": "1"}
    procesos = [(n, [sys.executable, "-m", "uvicorn", f"{n}.main:app", "--port", str(p),
                     "--log-level", "warning"]) for n, p in SERVICIOS.items()]
    procesos.append(("gateway", [sys.executable, "-m", "uvicorn", "gateway.main:app", "--host", "0.0.0.0",
                                 "--port", GATEWAY, "--log-level", "warning"]))
    hijos = [(n, subprocess.Popen(cmd, cwd=RAIZ, env=env)) for n, cmd in procesos]
    print(f"\n  Aplicación web:  http://localhost:{GATEWAY}\n"
          f"  Estado:          http://localhost:{GATEWAY}/api/estado\n"
          f"  Swagger:         http://localhost:{GATEWAY}/api/<servicio>/docs (ej. /api/eventos/docs)\n"
          "  (Ctrl+C para detener)\n")
    try:
        while all(p.poll() is None for _, p in hijos):
            time.sleep(1)
        for n, p in hijos:
            if p.poll() is not None:
                print(f"El proceso '{n}' terminó con código {p.returncode}.")
    except KeyboardInterrupt:
        pass
    finally:
        for _, p in hijos:
            if p.poll() is None:
                p.terminate()


if __name__ == "__main__":
    main()
