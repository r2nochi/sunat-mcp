"""sunat-mcp: valida y consulta RUCs peruanos sin que salgan de tu maquina."""

from sunat_mcp.ruc import ResultadoValidacion, digito_verificador, es_valido, validar

__version__ = "0.1.0"

__all__ = [
    "ResultadoValidacion",
    "digito_verificador",
    "es_valido",
    "validar",
    "__version__",
]
