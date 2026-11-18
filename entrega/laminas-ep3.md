# Las 6 láminas de EP3, por caso

Máximo 6, 4 minutos, y sirven al **IE3** (EP3 §5.2): el caso, la decisión de negocio que apoya el modelo,
la arquitectura desplegada y por qué ese diseño ayuda a decidir mejor. **No repitan lo que van a mostrar
en vivo** (el front, el dashboard, CloudWatch). Archivo: `EP3_Presentacion_Equipo<N>.pdf`, subido a AVA
antes del turno.

Reglas de forma que ayudan en 4 minutos: **un mensaje por lámina** (es el título, en una frase), un número
grande por lámina, y menos de 30 palabras de texto. Lo demás lo dicen ustedes.

Los números de ejemplo son los medidos con esta plantilla; **pongan los suyos** (`herramientas/evidencias.sh`,
`herramientas/costos.py`, `METRICAS.md`).

---

## La misma estructura para los tres

| # | Título (el mensaje) | Contenido | ~Tiempo |
|---|---|---|---|
| 1 | El problema, con su número | Empresa, quién sufre el problema y cuánto cuesta | 30 s |
| 2 | La decisión que cambia | Quién decide, qué decide, con qué salida del modelo | 45 s |
| 3 | El modelo, contra la línea base | Qué predice, con qué datos, una métrica contra la línea base, el costo de equivocarse | 45 s |
| 4 | La arquitectura en AWS | El diagrama de despliegue (capítulo 13.1) | 45 s |
| 5 | Por qué este diseño decide mejor | Reglas antes del modelo, reserva, explicación, LLM fuera del camino; el RNF y su medición | 45 s |
| 6 | Costo y lo que falta | Costo mensual vs presupuesto; la deuda declarada | 30 s |

---

## Caso 3 · Kipu Pagos · fraude

1. **«Bloquear clientes buenos nos cuesta más que el fraude.»** Falsos positivos: USD 1,16 M al año; fraude:
   USD 0,5 M. 200.000 transacciones diarias.
2. **«Cada transacción sale aprobada, en revisión o bloqueada, con sus razones.»** El core de pagos decide
   en línea; los seis analistas revisan la cola priorizada por riesgo y monto (RF1, RF2, RF5).
3. **«PR-AUC 0,95 contra 0,11 del azar.»** XGBoost en SageMaker, entrenado solo con las transacciones
   revisadas y sin las columnas que filtran la respuesta. En prueba: 5 falsos positivos y 4 falsos
   negativos en 308. El accuracy no decide: «nunca es fraude» da 99,988%.
4. **El diagrama:** EC2 (Caddy, gateway, dominio, 2 réplicas de IA, base, RabbitMQ, worker) → SageMaker
   serverless; worker → NVIDIA; logs → CloudWatch.
5. **«La decisión nunca espera a nadie que no sea el modelo, y ni a él más de 300 ms.»** Lista negra y
   reglas duras antes del modelo (RF4); umbrales en configuración (RF3); reserva si SageMaker no
   responde (RNF3); el LLM redacta para el analista, por la cola. **RNF1 p99 < 100 ms: no se cumple** con
   serverless (p95 102 ms en el dominio): la propuesta y su costo.
6. **«USD 77 al mes, el 1,3% del presupuesto.»** Deuda: puerto 22 abierto para el despliegue; una sola AZ;
   rate limit en memoria.

## Caso 1 · Nexus Retail · recomendación

1. **«‹la conversión o el ticket que el caso quiere subir›.»** 100.000 usuarios activos al mes.
2. **«Qué 4 a 8 productos ve cada cliente, y qué campaña recibe.»** Tienda (ficha y home) y marketing
   (Mailchimp); la gerenta de e-commerce mira el dashboard.
3. **«En 3 categorías acierta el 80,6% de las veces; los más vendidos, el 47,9%.»** Propensión por usuario
   y categoría, solo con clientes que dieron consentimiento (RN2). ROC-AUC 0,75 contra 0,60 de ordenar
   por popularidad.
4. **El diagrama** (igual estructura; la ruta propia `POST /api/campanas/{usuario}`).
5. **«Nunca un producto sin stock, nunca sin consentimiento, siempre con motivo.»** RF5, RN2, RN3; los
   más vendidos si el modelo no responde en 200 ms (RNF3); el LLM redacta la campaña por la cola sin
   datos personales (RNF7). RNF1 p95 < 200 ms: ‹su medición›.
6. **«USD 42 al mes, el 1,9% del presupuesto.»** Deuda y lo que falta (conversión atribuida, RF10).

## Caso 2 · Andesnet · chatbot

1. **«340.000 contactos al mes, ‹tiempo de espera o tasa de derivación del caso›.»**
2. **«Responder con el artículo correcto o derivar a tiempo.»** El cliente recibe el artículo o el aviso de
   derivación; el ejecutivo ve el historial; Experiencia de clientes mide la derivación (RNF9).
3. **«Reconoce 10 intenciones; con frases nuevas, F1 0,17: por eso la derivación no depende del
   modelo.»** Honestidad sobre el F1 de 1,0 inflado (DESAFÍO M4) y qué hicieron con eso.
4. **El diagrama** (la ruta propia `POST /api/conversacion` y la anonimización antes de la cola).
5. **«Pedir una persona funciona siempre, aunque todo lo demás falle.»** Reglas de derivación antes del
   modelo (RF8, RNF11); umbral de confianza; ningún RUT, correo ni tarjeta sale a NVIDIA (RNF5). RNF1
   p95 < 3 s **con el LLM**: ‹su medición, capítulo 15.5›.
6. **«USD 193 al mes; 153 son del LLM.»** El costo lo manda el LLM, no la infraestructura: la optimización
   que proponen (respuestas fijas para las intenciones frecuentes, un modelo más chico) y su efecto.

---

## Antes de exportar

- [ ] Cada título es una frase con el mensaje, no un tema («Arquitectura» no; «La decisión nunca espera
      al LLM» sí).
- [ ] Todos los números son de **su** sistema y coinciden con el informe.
- [ ] Ninguna lámina muestra lo que la demo va a mostrar.
- [ ] Ensayado con cronómetro: 4:00 o menos.
