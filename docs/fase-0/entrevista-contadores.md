# Fase 0: entrevistas a contadores

**Objetivo:** decidir con evidencia si Kipu vale la pena, antes de construir más.

**Regla de decisión:** al final de la fase, **al menos 3 contadores usan la skill de revisión de proveedores cada semana sin que se lo recuerdes**.
- Si se cumple, se pasa a la fase 1.
- Si no se cumple, se ajusta o se descarta. Es un resultado válido, no un fracaso.

Meta: 10 conversaciones de 20–30 minutos.

---

## Mensaje para reclutar (WhatsApp / LinkedIn)

> Hola [nombre], estoy armando una herramienta gratuita para estudios contables que revisa la lista de proveedores contra el padrón de SUNAT (activo / habido / de baja) consultando el padrón en tu propia computadora, sin servicios de terceros. ¿Me regalas 20 minutos para contarme cómo lo haces hoy? No te voy a vender nada.

## Reglas para entrevistar
- **Pregunta por lo que hicieron, no por lo que harían.** "¿Lo usarías?" casi siempre recibe un sí que no significa nada.
- Pide casos concretos: "la última vez que...".
- Escucha más de lo que hablas. No muestres la herramienta hasta la parte 4.
- Anota **frases textuales**. Valen más que tu resumen.

---

## Guion

### 1. Contexto (3 min)
- ¿Trabajas sola/o o en un estudio? ¿Cuántos clientes llevan?
- ¿Qué tipo de clientes: régimen general, MYPE, RER?
- ¿Qué software contable usan hoy?

### 2. Cómo lo hacen hoy (10 min): **la parte más importante**
- Cuéntame la **última vez** que revisaste si un proveedor estaba activo o habido. ¿Qué pasó? ¿Cómo lo hiciste?
- ¿Cada cuánto lo haces? ¿Lo revisas para todos los proveedores o solo para algunos?
- ¿Cuánto tiempo te toma al mes, aproximadamente?
- ¿Te ha pasado que un proveedor resultó no habido o de baja **después** de registrar su factura? ¿Qué tuviste que hacer? ¿Cuánto costó, en tiempo o en dinero?
- ¿Usas alguna API, Excel con macros o servicio pagado para esto? ¿Cuánto pagas?

### 3. Herramientas de IA (5 min)
- ¿Usas ChatGPT, Claude, Copilot u otra IA en el trabajo? ¿Para qué, exactamente? ¿Desde cuándo?
- ¿Alguna vez instalaste algo en tu computadora siguiendo instrucciones técnicas (Python, una extensión)?
- ¿Te preocupa enviar los datos de tus clientes a servicios de terceros, incluida la IA? ¿Por qué? (Sé honesto: el padrón se consulta en local, pero lo que pegues en Claude sí lo procesa Claude.)

### 4. Prueba de la skill (10 min): solo si usan Claude Code o Claude Desktop
- Pídele que traiga su lista real de proveedores del mes (puede anonimizar los nombres).
- **Observa sin ayudar**: ¿dónde se traba?
- La instalación toma unos 22 minutos y ocupa unos 2 GB de disco. ¿Eso es un problema? ¿Preferirías que alguien lo instale, o una versión que no requiera instalar nada?
- ¿Qué le falta al reporte para que se lo puedas enviar a tu cliente o a tu jefe?

### 5. Cierre (2 min)
- Si esto te ahorrara [el tiempo que dijo] al mes, ¿cuánto pagarías? (Anota la cifra, no el sí.)
- ¿A quién más le debería preguntar?
- ¿Puedo escribirte en 2 semanas para ver si lo sigues usando?

---

## Registro de cada entrevista

| Campo | Respuesta |
|---|---|
| Fecha / nombre / tipo de estudio | |
| N.º de clientes | |
| Cómo revisa proveedores hoy | |
| Tiempo al mes | |
| ¿Tuvo un caso real de proveedor no habido? Consecuencia | |
| Usa IA (cuál y para qué) | |
| ¿Pudo instalarlo? ¿Dónde se trabó? | |
| Disposición a pagar (cifra) | |
| Frases textuales | |
| **¿La usa a las 2 semanas?** (sí/no) | |

## Lo que hay que responder al terminar las 10
1. ¿El problema es frecuente y duele, o es una molestia menor?
2. ¿Cuántos usan IA de verdad? Si son casi ninguno, la fase 3 (Kipu Estudio, sin Claude) pasa al frente.
3. ¿La instalación espanta a la gente? Si es así, la prioridad es simplificarla.
4. ¿Qué piden que **no** está en el padrón reducido? Agentes de retención, historial de cambios, validez de comprobantes. Eso define la fase 1.
