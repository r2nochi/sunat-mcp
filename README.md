# sunat-mcp

Servidor **MCP** para validar y consultar RUCs peruanos contra el **Padrón Reducido
oficial de SUNAT**, indexado localmente.

Los RUCs que consultas **no salen de tu máquina**.

## El problema

Todo estudio contable peruano valida RUCs a diario: verificar que una factura tenga un
RUC bien formado, confirmar la razón social de un proveedor, revisar si un contribuyente
está activo y habido antes de aceptar un comprobante.

Las soluciones que existen tienen un problema u otro:

- **Consultar la web de SUNAT a mano** — lento, imposible de automatizar.
- **Scrapear la web de SUNAT** — frágil (se rompe con cada cambio de HTML) y de
  legalidad discutible.
- **APIs de terceros** — requieren llave, tienen límite de consultas y, sobre todo,
  **le envías a un tercero los RUCs de tus clientes**. Para un contador con deber de
  reserva, eso no es un detalle menor.

Este proyecto toma el camino que casi nadie toma: SUNAT **publica el padrón completo
como datos abiertos**. Se descarga una vez, se indexa, y se consulta local.

## Cómo funciona

```text
Padrón Reducido oficial (ZIP, ~372 MiB)
        │  scripts/ingest.py — descarga, verifica SHA-256, recorre en streaming
        ▼
data/padron.sqlite3 — índice local, consulta por clave primaria
        │
        ▼
sunat_mcp/server.py — 4 herramientas MCP  →  Claude Code / Claude Desktop
```

La ingesta **nunca carga el archivo completo en memoria**: lee el `.txt` de 1.56 GB
línea por línea directamente desde el ZIP.

## Herramientas

| Herramienta | Qué devuelve | Requiere índice | Red |
|---|---|:---:|:---:|
| `validar_ruc` | Estructura, prefijo y dígito verificador (módulo 11 SUNAT) | No | No |
| `consultar_ruc` | Razón social, estado, condición de domicilio, ubigeo, dirección | Sí | No |
| `buscar_razon_social` | Contribuyentes cuyo nombre coincide | Sí | No |
| `estado_padron` | Fuente, SHA-256, fecha de SUNAT, fecha de ingesta, nº de registros | Sí | No |

`validar_ruc` funciona **sin haber construido el índice**: es aritmética pura.

## Instalación

Requiere Python 3.10+.

```powershell
git clone https://github.com/r2nochi/sunat-mcp
cd sunat-mcp
python -m venv .venv
.\.venv\Scripts\pip.exe install -e ".[dev,ingest]"
```

## Construir el índice

```powershell
.\.venv\Scripts\python.exe scripts\ingest.py
```

Descarga el ZIP oficial, verifica su checksum y construye el índice.

> **Ten en cuenta:** descarga ~372 MiB y el índice resultante ocupa varios GB en disco.
> Es una operación de una sola vez; para actualizar, vuelve a correrlo.

Para probar sin bajar todo el padrón:

```powershell
.\.venv\Scripts\python.exe scripts\ingest.py --limite 50000
```

El índice quedará marcado como muestra parcial y `estado_padron` lo avisará.

## Rendimiento medido

Sobre el padrón completo del **27/07/2026**: **18,297,300 contribuyentes**, índice de
2.14 GB (Windows 11, SSD, Python 3.14).

| Operación | Tiempo | Plan de SQLite |
|---|---:|---|
| `consultar_ruc` (clave primaria) | **0.2 ms** | `SEARCH ... USING PRIMARY KEY` |
| `buscar_razon_social` por prefijo | **0.2 ms** | `SEARCH ... USING COVERING INDEX` |
| `buscar_razon_social` por subcadena | ~40 s | `SCAN` (inevitable, es un `LIKE '%x%'`) |
| Ingesta completa (descarga + índice) | ~22 min | — |

### Por qué el índice usa `COLLATE NOCASE`

La primera versión indexaba `razon_social` con la colación por defecto (BINARY) y
buscaba con `LIKE 'TEXTO%'`. La búsqueda por prefijo tardaba **39,848 ms**.

