# Imagen del puente de WhatsApp (Node + Baileys + ffmpeg para las notas de voz).
FROM node:20-bookworm-slim

RUN apt-get update \
 && apt-get install -y --no-install-recommends ffmpeg git ca-certificates \
 && rm -rf /var/lib/apt/lists/*
# baileys-caller se instala desde GitHub; dentro del contenedor no hay llaves SSH
RUN git config --global url."https://github.com/".insteadOf "ssh://git@github.com/"

ENV NODE_ENV=production \
    WA_AUTH_DIR=/auth

WORKDIR /app
COPY package.json package-lock.json ./
COPY patches ./patches
RUN npm ci --omit=dev && npm cache clean --force
COPY *.mjs ./

VOLUME ["/auth"]
CMD ["node", "supervisor.mjs"]
