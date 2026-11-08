# Rous en AWS con Terraform

Una instancia EC2 con Docker que corre el mismo `docker-compose.yml` que en la laptop, más Caddy para servir el panel por HTTPS en **https://rous.foor.dev/control** con contraseña. Todo lo crea y lo borra Terraform; lo único manual es el registro de Cloudflare.

Qué se crea:

| Recurso | Para qué |
|---|---|
| EC2 `t3.small` con Ubuntu 24.04, disco gp3 de 30 GB cifrado | Corre bot, puente, programador, panel y Caddy |
| IP fija (Elastic IP) | El registro de Cloudflare no cambia si la instancia se reinicia |
| Grupo de seguridad | 22 solo desde tu IP; 80 y 443 abiertos para el panel |
| Llave SSH | Tu llave pública de `~/.ssh` |
| Rol de IAM | Session Manager (entrar aunque cambie tu IP) y permiso para Nova Sonic sin llaves en el `.env` |

El primer arranque instala Docker, pone la zona horaria de México, crea 2 GB de memoria de intercambio y clona el repositorio en `/opt/rous`. El `.env` no viaja en Terraform (quedaría en el estado); lo sube `desplegar.sh`.

## 0. Antes de empezar

Requisitos en la laptop: Terraform 1.10 o posterior, AWS CLI con el perfil `Fortino-IAM-Admin` y una llave SSH (`ssh-keygen -t ed25519` si no tienes).

El estado de Terraform queda local en `infra/terraform.tfstate` (está en `.gitignore`). Si después quieres un bucket para estados, copia `backend.tf.ejemplo` como `backend.tf` y corre `terraform init -migrate-state`.

Contraseña del panel (la misma para Fortino y Majo):

```bash
cd agente
uv run compania-panel-clave        # pide la contraseña dos veces e imprime PANEL_CLAVE_HASH=...
```

Agrega esa línea a `agente/.env`. Se guarda solo el hash, no la contraseña. Si la pones en el `.env` de la laptop, el panel local también la pedirá; si prefieres que no, usa un `.env` aparte para el servidor (paso 2).

## 1. Crear el servidor

```bash
cd infra
cp terraform.tfvars.ejemplo terraform.tfvars
curl -s https://checkip.amazonaws.com        # tu IP; ponla en mi_ip con /32
terraform init
terraform plan                               # revisa que solo cree lo de la tabla
terraform apply
terraform output -raw cloudflare
```

## 2. Registro en Cloudflare

En Cloudflare, zona `foor.dev`, DNS, Agregar registro, con lo que imprimió `terraform output -raw cloudflare`:

| Campo | Valor |
|---|---|
| Tipo | A |
| Nombre | `rous` |
| Dirección IPv4 | la IP de `terraform output -raw ip` |
| Proxy | Desactivado (solo DNS, nube gris) |
| TTL | Automático |

Con el proxy desactivado, Caddy recibe la conexión directa y saca el certificado de Let's Encrypt solo. Si la zona tiene registros CAA, deben permitir `letsencrypt.org`.

## 3. Subir el .env y levantar Rous

```bash
./desplegar.sh                               # usa ../agente/.env
./desplegar.sh ../agente/.env.nube           # o un .env aparte para el servidor
```

El script:
- Revisa que el `.env` tenga `PANEL_CLAVE_HASH`; sin contraseña no despliega.
- Espera a que termine el primer arranque y sube el `.env` sin `AWS_PROFILE` (en el servidor Nova usa el rol).
- Activa Caddy con el dominio, baja la última versión de la rama y construye las imágenes. La primera vez tarda unos 10 minutos.

## 4. Abrir el panel

**https://rous.foor.dev/control** desde la computadora o el teléfono, con la contraseña. Ahí está el QR para vincular el WhatsApp de la asistente y la guía de la demo en https://rous.foor.dev/guia.

Antes de vincular en el servidor, apaga el puente de la laptop y el de cualquier otra computadora: con dos sesiones Rous puede contestar doble.

Plan B si el dominio falla: `terraform output -raw tunel`, y con el túnel abierto http://127.0.0.1:7861/control.

## 5. Actualizar después de un cambio

Sube los cambios a GitHub y vuelve a correr `./desplegar.sh`. Los datos, la sesión de WhatsApp y el certificado viven en volúmenes de Docker y no se pierden. Grupo, prefijo, nombre de la asistente y número de la persona se cambian en el panel sin redesplegar.

## 6. Borrar todo

```bash
terraform destroy
```

Borra la instancia, su disco (base de datos y sesión de WhatsApp incluidas) y la IP fija. Después borra el registro `rous` en Cloudflare. Para conservar los datos, antes:

```bash
ssh ubuntu@$(terraform output -raw ip) 'cd /opt/rous && docker compose run --rm --no-deps -v /tmp:/respaldo bot tar czf /respaldo/datos.tgz -C /datos .'
scp ubuntu@$(terraform output -raw ip):/tmp/datos.tgz .
```

## Costos

- `t3.small` aparece como elegible del plan gratuito en la cuenta (consulta `aws ec2 describe-instance-types --filters Name=free-tier-eligible,Values=true`).
- La IP pública se cobra por hora: USD 0.005 por hora según el anuncio de AWS (https://aws.amazon.com/about-aws/whats-new/2024/02/aws-free-tier-750-hours-free-public-ipv4-addresses/). En cuentas con créditos se descuenta de ellos.
- Con `cpu_credits = "standard"` la instancia nunca cobra CPU extra; si se agotan los créditos solo va más lenta.

## Seguridad

- El panel pide contraseña; la sesión dura 7 días en una cookie firmada, solo por HTTPS y sin acceso desde JavaScript. Tras 5 intentos fallidos desde una IP (o 40 en total) se bloquea 15 minutos.
- Si falta `PANEL_CLAVE_HASH`, el panel en el servidor no abre.
- El panel rechaza envíos de formularios que vengan de otros sitios.
- SSH solo desde tu IP.

## Problemas comunes

| Qué pasa | Qué hacer |
|---|---|
| El navegador dice que el certificado no es válido | El registro de Cloudflare no existe, apunta a otra IP o tiene el proxy activado. Revisa y espera un minuto: Caddy reintenta solo |
| "Panel cerrado: falta PANEL_CLAVE_HASH" | Agrega la línea al `.env` y corre `./desplegar.sh` |
| "Demasiados intentos" | Espera 15 minutos, o reinicia el panel: `ssh ... 'cd /opt/rous && docker compose restart panel'` |
| `ssh` se queda esperando | Cambió tu IP: actualiza `mi_ip` y `terraform apply`, o entra con `terraform output -raw sin_ssh` |
| `desplegar.sh` espera mucho | El primer arranque sigue instalando. En el servidor: `sudo tail -f /var/log/cloud-init-output.log` |
| El bot se reinicia en bucle | Falta la llave del motor elegido en el `.env`. `docker compose logs bot` en `/opt/rous` |
