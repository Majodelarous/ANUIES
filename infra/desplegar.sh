#!/usr/bin/env bash
# Sube el .env al servidor, baja la última versión de la rama y levanta los contenedores.
# Uso, desde infra/ después de terraform apply:
#   ./desplegar.sh                 usa ../agente/.env
#   ./desplegar.sh ../agente/.env.prod
set -euo pipefail
cd "$(dirname "$0")"

ENV_LOCAL="${1:-../agente/.env}"
[ -f "$ENV_LOCAL" ] || { echo "No existe $ENV_LOCAL"; exit 1; }
IP="$(terraform output -raw ip)"
DESTINO="ubuntu@$IP"
SSH=(ssh -o StrictHostKeyChecking=accept-new "$DESTINO")

echo "Esperando a que el servidor termine de instalar Docker (la primera vez tarda unos minutos)..."
until "${SSH[@]}" test -f /var/lib/cloud/instance/rous-listo 2>/dev/null; do sleep 10; done

# AWS_PROFILE no existe en el servidor: Nova usa el rol de la instancia
TEMPORAL="$(mktemp)"
trap 'rm -f "$TEMPORAL"' EXIT
grep -v '^AWS_PROFILE=' "$ENV_LOCAL" > "$TEMPORAL"
scp -q "$TEMPORAL" "$DESTINO:/opt/rous/agente/.env"

"${SSH[@]}" 'chmod 600 /opt/rous/agente/.env && cd /opt/rous && git pull --ff-only && docker compose up -d --build && docker compose ps'

echo
echo "Listo. Para el panel, en otra terminal:"
echo "  $(terraform output -raw panel)"
echo "y abre http://127.0.0.1:7861/control"
