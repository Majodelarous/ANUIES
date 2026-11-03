#!/usr/bin/env bash
# Muestra un código QR para configurar Linphone con la cuenta creada por configurar.sh.
# Linphone descarga la cuenta desde una URL de esta laptop (solo en tu red local y por tiempo limitado).
# Uso: ./qr.sh [cuenta] [minutos]
set -euo pipefail
cuenta="${1:-abue}"
minutos="${2:-5}"
cd "$(dirname "$0")"

cuentas="asterisk/pjsip_cuentas.conf"
[[ -f "$cuentas" ]] || { echo "No existe $cuentas. Ejecuta primero: ./configurar.sh $cuenta"; exit 1; }
clave="$(awk -v c="[$cuenta](auth-app)" '$0==c{f=1;next} /^\[/{f=0} f && /^password/{print $3}' "$cuentas")"
[[ -n "$clave" ]] || { echo "La cuenta '$cuenta' no está en $cuentas"; exit 1; }

ip="$(ip route get 1.1.1.1 2>/dev/null | awk '{for(i=1;i<=NF;i++) if($i=="src") print $(i+1)}' || true)"
ip="${ip:-$(hostname -I | awk '{print $1}' || true)}"
# Primer puerto libre entre 8090 y 8099 (o el de QR_PUERTO)
puerto="${QR_PUERTO:-$(python3 - "$ip" <<'PY'
import socket, sys
for p in range(8090, 8100):
    with socket.socket() as s:
        try:
            s.bind((sys.argv[1], p))
        except OSError:
            continue
        print(p)
        break
PY
)}"
[[ -n "$puerto" ]] || { echo "No hay puertos libres entre 8090 y 8099; define QR_PUERTO"; exit 1; }
# Huella de la contraseña (realm por omisión de Asterisk) para no enviar la contraseña en texto
ha1="$(printf '%s:asterisk:%s' "$cuenta" "$clave" | md5sum | awk '{print $1}')"

dir="$(mktemp -d)"
trap 'rm -rf "$dir"' EXIT
cat > "$dir/linphone.xml" <<XML
<?xml version="1.0" encoding="UTF-8"?>
<config xmlns="http://www.linphone.org/xsds/lpconfig.xsd">
  <section name="proxy_0">
    <entry name="reg_identity" overwrite="true">sip:$cuenta@$ip</entry>
    <entry name="reg_proxy" overwrite="true">&lt;sip:$ip:5060;transport=udp&gt;</entry>
    <entry name="reg_sendregister" overwrite="true">1</entry>
    <entry name="reg_expires" overwrite="true">600</entry>
    <entry name="realm" overwrite="true">asterisk</entry>
  </section>
  <section name="auth_info_0">
    <entry name="username" overwrite="true">$cuenta</entry>
    <entry name="ha1" overwrite="true">$ha1</entry>
    <entry name="realm" overwrite="true">asterisk</entry>
    <entry name="domain" overwrite="true">$ip</entry>
    <entry name="algorithm" overwrite="true">MD5</entry>
  </section>
  <section name="sip">
    <entry name="media_encryption" overwrite="true">none</entry>
    <entry name="media_encryption_mandatory" overwrite="true">0</entry>
  </section>
  <section name="misc">
    <entry name="transient_provisioning" overwrite="true">1</entry>
  </section>
</config>
XML

url="http://$ip:$puerto/linphone.xml"
echo "En Linphone: Asistente > Configurar con código QR y escanea:"
echo
if command -v qrencode >/dev/null; then
  qrencode -t ansiutf8 "$url" || true
elif command -v uvx >/dev/null; then
  uvx --quiet --from qrcode python -c 'import qrcode, sys
q = qrcode.QRCode(border=1)
q.add_data(sys.argv[1])
q.print_ascii(invert=True)' "$url" || echo "(No se pudo dibujar el QR; usa la URL de abajo)"
else
  echo "(No se encontró qrencode ni uvx; genera el QR con tu herramienta usando esta URL)"
fi
echo
echo "URL: $url"
echo "Disponible por $minutos minutos en tu red local. Ctrl+C para cerrar antes."
timeout "$((minutos * 60))" python3 -m http.server "$puerto" --bind "$ip" --directory "$dir" || true
echo "Listo. El archivo de configuración se borró."
