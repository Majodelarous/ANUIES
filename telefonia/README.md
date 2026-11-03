# Telefonía por app (Asterisk + Linphone)

Demo sin operador telefónico: Asterisk corre en Docker en la misma máquina que el bot y la persona recibe la llamada en Linphone (app SIP de código abierto) por internet o wifi. En producción se agrega un troncal SIP a este mismo Asterisk para llamar a cualquier teléfono.

```
Linphone (celular) <-- SIP/RTP --> Asterisk (Docker) <-- websocket, slin16 --> compania-asterisk (bot)
```

## Pasos

1. Crear la cuenta de Linphone: `./configurar.sh abue` (anota usuario, contraseña e IP).
2. Levantar Asterisk: `docker compose up -d`.
3. En `agente/`: `uv sync --extra nova --extra telefonia` y `uv run compania-asterisk` (puerto 7862).
4. En Linphone: escanea el código QR que muestra `configurar.sh` (o `./qr.sh abue` después), o configura a mano "Usar cuenta SIP" con usuario, contraseña, dominio = IP de la laptop y transporte UDP. Celular y laptop en el mismo wifi. El QR apunta a un archivo servido 5 minutos en tu red local con la huella de la contraseña, no la contraseña.
5. Que la asistente llame: `uv run compania-llamar-app abue`. O desde Linphone marcar `100` para hablar con la asistente.

Diagnóstico: `docker exec -it compania-asterisk asterisk -rvvv` y `pjsip show endpoints`.

Los archivos de `asterisk/` parten del ejemplo de [pipecat-asterisk](https://github.com/NikolayShakin/pipecat-asterisk) (BSD-2-Clause).
