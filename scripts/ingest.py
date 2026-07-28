"""Construye el indice local desde el Padron Reducido oficial de SUNAT.

Descarga (o reutiliza) `padron_reducido_ruc.zip`, verifica su integridad,
lo recorre en streaming y genera un SQLite consultable en milisegundos.

El ZIP pesa ~372 MiB y el .txt interno ~1.56 GB. La ingesta nunca carga el
archivo completo en memoria: lo lee linea por linea desde el ZIP.

Uso:
    python scripts/ingest.py                 # descarga si hace falta y construye
    python scripts/ingest.py --zip ruta.zip  # usa un ZIP ya descargado
    python scripts/ingest.py --limite 50000  # muestra pequena, para probar
"""

from __future__ import annotations

import argparse
import hashlib
import sqlite3
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sunat_mcp.padron import (  # noqa: E402
    COLUMNAS,
    ESQUEMA_VERSION,
    componer_direccion,
    crear_esquema,
    limpiar,
)

URL_PADRON = "https://www2.sunat.gob.pe/padron_reducido_ruc.zip"
NOMBRE_INTERNO = "padron_reducido_ruc.txt"
ENCODING = "latin-1"  # SUNAT publica el .txt en latin-1, no en UTF-8.
RAIZ = Path(__file__).resolve().parent.parent


def descargar(destino: Path) -> str | None:
    """Descarga el ZIP oficial. Devuelve el Last-Modified que informa SUNAT."""
    try:
        import httpx
    except ImportError:  # pragma: no cover - depende del entorno
        raise SystemExit(
            "Falta httpx para descargar. Instala con: pip install -e '.[ingest]'\n"
            "O descarga el ZIP a mano y pasalo con --zip."
        )

    destino.parent.mkdir(parents=True, exist_ok=True)
    print(f"Descargando {URL_PADRON}")
    last_modified = None

    with httpx.stream("GET", URL_PADRON, follow_redirects=True, timeout=120.0) as r:
        r.raise_for_status()
        last_modified = r.headers.get("last-modified")
        total = int(r.headers.get("content-length", 0))
        leidos = 0
        with destino.open("wb") as f:
            for bloque in r.iter_bytes(chunk_size=1 << 20):
                f.write(bloque)
                leidos += len(bloque)
                if total:
                    print(f"\r  {leidos / total:.1%}", end="", flush=True)
    print()
    return last_modified


def consultar_last_modified() -> str | None:
    """Pregunta a SUNAT la fecha de publicacion sin descargar el archivo.

    Se usa cuando se reutiliza un ZIP ya bajado, para que la procedencia no
    quede incompleta. Si no hay red, devuelve None y la ingesta continua.
    """
    try:
        import httpx

        r = httpx.head(URL_PADRON, follow_redirects=True, timeout=15.0)
        r.raise_for_status()
        return r.headers.get("last-modified")
    except Exception:  # sin red, DNS caido, timeout: no es motivo para abortar
        return None


def sha256(ruta: Path) -> str:
    """Checksum del archivo, leido por bloques."""
    h = hashlib.sha256()
    with ruta.open("rb") as f:
        for bloque in iter(lambda: f.read(1 << 20), b""):
            h.update(bloque)
    return h.hexdigest()


def verificar_cabecera(cabecera: str) -> None:
    """Aborta si SUNAT cambio el esquema del archivo.

    Preferimos fallar ruidosamente a ingerir datos en columnas equivocadas.
    """
    campos = [c.strip().upper() for c in cabecera.rstrip("\n").split("|") if c.strip()]
    esperados = [c.upper() for c in COLUMNAS]

    def sin_tildes(s: str) -> str:
        for a, b in zip("ÁÉÍÓÚÑ", "AEIOUN"):
            s = s.replace(a, b)
        return s

    campos = [sin_tildes(c) for c in campos]
    if campos != esperados:
        raise SystemExit(
            "El esquema del padron cambio y la ingesta se detuvo para no "
            "escribir datos en columnas equivocadas.\n"
            f"  esperado: {esperados}\n"
            f"  recibido: {campos}\n"
            "Revisa sunat_mcp/padron.py:COLUMNAS antes de continuar."
        )


