/**
 * Utilidades puras del puente: conversión de audio y validación de números.
 */

/** Float32 [-1, 1] a PCM de 16 bits little-endian. */
export const floatAPcm16 = (muestras) => {
  const salida = Buffer.alloc(muestras.length * 2);
  for (let i = 0; i < muestras.length; i += 1) {
    const v = Math.max(-1, Math.min(1, muestras[i]));
    salida.writeInt16LE(Math.round(v < 0 ? v * 0x8000 : v * 0x7fff), i * 2);
  }
  return salida;
};

/** PCM de 16 bits little-endian a Float32 [-1, 1]. Ignora un byte suelto al final. */
export const pcm16AFloat = (bytes) => {
  const n = Math.floor(bytes.length / 2);
  const salida = new Float32Array(n);
  for (let i = 0; i < n; i += 1) {
    salida[i] = bytes.readInt16LE(i * 2) / 0x8000;
  }
  return salida;
};

/** Deja solo dígitos y valida longitud con código de país (10 a 15). */
export const normalizarNumero = (texto) => {
  let digitos = String(texto ?? "").replace(/\D/g, "");
  // 10 dígitos es un número de México sin lada de país: se agrega el 52
  if (digitos.length === 10) digitos = `52${digitos}`;
  if (!/^\d{10,15}$/.test(digitos)) {
    throw new Error("Usa el número con código de país, por ejemplo 522221234567");
  }
  return digitos;
};

/** Número de WhatsApp a partir del JID que devuelve onWhatsApp (p. ej. 5212221234567@s.whatsapp.net). */
export const numeroDeJid = (jid) => String(jid).split("@")[0].split(":")[0];