El motivo: el `LIKE` de SQLite es *case-insensitive* por defecto, y por eso **no puede
usar un índice BINARY** — degeneraba en un `SCAN` de los 18.3 millones de filas. Había
además un problema de correctitud: el padrón trae algunas razones sociales en minúscula,
que una comparación binaria habría perdido en silencio.

La solución fue indexar con `COLLATE NOCASE` y resolver el prefijo como un **rango**
(`>= 'TEXTO' AND < 'TEXTO' + centinela`) en lugar de un `LIKE`:

```
antes:  SCAN contribuyente USING COVERING INDEX idx_razon_social      39,848 ms
ahora:  SEARCH contribuyente USING COVERING INDEX idx_razon_nocase         0.2 ms
```

Hay un test que afirma el plan de ejecución, para que la regresión no pueda volver en
silencio.

## Conectarlo a Claude Code

```powershell
claude mcp add sunat --scope user -- <ruta>\sunat-mcp\.venv\Scripts\python.exe -m sunat_mcp.server
```

O en `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "sunat": {
      "command": "C:\\ruta\\a\\sunat-mcp\\.venv\\Scripts\\python.exe",
      "args": ["-m", "sunat_mcp.server"]
    }
  }
}
```

El índice se busca en `data/padron.sqlite3`. Para moverlo, define `SUNAT_MCP_DB`.

## Fuente de los datos

**Padrón Reducido del RUC**, publicado por SUNAT como datos abiertos:
<https://www.sunat.gob.pe/descargaPRR/mrc137_padron_reducido.html>

Archivo: `padron_reducido_ruc.zip` → `padron_reducido_ruc.txt`
Formato: 16 columnas separadas por `|`, codificación **latin-1**, `-` como dato ausente.

```text
RUC | NOMBRE O RAZÓN SOCIAL | ESTADO DEL CONTRIBUYENTE | CONDICIÓN DE DOMICILIO |
UBIGEO | TIPO DE VÍA | NOMBRE DE VÍA | CÓDIGO DE ZONA | TIPO DE ZONA | NÚMERO |
INTERIOR | LOTE | DEPARTAMENTO | MANZANA | KILÓMETRO |
```

`estado_padron` expone el SHA-256 del ZIP ingerido y la fecha que informó SUNAT, para
que puedas saber exactamente qué versión de los datos estás consultando.

Si SUNAT cambia el esquema, **la ingesta se detiene con error** en vez de escribir datos
en columnas equivocadas.

## Límites

Léelos antes de confiar en el resultado:

- **El padrón es una foto, no un servicio en vivo.** SUNAT lo publica periódicamente. Un
  RUC creado o dado de baja después de tu última ingesta **no se refleja**. Consulta
  `estado_padron` para ver la fecha.
- **`validar_ruc` solo comprueba aritmética.** Un RUC con dígito verificador correcto
  puede no existir. Son preguntas distintas.
- **El Padrón Reducido no trae todo.** No incluye representantes legales, actividad
  económica CIIU detallada, teléfonos ni la condición de agente de retención.
- **La búsqueda por nombre es textual, no semántica.** No corrige errores de tipeo ni
  entiende sinónimos. La búsqueda por **prefijo** es instantánea; la búsqueda por
  **subcadena** (`%TEXTO`) recorre los 18.3 millones de registros y puede tardar decenas
  de segundos. Es un costo que solo se paga si se pide explícitamente.
- **La dirección se reconstruye** uniendo las 10 columnas de domicilio del padrón. No se
  valida contra ningún servicio de direcciones.
- **Esto no es asesoría tributaria.** Para decisiones con efecto legal o contable,
  verifica en el portal oficial de SUNAT.

## Tests

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

Las pruebas **generan su propio ZIP de padrón sintético** con el mismo formato del
oficial (16 columnas, `|`, latin-1, `-`). No dependen del archivo real de 372 MiB ni
contienen datos de ningún contribuyente real, salvo RUCs que aparecen en la cabecera
pública del padrón.

Incluyen una prueba de que la ingesta **aborta si SUNAT cambia las columnas**.

## Licencia

MIT. Los datos del Padrón Reducido son de SUNAT y se rigen por sus propios términos.

---

Hecho por [David Nochi](https://github.com/r2nochi) — Ingeniero de IA Aplicada, Lima, Perú.
