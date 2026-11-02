# Especificación

## Historias de usuario

### HU-01 Platicar por voz

Como persona adulta mayor, quiero platicar por voz con la asistente desde mi teléfono o desde el navegador, para sentirme acompañada.

Criterios de aceptación:

1. La asistente saluda usando el trato configurado y dice que es una asistente en la primera llamada.
2. Habla en español, con frases cortas.
3. Tolera silencios de al menos 0.8 segundos sin interrumpir.
4. La llamada queda registrada con inicio y fin.

### HU-02 Recordar mi historia

Como persona, quiero que la asistente recuerde lo que le conté, para no repetirlo y sentir que me conoce.

1. Cuando la persona cuenta algo significativo y acepta guardarlo, se registra un recuerdo con tema y contenido.
2. La persona puede decir si el recuerdo se comparte con la familia (por omisión, no se comparte).
3. Al iniciar una llamada, la asistente conoce los recuerdos más recientes y puede retomarlos.

### HU-03 Jugar a recordar

Como persona, quiero juegos de memoria por voz, para ejercitar la mente.

1. Hay al menos tres tipos: refranes, adivinanzas y lista de palabras.
2. Un juego no se repite en la misma llamada.
3. El resultado (acertó o no) se registra.

### HU-04 Señal de bienestar

Como familiar, quiero ver una señal semanal del ánimo de mi mamá, para saber cuándo acercarme.

1. La asistente hace como máximo dos preguntas de bienestar por llamada, de forma natural.
2. Las respuestas se guardan con fecha.
3. La señal se calcula con las respuestas de los últimos 14 días: verde, amarillo, rojo o insuficiente.
4. Con menos de 5 preguntas respondidas la señal es "insuficiente".
5. Una alerta de crisis en el periodo pone la señal en rojo.
6. Se presenta siempre como tendencia, no como diagnóstico.

### HU-05 Recordatorios y mensajes

Como familiar, quiero dejar recordatorios y mensajes, para que la asistente se los entregue a mi abuela.

1. Los recordatorios tienen texto y hora; la asistente menciona los pendientes del día.
2. Los mensajes familiares pendientes se entregan en la siguiente llamada y se marcan como entregados.
3. (Siguiente iteración) Un mensaje puede incluir audio con voz familiar consentida.

### HU-06 Alertas

Como contacto de emergencia, quiero recibir una alerta si algo va mal.

1. La asistente puede generar alertas de nivel informativo, atención o crisis.
2. En crisis, la asistente comparte la Línea de la Vida (800 911 2000).
3. Las alertas quedan registradas para el panel familiar.

### HU-07 Panel familiar (siguiente iteración)

Como familiar, quiero un panel con llamadas, señal de bienestar, recordatorios, recuerdos compartidos y alertas.
