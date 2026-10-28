"""Revision en lote de una lista de proveedores contra el indice local.

Clasifica cada RUC en uno de cuatro resultados. La regla es una lista
blanca: solo ACTIVO + HABIDO cuenta como "ok". Cualquier otro estado o
condicion (incluidos valores que SUNAT agregue en el futuro) queda como
"observado" con el valor tal cual viene del padron, nunca se asume bueno.
"""

from __future__ import annotations

import sqlite3
from dataclasses import asdict, dataclass, field

from sunat_mcp import padron as p
from sunat_mcp.ruc import normalizar, validar

# Tope por llamada: una lista de compras mensual de un estudio cabe de sobra,
# y evita que un pegado accidental de miles de lineas bloquee al agente.
MAX_RUCS = 500

ESTADO_OK = "ACTIVO"
CONDICION_OK = "HABIDO"

OK = "ok"
OBSERVADO = "observado"
INVALIDO = "invalido"
NO_ENCONTRADO = "no_encontrado"


@dataclass(frozen=True)
class Revision:
    ruc: str
    resultado: str
    motivos: list[str] = field(default_factory=list)
    razon_social: str | None = None
    estado: str | None = None
    condicion_domicilio: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


def _es(valor: str | None, esperado: str) -> bool:
    return (valor or "").strip().upper() == esperado


def revisar_uno(con: sqlite3.Connection, ruc: str) -> Revision:
    """Revisa un RUC ya normalizado."""
    estructura = validar(ruc)
    if not estructura.valido:
        return Revision(ruc=ruc, resultado=INVALIDO, motivos=[estructura.motivo or "RUC invalido"])

    c = p.consultar(con, estructura.ruc)
    if c is None:
        return Revision(
            ruc=estructura.ruc,
            resultado=NO_ENCONTRADO,
            motivos=["Bien formado pero no figura en el padron indexado"],
        )

    motivos = []
    if not _es(c.estado, ESTADO_OK):
        motivos.append(f"Estado: {c.estado or 'sin dato'}")
    if not _es(c.condicion_domicilio, CONDICION_OK):
        motivos.append(f"Condicion de domicilio: {c.condicion_domicilio or 'sin dato'}")

    return Revision(
        ruc=c.ruc,
        resultado=OBSERVADO if motivos else OK,
        motivos=motivos,
        razon_social=c.razon_social,
        estado=c.estado,
        condicion_domicilio=c.condicion_domicilio,
    )


def preparar(rucs: list[str]) -> tuple[list[str], int]:
    """Normaliza, descarta lineas vacias y quita duplicados conservando el orden.

    Una entrada sin digitos ("N/A", "SIN RUC") no se descarta: se conserva tal
    cual para que la revision la reporte como invalida en vez de perderla.
    Devuelve la lista unica y cuantos duplicados se omitieron.
    """
    vistos: dict[str, None] = {}
    duplicados = 0
    for entrada in rucs:
        ruc = normalizar(entrada) or entrada.strip()
        if not ruc:
            continue
        if ruc in vistos:
            duplicados += 1
        else:
            vistos[ruc] = None
    return list(vistos), duplicados


def revisar(con: sqlite3.Connection, rucs: list[str]) -> list[Revision]:
    """Revisa una lista ya preparada (ver `preparar`)."""
    return [revisar_uno(con, ruc) for ruc in rucs]
