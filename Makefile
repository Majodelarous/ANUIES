# Comandos del prototipo. Ejecuta "make" para ver la ayuda.
#
# make dev levanta los cuatro servicios en una terminal (bot, puente de WhatsApp, programador
# y panel) y guarda todo en logs/ con fecha, para revisar después llamadas que fallaron.

SHELL := /bin/bash
.DEFAULT_GOAL := ayuda

LOGS := logs
HONCHO := uvx --quiet honcho
ENTORNO_PY := uv run --quiet --no-project python scripts/entorno.py
# Los procesos de Python escriben al momento y no al final (para que el log salga en orden)
export PYTHONUNBUFFERED := 1

.PHONY: ayuda instalar dev bot puente programador panel test llamar colgar log logs \
	entorno nuevo-entorno usar poner motor persona personas telefono respaldo limpiar vincular

ayuda: ## Muestra esta ayuda
	@grep -E '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*## "} {printf "  make %-14s %s\n", $$1, $$2}'

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

# --- Entornos, personas y WhatsApp (ver OPERACION.md) ---------------------------------

entorno: ## Muestra el entorno activo: motor de IA, números, grupo y dónde están los datos
	@$(ENTORNO_PY) mostrar

nuevo-entorno: ## Crea un entorno con datos separados: make nuevo-entorno ENTORNO=prod
	@test -n "$(ENTORNO)" || (echo "Falta ENTORNO, por ejemplo: make nuevo-entorno ENTORNO=prod" && exit 1)
	@$(ENTORNO_PY) crear $(ENTORNO)

usar: ## Cambia de entorno (servicios apagados): make usar ENTORNO=prod
	@test -n "$(ENTORNO)" || (echo "Falta ENTORNO, por ejemplo: make usar ENTORNO=prod" && exit 1)
	@$(ENTORNO_PY) usar $(ENTORNO)

poner: ## Cambia una variable del entorno activo: make poner CLAVE=WHATSAPP_GRUPO VALOR="Familia López"
	@test -n "$(CLAVE)" || (echo "Falta CLAVE, por ejemplo: make poner CLAVE=WHATSAPP_PERSONA VALOR=522221234567" && exit 1)
	@$(ENTORNO_PY) poner "$(CLAVE)" "$(VALOR)"

motor: ## Cambia el motor de voz: make motor MOTOR=gemini, nova u openai
	@test -n "$(MOTOR)" || (echo "Falta MOTOR: gemini, nova u openai" && exit 1)
	@$(ENTORNO_PY) poner MOTOR_VOZ "$(MOTOR)"

persona: ## Registra a la persona: make persona NOMBRE="Amada" TRATO="abuelita" TELEFONO=52... [CONSENTIMIENTO=si]
	@test -n "$(NOMBRE)" -a -n "$(TRATO)" || (echo 'Faltan datos: make persona NOMBRE="Amada López" TRATO="abuelita" TELEFONO=522221234567' && exit 1)
	cd agente && uv run compania-semilla --nombre "$(NOMBRE)" --trato "$(TRATO)" \
		$(if $(TELEFONO),--telefono "$(TELEFONO)") $(if $(CONTACTO),--contacto "$(CONTACTO)") \
		$(if $(filter si,$(CONSENTIMIENTO)),--consentimiento)

personas: ## Lista las personas de la base del entorno activo
	@cd agente && uv run --quiet compania-datos personas

telefono: ## Cambia el WhatsApp de una persona: make telefono ID=1 NUMERO=522221234567
	@test -n "$(ID)" -a -n "$(NUMERO)" || (echo "Uso: make telefono ID=1 NUMERO=522221234567" && exit 1)
	@cd agente && uv run --quiet compania-datos telefono $(ID) $(NUMERO)

respaldo: ## Copia base, notas de voz y sesión de WhatsApp del entorno activo a respaldos/
	@$(ENTORNO_PY) respaldo

limpiar: ## Vacía base y notas de voz del entorno activo (las guarda en respaldos/): CONFIRMAR=si
	@$(ENTORNO_PY) limpiar $(if $(filter si,$(CONFIRMAR)),--si)

vincular: ## Quita la sesión de WhatsApp y muestra un QR nuevo para vincular otro número: CONFIRMAR=si
	@$(ENTORNO_PY) desvincular $(if $(filter si,$(CONFIRMAR)),--si)
	@echo "Escanea el QR desde WhatsApp > Dispositivos vinculados del número de la asistente."
	@echo "Cuando diga Listo, detén con Ctrl+C y levanta todo con: make dev"
	cd whatsapp && npm run puente
