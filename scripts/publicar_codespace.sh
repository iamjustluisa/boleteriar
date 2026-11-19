#!/usr/bin/env bash
# Vuelve públicos los puertos del Codespace para compartir el enlace con el profesor.
# Uso (dentro del Codespace):  bash scripts/publicar_codespace.sh
set -e
if [ -z "$CODESPACE_NAME" ]; then echo "Este script se ejecuta dentro de un GitHub Codespace."; exit 1; fi
gh codespace ports visibility 8080:public 8081:public -c "$CODESPACE_NAME"
DOM="${GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN:-app.github.dev}"
echo
echo "  Aplicación:     https://${CODESPACE_NAME}-8080.${DOM}"
echo "  Base de datos:  https://${CODESPACE_NAME}-8081.${DOM}   (Adminer · servidor: mysql · usuario: boleteria)"
echo "  Estado:         https://${CODESPACE_NAME}-8080.${DOM}/#/sistema"
echo
