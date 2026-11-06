# Imagen del agente: bot de voz, programador y panel (mismo código, distinto comando).
FROM python:3.13-slim-bookworm

ENV PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH=/opt/venv/bin:$PATH \
    RUTA_DB=/datos/compania.db \
    CARPETA_AUDIOS=/datos/audios

RUN pip install --no-cache-dir uv==0.13.4

WORKDIR /app
# Primero solo las dependencias, para que un cambio de código no las vuelva a instalar
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv uv sync --frozen --no-dev --no-install-project
COPY src ./src
RUN --mount=type=cache,target=/root/.cache/uv uv sync --frozen --no-dev

RUN mkdir -p /datos/audios
WORKDIR /datos
VOLUME ["/datos"]
CMD ["compania-whatsapp"]
