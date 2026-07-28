"""Validacion y clasificacion de RUCs peruanos. Sin red, sin dependencias."""

from __future__ import annotations

from dataclasses import dataclass

# Factores del algoritmo modulo 11 de SUNAT, aplicados a los 10 primeros digitos.
_FACTORES = (5, 4, 3, 2, 7, 6, 5, 4, 3, 2)

# Prefijos de RUC vigentes y su significado segun SUNAT.
_TIPOS: dict[str, str] = {
    "10": "Persona natural con negocio",
    "15": "Persona natural no domiciliada",
    "16": "Persona natural (asignacion especial)",
    "17": "Persona juridica no domiciliada",
    "20": "Persona juridica",
}


@dataclass(frozen=True)
class ResultadoValidacion:
    """Resultado de validar un RUC. `valido` es la unica fuente de verdad."""

    ruc: str
    valido: bool
    motivo: str | None
    tipo_contribuyente: str | None
    digito_verificador_esperado: int | None


def digito_verificador(ruc_base: str) -> int:
    """Calcula el digito verificador (modulo 11) de los 10 primeros digitos del RUC.

    Lanza `ValueError` si `ruc_base` no son exactamente 10 digitos.
    """
    if len(ruc_base) != 10 or not ruc_base.isdigit():
        raise ValueError("El RUC base debe tener exactamente 10 digitos")

    suma = sum(int(d) * f for d, f in zip(ruc_base, _FACTORES))
    digito = 11 - (suma % 11)
    if digito == 10:
        return 0
    if digito == 11:
        return 1
    return digito


def normalizar(ruc: str) -> str:
    """Quita espacios, puntos y guiones. No valida nada."""
    return "".join(c for c in ruc if c.isdigit())


def validar(ruc: str) -> ResultadoValidacion:
    """Valida un RUC peruano: longitud, prefijo y digito verificador modulo 11.

    Esta comprobacion es puramente aritmetica y offline. Un RUC valido aqui
    puede no existir en SUNAT, estar de baja o no estar habido: para eso hay
    que consultarlo contra el Padron Reducido (`consultar_ruc`).
    """
    limpio = normalizar(ruc)

    if not limpio:
        return ResultadoValidacion(ruc, False, "No contiene digitos", None, None)

    if len(limpio) != 11:
        return ResultadoValidacion(
            limpio,
            False,
            f"Un RUC tiene 11 digitos; este tiene {len(limpio)}",
            None,
            None,
        )

    prefijo = limpio[:2]
    tipo = _TIPOS.get(prefijo)
    if tipo is None:
        return ResultadoValidacion(
            limpio,
            False,
            f"Prefijo '{prefijo}' no corresponde a ningun tipo de RUC vigente "
            f"(validos: {', '.join(sorted(_TIPOS))})",
            None,
            None,
        )

    esperado = digito_verificador(limpio[:10])
    if esperado != int(limpio[10]):
        return ResultadoValidacion(
            limpio,
            False,
            f"Digito verificador incorrecto: se esperaba {esperado}, llego {limpio[10]}",
            tipo,
            esperado,
        )

    return ResultadoValidacion(limpio, True, None, tipo, esperado)


def es_valido(ruc: str) -> bool:
    """Atajo booleano de `validar`."""
    return validar(ruc).valido