def construir(zip_path: Path, db_path: Path, limite: int | None, last_modified: str | None) -> int:
    """Recorre el ZIP en streaming y escribe el indice. Devuelve nº de filas."""
    if db_path.exists():
        db_path.unlink()
    db_path.parent.mkdir(parents=True, exist_ok=True)

    print(f"Calculando SHA-256 de {zip_path.name}...")
    checksum = sha256(zip_path)
    print(f"  {checksum}")

    con = sqlite3.connect(db_path)
    # Ajustes solo de carga: el indice se consulta despues en modo lectura.
    con.execute("PRAGMA journal_mode = OFF")
    con.execute("PRAGMA synchronous = OFF")
    crear_esquema(con)

    indices = {nombre: i for i, nombre in enumerate(COLUMNAS)}
    n = 0
    lote: list[tuple] = []

    with zipfile.ZipFile(zip_path) as z, z.open(NOMBRE_INTERNO) as bruto:
        cabecera = bruto.readline().decode(ENCODING)
        verificar_cabecera(cabecera)

        for linea in bruto:
            campos = linea.decode(ENCODING).rstrip("\r\n").split("|")
            if len(campos) < len(COLUMNAS):
                continue

            ruc = campos[indices["RUC"]].strip()
            if len(ruc) != 11 or not ruc.isdigit():
                continue

            por_nombre = {c: limpiar(campos[indices[c]]) for c in COLUMNAS}
            lote.append(
                (
                    ruc,
                    por_nombre["NOMBRE O RAZON SOCIAL"] or "",
                    por_nombre["ESTADO DEL CONTRIBUYENTE"],
                    por_nombre["CONDICION DE DOMICILIO"],
                    por_nombre["UBIGEO"],
                    componer_direccion(por_nombre),
                )
            )
            n += 1

            if len(lote) >= 50_000:
                _volcar(con, lote)
                lote.clear()
                print(f"\r  {n:,} registros", end="", flush=True)

            if limite and n >= limite:
                break

    if lote:
        _volcar(con, lote)
    print(f"\r  {n:,} registros")

    con.executemany(
        "INSERT OR REPLACE INTO provenance (clave, valor) VALUES (?, ?)",
        [
            ("fuente_url", URL_PADRON),
            ("archivo_zip", zip_path.name),
            ("sha256_zip", checksum),
            ("last_modified_sunat", last_modified or "desconocido"),
            ("fecha_ingesta_utc", datetime.now(timezone.utc).isoformat(timespec="seconds")),
            ("registros", str(n)),
            ("esquema_version", ESQUEMA_VERSION),
            ("muestra_parcial", "si" if limite else "no"),
        ],
    )
    con.commit()

    print("Optimizando indice...")
    con.execute("PRAGMA optimize")
    con.execute("VACUUM")
    con.close()
    return n


def _volcar(con: sqlite3.Connection, lote: list[tuple]) -> None:
    con.executemany(
        "INSERT OR REPLACE INTO contribuyente "
        "(ruc, razon_social, estado, condicion_domicilio, ubigeo, direccion) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        lote,
    )


def main() -> int:
    p = argparse.ArgumentParser(description="Construye el indice local del Padron Reducido.")
    p.add_argument("--zip", type=Path, default=RAIZ / "data" / "padron_reducido_ruc.zip")
    p.add_argument("--db", type=Path, default=RAIZ / "data" / "padron.sqlite3")
    p.add_argument("--limite", type=int, default=None, help="Ingerir solo N filas (pruebas).")
    p.add_argument("--forzar-descarga", action="store_true")
    args = p.parse_args()

    last_modified = None
    if args.forzar_descarga or not args.zip.exists():
        last_modified = descargar(args.zip)
    else:
        print(f"Reutilizando {args.zip} ({args.zip.stat().st_size / 1e6:.0f} MB)")
        last_modified = consultar_last_modified()
        if last_modified:
            print(f"  SUNAT informa Last-Modified: {last_modified}")
        else:
            print("  No se pudo consultar la fecha de SUNAT (sin red).")

    n = construir(args.zip, args.db, args.limite, last_modified)
    tam = args.db.stat().st_size / 1e9
    print(f"\nListo: {n:,} contribuyentes en {args.db} ({tam:.2f} GB)")
    if args.limite:
        print("AVISO: es una muestra parcial, no el padron completo.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
