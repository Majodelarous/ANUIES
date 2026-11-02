# Plan técnico

## Decisiones

| Decisión | Elección | Motivo |
|---|---|---|
| Orquestación de voz | Pipecat 1.15 | Código abierto (BSD-2), soporta Gemini Live y Nova Sonic, WebRTC y Twilio |
| Modelo de voz | Gemini Live por omisión; Nova Sonic como alternativa (`MOTOR_VOZ`) | Gemini tiene nivel gratuito para el prototipo; Nova se integra con AWS |
| Canales | WebRTC (navegador) y Twilio (teléfono) | El teléfono no requiere internet del lado de la persona |
| Persistencia | SQLite | Suficiente para el prototipo; se reemplaza por un servicio en la nube después |
| Herramientas | `FunctionSchema` con manejadores que llaman al dominio | Separar reglas del negocio del proveedor de voz |

## Capas

```
compania.agente          (Pipecat: bot, instrucciones, herramientas)
        |
compania.dominio         (bienestar, juegos, modelos, política de alertas)
        |
compania.infraestructura (repositorio SQLite)
```

## Herramientas del agente

| Herramienta | Contexto | Qué hace |
|---|---|---|
| `guardar_recuerdo` | Memoria de vida | Guarda tema, contenido y si se comparte |
| `buscar_recuerdos` | Memoria de vida | Devuelve recuerdos por tema o recientes |
| `obtener_juego` | Actividades | Entrega un juego de memoria no repetido |
| `registrar_resultado_juego` | Actividades | Guarda si acertó |
| `registrar_respuesta_bienestar` | Bienestar | Guarda una respuesta a una pregunta |
| `crear_recordatorio` | Cuidado | Crea un recordatorio con hora |
| `marcar_mensaje_entregado` | Cuidado | Marca un mensaje familiar como entregado |
| `generar_alerta` | Cuidado | Registra una alerta para la familia |

## Pendiente de decidir

- Voz de Gemini y de Nova en español que suene más natural (prueba con la persona real).
- Reproducción de audio con voz familiar dentro de la llamada.
- Panel familiar y notificaciones (WhatsApp o SMS).
