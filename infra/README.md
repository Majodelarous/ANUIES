# Rous en AWS con Terraform

Una instancia EC2 con Docker que corre el mismo `docker-compose.yml` que en la laptop. Todo lo crea y lo borra Terraform; nada se hace a mano en la consola.

Qué se crea:

| Recurso | Para qué |
|---|---|
| EC2 `t3.small` con Ubuntu 24.04, disco gp3 de 30 GB cifrado | Corre los cuatro contenedores |
| Grupo de seguridad | Solo el puerto 22, solo desde tu IP. El panel nunca queda en internet |
| Llave SSH | Tu llave pública de `~/.ssh` |
| Rol de IAM | Session Manager (entrar aunque cambie tu IP) y permiso para Nova Sonic sin llaves en el `.env` |

El primer arranque instala Docker, pone la zona horaria de México, crea 2 GB de memoria de intercambio y clona el repositorio en `/opt/rous`. El `.env` no viaja en Terraform (quedaría en el estado); lo sube `desplegar.sh`.

## 0. Antes de empezar

Requisitos en la laptop: Terraform 1.10 o posterior, AWS CLI con el perfil `Fortino-IAM-Admin` y una llave SSH (`ssh-keygen -t ed25519` si no tienes).

Revisar qué tipos entran en el plan gratuito de tu cuenta:

```bash
aws ec2 describe-instance-types --region us-east-1 --profile Fortino-IAM-Admin \
  --filters Name=free-tier-eligible,Values=true \
  --query 'InstanceTypes[].InstanceType' --output text
```

Si `t3.small` no aparece, revisa antes de cambiar `tipo_instancia`: `t3.micro` tiene 1 GB y se queda corta, y `t4g.small` es ARM, donde las imágenes todavía no se han probado.

Revisar si ya hay un bucket para estados de Terraform:

```bash
aws s3 ls --profile Fortino-IAM-Admin
```

- Si hay uno: `cp backend.tf.ejemplo backend.tf`, pon el nombre del bucket y sigue.
- Si no: no hagas nada; el estado queda en `infra/terraform.tfstate` (está en `.gitignore`).

## 1. Crear el servidor

```bash
cd infra
cp terraform.tfvars.ejemplo terraform.tfvars
curl -s https://checkip.amazonaws.com        # tu IP; ponla en mi_ip con /32
terraform init
terraform plan                               # revisa que solo cree lo de la tabla
terraform apply
```

## 2. Subir el .env y levantar Rous

```bash
./desplegar.sh                               # usa ../agente/.env
```

Espera a que termine el primer arranque, sube el `.env` sin la línea `AWS_PROFILE` (en el servidor Nova usa el rol), baja la última versión de la rama y construye las imágenes. La primera vez tarda unos 10 minutos.

## 3. Abrir el panel

```bash
terraform output -raw panel                  # copia y corre el comando en otra terminal
```

Con el túnel abierto, entra a http://127.0.0.1:7861/control. Ahí está el QR para vincular el WhatsApp de la asistente y la guía de la demo en http://127.0.0.1:7861/guia.

Antes de vincular en el servidor, apaga el puente de la laptop y el de cualquier otra computadora: con dos sesiones Rous puede contestar doble.

## 4. Actualizar después de un cambio

Sube los cambios a GitHub y vuelve a correr `./desplegar.sh`. Los datos y la sesión de WhatsApp viven en volúmenes de Docker y no se pierden.

## 5. Borrar todo

```bash
terraform destroy
```

Borra la instancia y su disco, con la base de datos y la sesión de WhatsApp. Si quieres conservarlas, antes copia un respaldo:

```bash
ssh ubuntu@$(terraform output -raw ip) 'cd /opt/rous && docker compose run --rm --no-deps -v /tmp:/respaldo bot tar czf /respaldo/datos.tgz -C /datos .'
scp ubuntu@$(terraform output -raw ip):/tmp/datos.tgz .
```

## Costos

- La instancia y el disco entran en el plan gratuito según el tipo de cuenta; revisa el comando del paso 0 y la consola de Billing.
- La IP pública se cobra por hora fuera del plan gratuito: USD 0.005 por hora, según el anuncio de AWS (https://aws.amazon.com/about-aws/whats-new/2024/02/aws-free-tier-750-hours-free-public-ipv4-addresses/). En cuentas con créditos se descuenta de ellos.
- Con `cpu_credits = "standard"` la instancia nunca cobra CPU extra; si se agotan los créditos solo va más lenta.

## Problemas comunes

| Qué pasa | Qué hacer |
|---|---|
| `ssh` se queda esperando | Cambió tu IP: actualiza `mi_ip` y `terraform apply`, o entra con `terraform output -raw sin_ssh` |
| `desplegar.sh` espera mucho | El primer arranque sigue instalando. En el servidor: `sudo tail -f /var/log/cloud-init-output.log` |
| El bot se reinicia en bucle | Falta la llave del motor elegido en el `.env`. `docker compose logs bot` en `/opt/rous` |
| Nova no funciona en el servidor | Revisa que `permitir_nova` sea `true` y que tu cuenta tenga acceso al modelo en Bedrock |
