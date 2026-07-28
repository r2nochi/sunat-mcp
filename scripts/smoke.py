"""Prueba de humo: ejerce las 4 herramientas MCP contra el indice real.

No sustituye a los tests (`pytest`), que corren contra un padron sintetico.
Esto verifica que el indice construido localmente responde de verdad.

Uso:
    python scripts/smoke.py
    python scripts/smoke.py 20131312955   # consultar un RUC concreto
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sunat_mcp.server import (  # noqa: E402
    buscar_razon_social,
    consultar_ruc,
    estado_padron,
    validar_ruc,
)


def _mostrar(titulo: str, resultado, ms: float | None = None) -> None:
    marca = f"  ({ms:.1f} ms)" if ms is not None else ""
    print(f"\n### {titulo}{marca}")
    print(json.dumps(resultado, indent=2, ensure_ascii=False, default=str))


def _cronometrar(fn, *args, **kwargs):
    inicio = time.perf_counter()
    resultado = fn(*args, **kwargs)
    return resultado, (time.perf_counter() - inicio) * 1000


def main() -> int:
    # `@mcp.tool()` registra la funcion y la devuelve intacta, asi que se puede
    # llamar directamente. Si una version futura del SDK devuelve un envoltorio,
    # se accede a la funcion original con `.fn`.
    _validar = getattr(validar_ruc, "fn", validar_ruc)
    _consultar = getattr(consultar_ruc, "fn", consultar_ruc)
    _buscar = getattr(buscar_razon_social, "fn", buscar_razon_social)
    _estado = getattr(estado_padron, "fn", estado_padron)

    _mostrar("estado_padron", _estado())

    _mostrar("validar_ruc — valido", _validar("20123456786"))
    _mostrar("validar_ruc — digito incorrecto", _validar("20123456780"))
    _mostrar("validar_ruc — prefijo invalido", _validar("99123456786"))

    ruc = sys.argv[1] if len(sys.argv) > 1 else "20131312955"  # SUNAT
    resultado, ms = _cronometrar(_consultar, ruc)
    _mostrar(f"consultar_ruc — {ruc}", resultado, ms)

    resultado, ms = _cronometrar(_buscar, "COMERCIAL LOS ANDES", 5)
    _mostrar("buscar_razon_social — prefijo", resultado, ms)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
