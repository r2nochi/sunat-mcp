"""Acceso de solo lectura al indice local del Padron Reducido de SUNAT.

El indice es un SQLite construido por `scripts/ingest.py`. Este modulo nunca
sale a la red: si el indice no existe, lo dice y no intenta descargar nada.
"""

from __future__ import annotations

import os
import sqlite3
from dataclasses import asdict, dataclass
from pathlib import Path

ESQUEMA_VERSION = "1"

# Columnas del archivo oficial `padron_reducido_ruc.txt` (separador `|`).
COLUMNAS = (
    "RUC",
    "NOMBRE O RAZON SOCIAL",
    "ESTADO DEL CONTRIBUYENTE",
    "CONDICION DE DOMICILIO",
    "UBIGEO",
    "TIPO DE VIA",
    "NOMBRE DE VIA",
    "CODIGO DE ZONA",
    "TIPO DE ZONA",
    "NUMERO",
    "INTERIOR",
    "LOTE",
    "DEPARTAMENTO",
    "MANZANA",
    "KILOMETRO",
)

# SUNAT usa "-" como marcador de dato ausente.
_AUSENTE = "-"


class PadronNoDisponible(RuntimeError):
    """El indice local no existe o no se pudo abrir."""


@dataclass(frozen=True)
class Contribuyente:
    ruc: str
    razon_social: str
    estado: str | None
    condicion_domicilio: str | None
    ubigeo: str | None
    direccion: str | None

    def to_dict(self) -> dict:
        return asdict(self)


def limpiar(valor: str | None) -> str | None:
    """Normaliza un campo del padron: recorta y convierte '-' y '' en None."""
    if valor is None:
        return None
    v = valor.strip()
    return None if v in ("", _AUSENTE) else v


def componer_direccion(campos: dict[str, str | None]) -> str | None:
    """Reconstruye una direccion legible desde las 10 columnas de domicilio.

    SUNAT publica el domicilio fiscal descompuesto (tipo de via, nombre, numero,
    interior, lote, manzana, kilometro, zona). Aqui se vuelven a unir en un solo
    texto, omitiendo las partes ausentes. No se corrige ortografia ni se valida
    contra ninguna fuente de direcciones.
    """
    partes: list[str] = []

    via = " ".join(
        p for p in (campos.get("TIPO DE VIA"), campos.get("NOMBRE DE VIA")) if p
    )
    if via:
        partes.append(via)

    for etiqueta, clave in (
        ("NRO.", "NUMERO"),
        ("INT.", "INTERIOR"),
        ("LOTE", "LOTE"),
        ("MZ.", "MANZANA"),
        ("KM.", "KILOMETRO"),
        ("DPTO.", "DEPARTAMENTO"),
    ):
        valor = campos.get(clave)
        if valor:
            partes.append(f"{etiqueta} {valor}")

    zona = " ".join(
        p for p in (campos.get("TIPO DE ZONA"), campos.get("CODIGO DE ZONA")) if p
    )
    if zona:
        partes.append(zona)

    return " ".join(partes) if partes else None


def ruta_indice() -> Path:
    """Ubicacion del indice. Configurable con la variable SUNAT_MCP_DB."""
    env = os.environ.get("SUNAT_MCP_DB")
    if env:
        return Path(env)
    return Path(__file__).resolve().parent.parent / "data" / "padron.sqlite3"


def crear_esquema(con: sqlite3.Connection) -> None:
    """Crea el esquema del indice. Idempotente."""
    con.executescript(
        """
        CREATE TABLE IF NOT EXISTS contribuyente (
            ruc                 TEXT PRIMARY KEY,
            razon_social        TEXT NOT NULL,
            estado              TEXT,
            condicion_domicilio TEXT,
            ubigeo              TEXT,
            direccion           TEXT
        ) WITHOUT ROWID;

        -- COLLATE NOCASE es deliberado. Sin el, una busqueda por prefijo con
        -- LIKE degenera en SCAN de los ~18 millones de filas (~40 s medidos),
        -- porque el LIKE de SQLite es case-insensitive y no puede usar un
        -- indice BINARY. Ademas el padron trae razones sociales en minuscula,
        -- asi que comparar en binario las perderia en silencio.
        CREATE INDEX IF NOT EXISTS idx_razon_nocase
            ON contribuyente (razon_social COLLATE NOCASE);

        CREATE TABLE IF NOT EXISTS provenance (
            clave TEXT PRIMARY KEY,
            valor TEXT NOT NULL
        );
        """
    )


def conectar(ruta: Path | None = None) -> sqlite3.Connection:
    """Abre el indice en solo lectura.

    Lanza `PadronNoDisponible` si el archivo no existe, con el comando exacto
    para generarlo.
    """
    destino = ruta or ruta_indice()
    if not destino.exists():
        raise PadronNoDisponible(
            f"No existe el indice local en {destino}. "
            "Generalo con: python scripts/ingest.py"
        )
    con = sqlite3.connect(f"file:{destino}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    return con


def consultar(con: sqlite3.Connection, ruc: str) -> Contribuyente | None:
    """Busca un RUC exacto. O(1) sobre la clave primaria."""
    fila = con.execute(
        "SELECT ruc, razon_social, estado, condicion_domicilio, ubigeo, direccion "
        "FROM contribuyente WHERE ruc = ?",
        (ruc,),
    ).fetchone()
    return _a_contribuyente(fila) if fila else None


def buscar_por_nombre(
    con: sqlite3.Connection, texto: str, limite: int = 10
) -> list[Contribuyente]:
    """Busca por razon social. La comparacion ignora mayusculas y minusculas.

    - `"TEXTO"`  -> busqueda por PREFIJO. Se resuelve como un rango sobre el
      indice NOCASE (milisegundos).
    - `"%TEXTO"` -> busqueda por SUBCADENA. Obliga a recorrer los ~18 millones
      de registros y puede tardar decenas de segundos. Es deliberado: se paga
      solo si se pide explicitamente.
    """
    consulta = texto.strip()
    if not consulta:
        return []

    tope = max(1, min(limite, 100))
    columnas = (
        "SELECT ruc, razon_social, estado, condicion_domicilio, ubigeo, direccion "
        "FROM contribuyente WHERE "
    )
    orden = " ORDER BY razon_social COLLATE NOCASE LIMIT ?"

    if consulta.startswith("%"):
        patron = consulta if consulta.endswith("%") else f"{consulta}%"
        sql = columnas + "razon_social LIKE ? COLLATE NOCASE" + orden
        params: tuple = (patron, tope)
    else:
        # Rango [prefijo, prefijo + centinela). El centinela es el codepoint mas
        # alto de Unicode, asi que cubre cualquier sufijo posible.
        sql = (
            columnas
            + "razon_social >= ? COLLATE NOCASE AND razon_social < ? COLLATE NOCASE"
            + orden
        )
        params = (consulta, consulta + "\U0010ffff", tope)

    return [_a_contribuyente(f) for f in con.execute(sql, params).fetchall()]


def provenance(con: sqlite3.Connection) -> dict[str, str]:
    """Devuelve los metadatos de origen del indice (fuente, checksum, fechas)."""
    return {
        f["clave"]: f["valor"] for f in con.execute("SELECT clave, valor FROM provenance")
    }


def _a_contribuyente(fila: sqlite3.Row) -> Contribuyente:
    return Contribuyente(
        ruc=fila["ruc"],
        razon_social=fila["razon_social"],
        estado=fila["estado"],
        condicion_domicilio=fila["condicion_domicilio"],
        ubigeo=fila["ubigeo"],
        direccion=fila["direccion"],
    )
