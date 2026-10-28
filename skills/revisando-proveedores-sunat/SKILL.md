---
name: revisando-proveedores-sunat
description: Usar cuando un contador, estudio contable o pyme peruana pide revisar, validar o auditar una lista de proveedores o RUCs (registro de compras, Excel, CSV, facturas, cierre de mes) para saber si estan activos, habidos, de baja o no habidos ante SUNAT. Requiere el servidor MCP sunat-mcp (paquete mcp-sunat).
---

# Revision de proveedores contra el padron de SUNAT

## Que hace
Revisa una lista de proveedores contra el **Padron Reducido oficial de SUNAT**, indexado en la maquina del usuario. El servidor consulta el padron localmente, sin servicios externos de RUC. Pero lo que el usuario pega en esta conversacion si lo procesa el asistente de IA. Si pregunta por confidencialidad, explica ambas cosas; nunca digas que sus datos "no salen de su computadora".

## Antes de empezar
1. Llama `estado_padron`.
   - Si responde `disponible: false`, el indice no existe. Explica la instalacion (seccion final) y detente.
   - Si `muestra_parcial` vale `"si"`, advierte que el resultado no cubre todo el padron.
2. Extrae **solo los RUCs** del material del usuario: la columna de RUC del Excel o CSV, o los RUCs dentro del texto pegado. No pases numeros de factura ni montos. Pasalos tal cual, incluso los duplicados o los mal formados: la herramienta los cuenta y clasifica.

## Revision
- Llama **`revisar_proveedores`** con toda la lista en una sola llamada. Si hay mas de 500 RUCs unicos, dividela en partes.
- No uses `consultar_ruc` uno por uno para una lista.

## Formato de la respuesta (en este orden)
1. **Linea de fecha**: "Padron de SUNAT del `<last_modified_sunat>` (ingerido el `<fecha_ingesta_utc>`)". Siempre va, porque el resultado vale para esa foto y no para hoy. Si `last_modified_sunat` es `desconocido` o falta, escribe "fecha de publicacion desconocida, ingerido el `<fecha_ingesta_utc>`".
2. **Resumen**: cuantos estan ok, observados, invalidos y no encontrados, mas los duplicados omitidos.
3. **Tabla de los que requieren atencion**: primero los observados, luego los invalidos y los no encontrados. Columnas: RUC, razon social, motivo. Los que estan ok no se listan, salvo que el usuario lo pida.
4. **Siguiente paso por tipo**:
   - *Observado*: verificar en la Consulta RUC del portal de SUNAT antes de aceptar comprobantes de ese proveedor. (Un *ok* tambien es solo la foto de esa fecha.)
   - *Invalido*: probable error de digitacion; pedir el RUC correcto al proveedor.
   - *No encontrado*: puede ser un RUC muy reciente; consultarlo en el portal de SUNAT o actualizar el padron (ver Instalacion).
5. **Cierre fijo**: "Esto no es asesoria tributaria."

Si el usuario lo pide, entrega la tabla completa como CSV con las columnas `ruc, razon_social, resultado, estado, condicion_domicilio, motivos`.

## Lo que esta skill NO puede afirmar
El Padron Reducido no trae esta informacion. Si el pedido la incluye, haz la revision igual y agrega un bloque aparte que diga que esa parte no esta disponible en esta version; no la infieras:
- Si el proveedor es agente de retencion o de percepcion, o buen contribuyente.
- Desde cuando cambio su estado, o su historial.
- Si una factura concreta es valida, o el efecto sobre el credito fiscal.

## Errores comunes
| Error | Correccion |
|---|---|
| Omitir la fecha del padron | Siempre va primero |
| Culpar a la digitacion cuando muchos RUCs salen invalidos con forma `2.01235E+10` | Es Excel en notacion cientifica: pide formatear la columna como texto y exportar de nuevo |
| Tratar un estado poco comun (p. ej. SUSPENSION TEMPORAL) como "practicamente activo" | Solo ACTIVO + HABIDO es ok; muestra el valor exacto |
| Afirmar consecuencias legales ("pierdes el credito fiscal") | Indica verificar en SUNAT; no des asesoria |
| Inventar la razon social de un invalido o no encontrado | Dejala vacia, o usa el nombre que dio el usuario marcado "(segun tu lista)" |

## Instalacion (si `estado_padron` no esta disponible)
```powershell
git clone https://github.com/r2nochi/sunat-mcp ; cd sunat-mcp
python -m venv .venv
.\.venv\Scripts\pip.exe install -e ".[ingest]"
.\.venv\Scripts\python.exe scripts\ingest.py   # una vez: ~372 MiB de descarga, ~22 min, ~2 GB en disco
claude mcp add sunat --scope user -- <ruta>\sunat-mcp\.venv\Scripts\python.exe -m sunat_mcp.server
```
Para actualizar los datos: `.\.venv\Scripts\python.exe scripts\ingest.py --forzar-descarga` (sin esa opcion reutiliza el ZIP viejo). Cierra antes Claude, que mantiene abierto el indice. SUNAT publica el padron a diario.
