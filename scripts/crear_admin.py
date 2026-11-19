"""Crea (o promueve) un administrador. Los servicios deben estar corriendo.

Uso:  python -m scripts.crear_admin
Lee ADMIN_* del .env. Es idempotente: si el correo ya existe, solo lo promueve.
"""
import sys

import httpx

from common.config import settings
from scripts.seed import ADMIN, KEY, registrar


def main() -> int:
    id_usuario = registrar(ADMIN)
    r = httpx.put(f"{settings.url('acceso')}/internal/credenciales/{id_usuario}/rol",
                  json={"rol": "administrador"}, headers=KEY, timeout=30)
    if r.status_code != 200:
        print(f"Error: {r.status_code} {r.text}")
        return 1
    print(f"Listo: {ADMIN['correo']} es administrador (id={id_usuario}).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
