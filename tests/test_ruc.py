"""Pruebas de la validacion modulo 11. No tocan disco ni red."""

from __future__ import annotations

import pytest

from sunat_mcp.ruc import digito_verificador, es_valido, normalizar, validar


def _con_digito(base10: str) -> str:
    """Construye un RUC valido completando el digito verificador correcto."""
    return base10 + str(digito_verificador(base10))


class TestDigitoVerificador:
    def test_calcula_digito_conocido(self):
        # 20123456786 es el RUC sintetico usado en los ejemplos de DocuExtract.
        assert digito_verificador("2012345678") == 6

    def test_rechaza_longitud_incorrecta(self):
        with pytest.raises(ValueError):
            digito_verificador("123")

    def test_rechaza_no_numerico(self):
        with pytest.raises(ValueError):
            digito_verificador("20A2345678")

    @pytest.mark.parametrize("base", ["2012345678", "1045215942", "1080617369"])
    def test_el_digito_generado_siempre_valida(self, base):
        assert es_valido(_con_digito(base))


class TestValidar:
    def test_ruc_valido_persona_juridica(self):
        r = validar("20123456786")
        assert r.valido
        assert r.motivo is None
        assert r.tipo_contribuyente == "Persona juridica"

    def test_ruc_valido_persona_natural(self):
        # RUC real tomado de la cabecera publica del padron (persona natural).
        r = validar("10452159428")
        assert r.valido
        assert r.tipo_contribuyente == "Persona natural con negocio"

    def test_digito_verificador_incorrecto(self):
        r = validar("20123456780")
        assert not r.valido
        assert "Digito verificador incorrecto" in r.motivo
        assert r.digito_verificador_esperado == 6

    def test_longitud_incorrecta(self):
        r = validar("2012345678")
        assert not r.valido
        assert "11 digitos" in r.motivo

    def test_prefijo_invalido(self):
        r = validar("99123456786")
        assert not r.valido
        assert "Prefijo '99'" in r.motivo

    def test_vacio(self):
        r = validar("")
        assert not r.valido
        assert r.motivo == "No contiene digitos"

    def test_solo_letras(self):
        r = validar("ABCDEFGHIJK")
        assert not r.valido

    @pytest.mark.parametrize(
        "entrada",
        ["20-123456786", "20 123 456 786", " 20123456786 ", "20.123.456.786"],
    )
    def test_normaliza_separadores(self, entrada):
        r = validar(entrada)
        assert r.valido
        assert r.ruc == "20123456786"

    def test_normalizar_no_valida(self):
        assert normalizar("ab12cd34") == "1234"

    def test_todos_los_prefijos_vigentes_se_reconocen(self):
        for prefijo in ("10", "15", "16", "17", "20"):
            ruc = _con_digito(prefijo + "12345678")
            r = validar(ruc)
            assert r.valido, f"prefijo {prefijo} deberia ser valido"
            assert r.tipo_contribuyente is not None
