/**
 * Compuerta: deja pasar peticiones solo cuando el puente está listo; si no, las hace esperar.
 */
export class Compuerta {
  #abierta = false;
  #esperando = [];

  get abierta() {
    return this.#abierta;
  }

  abrir() {
    this.#abierta = true;
    for (const { resolver, temporizador } of this.#esperando.splice(0)) {
      clearTimeout(temporizador);
      resolver();
    }
  }

  cerrar() {
    this.#abierta = false;
  }

  /** Se resuelve cuando la compuerta se abre; falla si pasa `maxMs`. */
  esperar(maxMs) {
    if (this.#abierta) return Promise.resolve();
    return new Promise((resolver, rechazar) => {
      const entrada = { resolver };
      entrada.temporizador = setTimeout(() => {
        this.#esperando = this.#esperando.filter((e) => e !== entrada);
        rechazar(new Error("El puente no estuvo listo a tiempo"));
      }, maxMs);
      this.#esperando.push(entrada);
    });
  }
}

/** Espera entre reinicios: crece si el puente se cae apenas arranca, para no ciclarse. */
export const esperaReinicio = (caidasSeguidas) => Math.min(60_000, 1_000 * 2 ** Math.max(0, caidasSeguidas - 1));
