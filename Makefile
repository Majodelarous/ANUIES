# Comandos del prototipo. Ejecuta "make" para ver la ayuda.
#
# make dev levanta los cuatro servicios en una terminal (bot, puente de WhatsApp, programador
# y panel) y guarda todo en logs/ con fecha, para revisar después llamadas que fallaron.

SHELL := /bin/bash
.DEFAULT_GOAL := ayuda

LOGS := logs
HONCHO := uvx --quiet honcho
# Los procesos de Python escriben al momento y no al final (para que el log salga en orden)
export PYTHONUNBUFFERED := 1

.PHONY: ayuda instalar dev bot puente programador panel test llamar colgar log logs

ayuda: ## Muestra esta ayuda
	@grep -E '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*## "} {printf "  make %-12s %s\n", $$1, $$2}'

instalar: ## Instala dependencias de Python (uv) y de Node (aplica el parche del puente)
	cd agente && uv sync
	cd whatsapp && npm install

dev: ## Levanta bot, puente, programador y panel en esta terminal; guarda el log en logs/
	@mkdir -p $(LOGS)
	@archivo=$(LOGS)/dev-$$(date +%Y%m%d-%H%M%S).log; \
	echo "Log de esta sesión: $$archivo  (Ctrl+C detiene todo)"; \
	set -o pipefail; $(HONCHO) start -f Procfile 2>&1 | tee "$$archivo"

bot: ## Solo el bot de voz (websocket para el puente)
	cd agente && uv run compania-whatsapp

puente: ## Solo el puente de WhatsApp (supervisor)
	cd whatsapp && npm start

programador: ## Solo el programador de llamadas y recordatorios
	cd agente && uv run compania-programador

panel: ## Solo el panel de la familia (http://127.0.0.1:7861)
	cd agente && uv run compania-panel

test: ## Corre las pruebas de Python y de Node
	cd agente && uv run pytest -q
	cd whatsapp && npm test

llamar: ## Rous llama ahora (NUMERO=52... opcional; por omisión WHATSAPP_PERSONA)
	cd agente && uv run compania-llamar-wa $(NUMERO)

colgar: ## Cuelga la llamada en curso y libera el puente
	cd agente && uv run compania-llamar-wa --colgar

log: ## Sigue en vivo el log más reciente (útil desde otra terminal)
	@tail -f "$$(ls -t $(LOGS)/dev-*.log | head -1)"

logs: ## Lista los logs guardados
	@ls -lt $(LOGS)/ 2>/dev/null || echo "Aún no hay logs: usa make dev"
