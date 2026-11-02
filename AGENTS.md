# Reglas de ejecución

Reglas para cualquier persona o agente que modifique este repositorio.

## Antes de cambiar algo

1. Leer `docs/constitucion.md`. Ningún cambio puede contradecirla.
2. Ubicar la historia de usuario en `docs/spec.md` y la tarea en `docs/tasks.md`. Si no existe, agregarla primero.
3. Usar los términos de `docs/lenguaje-ubicuo.md` en código, pruebas y documentos.

## Código

- Python con uv. Dependencias solo con `uv add`.
- El paquete `compania.dominio` no importa Pipecat, SQLite ni servicios externos.
- La infraestructura implementa los puertos que define el dominio.
- Cada herramienta del agente tiene prueba en `agente/tests`.
- Llaves y secretos solo en `agente/.env`; nunca en el repositorio.
- Formato y orden de imports con `ruff`.

## Verificación

```bash
cd agente
uv run ruff check .
uv run pytest
```

Una tarea se marca como hecha en `docs/tasks.md` solo cuando sus criterios de aceptación se cumplen y las pruebas pasan.

## Commits

Mensajes breves en español con prefijo convencional: `feat:`, `fix:`, `docs:`, `test:`, `chore:`, `refactor:`.
