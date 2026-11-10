#!/usr/bin/env bash
# Sube el .env al servidor, baja la última versión de la rama y levanta los contenedores.
# Uso, desde infra/ después de terraform apply:
#   ./desplegar.sh                 usa ../agente/.env
#   ./desplegar.sh ../agente/.env.prod
set -euo pipefail
cd "$(dirname "$0")"

ENV_LOCAL="${1:-../agente/.env}"
[ -f "$ENV_LOCAL" ] || { echo "No existe $ENV_LOCAL"; exit 1; }
if ! grep -q '^PANEL_CLAVE_HASH=pbkdf2_sha256:' "$ENV_LOCAL"; then
  echo "Falta PANEL_CLAVE_HASH en $ENV_LOCAL: el panel queda en internet y necesita contraseña."
  echo "Genérala con: (cd ../agente && uv run compania-panel-clave)"
  exit 1
fi
IP="$(terraform output -raw ip)"
DOMINIO="$(terraform output -raw dominio)"
DESTINO="ubuntu@$IP"
SSH=(ssh -o StrictHostKeyChecking=accept-new "$DESTINO")

echo "Esperando a que el servidor termine de instalar Docker (la primera vez tarda unos minutos)..."
until "${SSH[@]}" test -f /var/lib/cloud/instance/rous-listo 2>/dev/null; do sleep 10; done

# AWS_PROFILE no existe en el servidor (Nova usa el rol de la instancia) y el token de
# Cloudflare solo lo usa Terraform en tu computadora: ninguno de los dos se sube
TEMPORAL="$(mktemp)"
trap 'rm -f "$TEMPORAL"' EXIT
grep -v -E '^(AWS_PROFILE|CLOUDFLARE_[A-Z_]*)=' "$ENV_LOCAL" > "$TEMPORAL"
scp -q "$TEMPORAL" "$DESTINO:/opt/rous/agente/.env"

# En el servidor, docker compose usa también docker-compose.nube.yml (Caddy) y el dominio
"${SSH[@]}" "printf 'COMPOSE_FILE=docker-compose.yml:docker-compose.nube.yml\nROUS_DOMINIO=%s\n' '$DOMINIO' > /opt/rous/.env"
"${SSH[@]}" 'chmod 600 /opt/rous/agente/.env && cd /opt/rous && git pull --ff-only && docker compose up -d --build --remove-orphans && docker compose ps'

if [ "$(dig +short "$DOMINIO" 2>/dev/null | sort -u | tr -d '\n')" != "$IP" ]; then
  echo
  echo "Ojo: $DOMINIO todavía no responde solo con $IP: $(dig +short "$DOMINIO" | tr '\n' ' ')"
  echo "Terraform maneja el registro; si hay otro registro de $DOMINIO en Cloudflare, bórralo."
  echo "Caddy saca el certificado solo en cuanto el nombre apunte nada más a $IP."
fi
echo
echo "Listo: $(terraform output -raw panel)"
