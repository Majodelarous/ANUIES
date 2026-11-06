# Rous en Docker (Windows, macOS o Linux)

Con Docker no hace falta instalar Python, uv, Node, ffmpeg ni make: todo viene dentro de las imágenes. Es la forma recomendada para correr Rous en Windows.

Son cuatro contenedores que trabajan juntos:

| Servicio | Qué hace |
|---|---|
| `bot` | La voz de Rous (motor de IA) y la API que usa el puente |
| `puente` | La sesión de WhatsApp de la asistente: llamadas, grupo de la familia, imágenes |
| `programador` | Llamadas diarias, recordatorios y avisos si no contesta |
| `panel` | Panel de la familia en http://127.0.0.1:7861 |

Los datos viven en dos volúmenes de Docker que no se borran al detener o actualizar: `datos` (base de datos y notas de voz) y `auth` (sesión de WhatsApp).

## 1. Requisitos en Windows

Según la documentación de Docker Desktop (https://docs.docker.com/desktop/setup/install/windows-install/):

- Windows 10 de 64 bits versión 22H2 (compilación 19045) o Windows 11 de 64 bits versión 23H2 (compilación 22631) o posterior.
- WSL 2 versión 2.1.5 o posterior.
- 8 GB de RAM y virtualización activada en el BIOS/UEFI.

Además:

- Git para Windows: https://git-scm.com/download/win
- Unos 4 GB libres de disco para las imágenes (agente 1.6 GB, puente 1.2 GB).

## 2. Instalar Docker Desktop

1. Descargar el instalador de Docker Desktop para Windows y ejecutarlo.
2. En la configuración, elegir el motor WSL 2.
3. Abrir Docker Desktop desde el menú Inicio y aceptar los términos. Esperar a que diga que el motor está corriendo.
4. Comprobar en PowerShell:

```powershell
docker version
docker compose version
```

## 3. Bajar el proyecto y configurarlo

```powershell
git clone <url del repositorio> compania-voz
cd compania-voz
git switch docker            # mientras esta rama no se una a main
Copy-Item agente/.env.example agente/.env
notepad agente/.env
```

En `agente/.env` llenar al menos:

- La llave del motor de voz: `GOOGLE_API_KEY` (Gemini), `OPENAI_API_KEY` (OpenAI) o `AWS_ACCESS_KEY_ID` y `AWS_SECRET_ACCESS_KEY` (Nova). En Docker no sirve `AWS_PROFILE`: el perfil de AWS de la computadora no existe dentro del contenedor.
- `MOTOR_VOZ`: `gemini`, `openai` o `nova`.
- `WHATSAPP_ASISTENTE`, `WHATSAPP_PERSONA` y `WHATSAPP_GRUPO`.

No hace falta tocar puertos ni direcciones: `docker-compose.yml` los fija para los contenedores.

## 4. Levantar todo

```powershell
.\rous.ps1 arriba
```

La primera vez tarda varios minutos porque construye las imágenes. Si Windows no deja ejecutar el script, una sola vez:

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

Sin el script, el equivalente es `docker compose up -d --build`.

## 5. Vincular WhatsApp

```powershell
.\rous.ps1 qr
```

Aparece un QR. En el celular de la asistente: WhatsApp, Dispositivos vinculados, Vincular un dispositivo. Cuando el registro diga "Listo", salir con Ctrl+C (los contenedores siguen corriendo). La sesión queda guardada en el volumen `auth`.

## 6. Registrar a la persona y probar

```powershell
.\rous.ps1 persona -Nombre "Amada López" -Trato abuelita -Telefono 522221234567
.\rous.ps1 personas
.\rous.ps1 panel                 # horarios, recordatorios y mensajes
.\rous.ps1 llamar                # Rous llama a WHATSAPP_PERSONA
```

Agregar `-Consentimiento` solo si la persona ya firmó el consentimiento por escrito.

## 7. Uso diario

| Para | Comando | Sin el script |
|---|---|---|
| Levantar | `.\rous.ps1 arriba` | `docker compose up -d --build` |
| Ver qué corre | `.\rous.ps1 estado` | `docker compose ps` |
| Registro en vivo | `.\rous.ps1 logs` o `.\rous.ps1 logs puente` | `docker compose logs -f` |
| Rous llama | `.\rous.ps1 llamar` | `docker compose exec bot compania-llamar-wa` |
| Colgar | `.\rous.ps1 colgar` | `docker compose exec bot compania-llamar-wa --colgar` |
| Cambiar motor | `.\rous.ps1 motor openai` | editar `MOTOR_VOZ` y `docker compose up -d` |
| Respaldo | `.\rous.ps1 respaldo` | ver `rous.ps1` |
| Otro número de asistente | `.\rous.ps1 vincular` | ver `rous.ps1` |
| Detener | `.\rous.ps1 abajo` | `docker compose down` |

Después de cambiar `agente/.env`, `.\rous.ps1 arriba` vuelve a crear los contenedores con la configuración nueva.

En Linux o macOS están los mismos atajos en el Makefile: `make docker-arriba`, `make docker-qr`, `make docker-logs`, `make docker-llamar`, `make docker-persona`, `make docker-abajo`.

## 8. Datos, respaldos y entornos

- `.\rous.ps1 respaldo` deja dos archivos en la carpeta `respaldos`: la base con notas de voz y la sesión de WhatsApp. Guardarlos fuera de la computadora; la sesión permite usar el WhatsApp de la asistente.
- `docker compose down` conserva los datos. `docker compose down -v` los borra (base, notas de voz y sesión de WhatsApp).
- Para un entorno separado (por ejemplo, la persona real), con su propio `.env` y sus propios volúmenes:

```powershell
$env:ROUS_ENV = "agente/.env.prod"
docker compose -p rous-prod up -d --build
docker compose -p rous-prod logs -f --no-log-prefix puente
```

Solo puede correr un entorno a la vez porque comparten el puerto del panel.

## 9. Problemas comunes

| Qué pasa | Qué hacer |
|---|---|
| `env file ... agente/.env not found` | Falta copiar `agente/.env.example` a `agente/.env` |
| El bot aparece como "Restarting" | Ver `.\rous.ps1 logs bot`: casi siempre falta la llave del motor elegido |
| Docker Desktop no arranca | Revisar que la virtualización esté activa en el BIOS y que WSL 2 esté instalado (`wsl --update`) |
| El puerto 7861 está ocupado | Cerrar lo que lo use o cambiar `127.0.0.1:7861:7861` en `docker-compose.yml` |
| El QR no se ve bien | Agrandar la ventana de la terminal o reducir el tamaño de letra |
| La llamada se cuelga a los 5 s | El puente vuelve a marcar solo una vez; guardar el registro (`.\rous.ps1 logs puente`) |

## 10. Hacia el despliegue

`[INFERENCIA]` Este mismo `docker-compose.yml` sirve en un servidor con Docker (por ejemplo, una máquina virtual en AWS) sin cambios. Para servicios que corren cada contenedor por separado, como Railway, hay que revisar dos cosas antes: los tres servicios del agente comparten la base SQLite en un mismo volumen, y la sesión de WhatsApp necesita un volumen persistente.
