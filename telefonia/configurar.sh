#!/usr/bin/env bash
# Crea la cuenta SIP para Linphone con una contraseña aleatoria.
# Uso: ./configurar.sh abue
set -euo pipefail
cuenta="${1:-abue}"
clave="$(head -c 12 /dev/urandom | base64 | tr -dc 'A-Za-z0-9' | head -c 16)"
cd "$(dirname "$0")"
cat > asterisk/pjsip_cuentas.conf <<CONF
[$cuenta](cuenta-app)
auth = $cuenta
aors = $cuenta
callerid = Compania <100>

[$cuenta](auth-app)
username = $cuenta
password = $clave

[$cuenta](aor-app)
CONF
ip="$(hostname -I 2>/dev/null | awk '{print $1}')"
echo "Cuenta creada para Linphone:"
echo "  Usuario:     $cuenta"
echo "  Contraseña:  $clave"
echo "  Dominio:     ${ip:-<IP de esta laptop>}"
echo "  Transporte:  UDP"
echo "Si Asterisk ya está corriendo: docker exec compania-asterisk asterisk -rx 'module reload res_pjsip.so'"
