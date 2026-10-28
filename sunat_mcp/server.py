"""Servidor MCP para validar y consultar RUCs peruanos.

Ninguna herramienta sale a internet. `validar_ruc` es aritmetica pura;
el resto consulta un indice SQLite local construido desde el Padron
Reducido oficial de SUNAT. Los RUCs que consultes no salen de tu maquina.
"""

from __future__ import annotations

import sqlite3

from mcp.server.fastmcp import FastMCP

from sunat_mcp import padron as p
from sunat_mcp import revision as rv
from sunat_mcp.ruc import validar

mcp = FastMCP(
    "sunat-ruc",
    instructions=(
        "Valida y consulta RUCs peruanos contra el Padron Reducido oficial de "
        "SUNAT, indexado localmente. Usa validar_ruc para comprobar si un RUC "
        "esta bien formado (no requiere indice) y consultar_ruc para obtener "
        "razon social, estado y condicion de domicilio. Para una lista de "
        "proveedores usa revisar_proveedores en una sola llamada."
    ),
)

_con: sqlite3.Connection | None = None


def _indice() -> sqlite3.Connection:
    """Conexion perezosa y reutilizada al indice local."""
    global _con
    if _con is None:
        _con = p.conectar()
    return _con


@mcp.tool()
def validar_ruc(ruc: str) -> dict:
    """Valida la estructura de un RUC peruano: 11 digitos, prefijo vigente y
    digito verificador segun el algoritmo modulo 11 de SUNAT.

    Es una comprobacion aritmetica y offline: NO consulta ninguna base de datos.
    Un RUC valido aqui puede aun asi no existir en SUNAT o estar de baja; para
    eso usa `consultar_ruc`.
    """
    r = validar(ruc)
    return {
        "ruc": r.ruc,
        "valido": r.valido,
        "motivo": r.motivo,
        "tipo_contribuyente": r.tipo_contribuyente,
        "nota": (
            "Solo valida la estructura. No confirma que el RUC exista ni que "
            "este activo en SUNAT."
        ),
    }


@mcp.tool()
def consultar_ruc(ruc: str) -> dict:
    """Consulta un RUC en el Padron Reducido local: razon social, estado del
    contribuyente, condicion de domicilio, ubigeo y direccion fiscal.

    Requiere haber construido el indice con `python scripts/ingest.py`.
    La consulta es local: el RUC no se envia a ningun servicio externo.
    """
    estructura = validar(ruc)
    if not estructura.valido:
        return {
            "encontrado": False,
            "ruc": estructura.ruc,
            "error": f"RUC invalido: {estructura.motivo}",
        }

    try:
        con = _indice()
    except p.PadronNoDisponible as e:
        return {"encontrado": False, "ruc": estructura.ruc, "error": str(e)}

    registro = p.consultar(con, estructura.ruc)
    if registro is None:
        return {
            "encontrado": False,
            "ruc": estructura.ruc,
            "nota": (
                "El RUC esta bien formado pero no figura en el padron indexado. "
                "Puede ser muy reciente: revisa la fecha con `estado_padron`."
            ),
        }

    datos = registro.to_dict()
    datos["encontrado"] = True
    datos["tipo_contribuyente"] = estructura.tipo_contribuyente
    return datos


@mcp.tool()
def buscar_razon_social(texto: str, limite: int = 10) -> dict:
    """Busca contribuyentes cuya razon social coincida con `texto`.

    Por defecto busca por PREFIJO, resuelto como un rango sobre el indice
    (milisegundos). Para buscar por subcadena antepone '%' al texto (p. ej.
    '%ANDES'), pero eso recorre los ~18 millones de registros y puede tardar
    decenas de segundos. La comparacion ignora mayusculas y minusculas.
    """
    try:
        con = _indice()
    except p.PadronNoDisponible as e:
        return {"resultados": [], "error": str(e)}

    encontrados = p.buscar_por_nombre(con, texto, limite)
    return {
        "consulta": texto,
        "total_devuelto": len(encontrados),
        "resultados": [c.to_dict() for c in encontrados],
        "nota": (
            "Coincidencia textual sobre la razon social tal como la publica "
            "SUNAT. No hay busqueda semantica ni correccion de errores de tipeo."
            if encontrados
            else "Sin coincidencias. Prueba con menos palabras o con '%' al inicio."
        ),
    }


@mcp.tool()
def revisar_proveedores(rucs: list[str | int]) -> dict:
    """Revisa en una sola llamada una lista de RUCs de proveedores (hasta 500).

    Cada RUC queda como `ok` (ACTIVO y HABIDO), `observado` (cualquier otro
    estado o condicion de domicilio, con el valor exacto del padron),
    `invalido` (mal formado) o `no_encontrado`. Quita duplicados y conserva el
    orden. Incluye la fecha del padron consultado: el resultado vale para esa
    foto, no para hoy.
    """
    # Los RUCs leidos de un Excel suelen llegar como numeros.
    unicos, duplicados = rv.preparar([str(r) for r in rucs])
    if len(unicos) > rv.MAX_RUCS:
        return {
            "error": (
                f"Se recibieron {len(unicos)} RUCs unicos; el maximo por llamada "
                f"es {rv.MAX_RUCS}. Divide la lista en partes."
            )
        }

    try:
        con = _indice()
    except p.PadronNoDisponible as e:
        return {"error": str(e)}

    revisiones = rv.revisar(con, unicos)
    resumen = {k: 0 for k in (rv.OK, rv.OBSERVADO, rv.INVALIDO, rv.NO_ENCONTRADO)}
    for r in revisiones:
        resumen[r.resultado] += 1

    prov = p.provenance(con)
    return {
        "padron": {
            "last_modified_sunat": prov.get("last_modified_sunat"),
            "fecha_ingesta_utc": prov.get("fecha_ingesta_utc"),
            "sha256_zip": prov.get("sha256_zip"),
            "muestra_parcial": prov.get("muestra_parcial") == "si",
        },
        "total_revisados": len(revisiones),
        "duplicados_omitidos": duplicados,
        "resumen": resumen,
        "resultados": [r.to_dict() for r in revisiones],
        "nota": (
            "Foto del Padron Reducido en la fecha indicada, no del dia de hoy. "
            "No es asesoria tributaria: antes de basar una decision en este "
            "resultado, verifica al proveedor en el portal oficial de SUNAT."
        ),
    }


@mcp.tool()
def estado_padron() -> dict:
    """Devuelve la procedencia del indice local: URL de origen, checksum
    SHA-256 del ZIP, fecha de publicacion de SUNAT, fecha de ingesta y numero
    de registros.

    Sirve para saber que tan actualizado esta el dato antes de confiar en el.
    """
    try:
        con = _indice()
    except p.PadronNoDisponible as e:
        return {"disponible": False, "error": str(e)}

    datos = p.provenance(con)
    datos["disponible"] = True
    if datos.get("muestra_parcial") == "si":
        datos["aviso"] = (
            "Este indice se construyo con --limite: es una muestra parcial, "
            "no el padron completo."
        )
    return datos


def main() -> None:
    """Punto de entrada del servidor (transporte stdio)."""
    mcp.run()


if __name__ == "__main__":
    main()
