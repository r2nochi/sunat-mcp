"""Pruebas de la capa de indice y de la ingesta.

Generan su propio ZIP de padron sintetico con el mismo formato que publica
SUNAT (16 columnas, separador '|', latin-1, '-' como ausente). No dependen
del archivo real de 372 MiB ni de datos de ningun contribuyente real.
"""

from __future__ import annotations

import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

from sunat_mcp import padron as p
from sunat_mcp import revision as rv

RAIZ = Path(__file__).resolve().parent.parent

CABECERA = (
    "RUC|NOMBRE O RAZÓN SOCIAL|ESTADO DEL CONTRIBUYENTE|CONDICIÓN DE DOMICILIO|"
    "UBIGEO|TIPO DE VÍA|NOMBRE DE VÍA|CÓDIGO DE ZONA|TIPO DE ZONA|NÚMERO|"
    "INTERIOR|LOTE|DEPARTAMENTO|MANZANA|KILÓMETRO|"
)

FILAS = [
    # RUC valido, persona juridica, con direccion completa.
    "20123456786|COMERCIAL LOS ANDES S.A.C.|ACTIVO|HABIDO|150101|AV.|AREQUIPA|"
    "LIMA|URB.|1234|501|-|-|-|-|",
    # Persona natural sin direccion (todo en '-').
    "10452159428|GARCIA CHANCO CARLOS AUGUSTO|ACTIVO|HABIDO|-|-|-|-|-|-|-|-|-|-|-|",
    # Contribuyente de baja y no habido.
    "20987654321|TEXTILES DEL SUR E.I.R.L.|BAJA DEFINITIVA|NO HABIDO|040101|CAL.|"
    "SAN MARTIN|-|-|455|-|-|-|-|-|",
    # Otra razon social que comparte prefijo, para probar busqueda.
    "20100047218|COMERCIAL DEL NORTE S.A.|ACTIVO|HABIDO|130101|JR.|LOS OLIVOS|"
    "-|-|89|-|-|-|MZ B|-|",
    # El padron real trae algunas razones sociales en minuscula. Si el indice
    # comparara en binario, esta fila se perderia en silencio.
    "20555888991|Comercial Minuscula S.A.C.|ACTIVO|HABIDO|150101|-|-|-|-|-|-|-|-|-|-|",
    # RUCs con digito verificador correcto para la revision de proveedores
    # (el de TEXTILES DEL SUR no lo tiene y la revision lo marca invalido).
    "20600000005|DISTRIBUIDORA CERRADA S.A.C.|BAJA DE OFICIO|HABIDO|150101|-|-|-|-|-|-|-|-|-|-|",
    "20600000013|SERVICIOS FANTASMA S.R.L.|ACTIVO|NO HABIDO|150101|-|-|-|-|-|-|-|-|-|-|",
    # Estado y condicion ausentes ('-'): nunca deben contar como ok.
    "20600000048|SIN DATOS S.A.C.|-|-|-|-|-|-|-|-|-|-|-|-|-|",
]


@pytest.fixture(scope="module")
def zip_sintetico(tmp_path_factory) -> Path:
    """Crea un ZIP con el mismo formato que el padron oficial."""
    carpeta = tmp_path_factory.mktemp("padron")
    destino = carpeta / "padron_sintetico.zip"
    contenido = "\n".join([CABECERA, *FILAS]) + "\n"
    with zipfile.ZipFile(destino, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("padron_reducido_ruc.txt", contenido.encode("latin-1"))
    return destino


@pytest.fixture(scope="module")
def indice(zip_sintetico: Path, tmp_path_factory) -> Path:
    """Ejecuta la ingesta real sobre el ZIP sintetico."""
    db = tmp_path_factory.mktemp("db") / "padron.sqlite3"
    proceso = subprocess.run(
        [
            sys.executable,
            str(RAIZ / "scripts" / "ingest.py"),
            "--zip", str(zip_sintetico),
            "--db", str(db),
        ],
        capture_output=True,
        text=True,
        cwd=RAIZ,
    )
    assert proceso.returncode == 0, proceso.stderr
    assert db.exists()
    return db


class TestLimpieza:
    def test_guion_es_ausente(self):
        assert p.limpiar("-") is None

    def test_vacio_es_ausente(self):
        assert p.limpiar("   ") is None

    def test_recorta_espacios(self):
        assert p.limpiar("  LIMA  ") == "LIMA"

    def test_none_pasa(self):
        assert p.limpiar(None) is None


class TestComponerDireccion:
    def test_arma_direccion_completa(self):
        d = p.componer_direccion(
            {
                "TIPO DE VIA": "AV.", "NOMBRE DE VIA": "AREQUIPA",
                "NUMERO": "1234", "INTERIOR": "501",
                "TIPO DE ZONA": "URB.", "CODIGO DE ZONA": "LIMA",
            }
        )
        assert d == "AV. AREQUIPA NRO. 1234 INT. 501 URB. LIMA"

    def test_sin_datos_devuelve_none(self):
        assert p.componer_direccion({k: None for k in p.COLUMNAS}) is None

    def test_omite_partes_ausentes(self):
        d = p.componer_direccion({"TIPO DE VIA": "JR.", "NOMBRE DE VIA": "UNION"})
        assert d == "JR. UNION"


class TestIngestaYConsulta:
    def test_ingesta_carga_todas_las_filas(self, indice: Path):
        con = p.conectar(indice)
        total = con.execute("SELECT COUNT(*) FROM contribuyente").fetchone()[0]
        assert total == len(FILAS)

    def test_consulta_ruc_existente(self, indice: Path):
        c = p.consultar(p.conectar(indice), "20123456786")
        assert c is not None
        assert c.razon_social == "COMERCIAL LOS ANDES S.A.C."
        assert c.estado == "ACTIVO"
        assert c.condicion_domicilio == "HABIDO"
        assert c.ubigeo == "150101"
        assert c.direccion == "AV. AREQUIPA NRO. 1234 INT. 501 URB. LIMA"

    def test_consulta_ruc_inexistente(self, indice: Path):
        assert p.consultar(p.conectar(indice), "20999999999") is None

    def test_direccion_ausente_queda_en_none(self, indice: Path):
        c = p.consultar(p.conectar(indice), "10452159428")
        assert c.direccion is None
        assert c.ubigeo is None

    def test_conserva_estado_de_baja(self, indice: Path):
        c = p.consultar(p.conectar(indice), "20987654321")
        assert c.estado == "BAJA DEFINITIVA"
        assert c.condicion_domicilio == "NO HABIDO"

    def test_busqueda_por_prefijo(self, indice: Path):
        r = p.buscar_por_nombre(p.conectar(indice), "COMERCIAL")
        assert {c.ruc for c in r} == {"20123456786", "20100047218", "20555888991"}


class TestBusquedaIgnoraMayusculas:
    """Regresion: el indice usa COLLATE NOCASE.

    Con un indice BINARY, una busqueda por prefijo degeneraba en SCAN de ~18
    millones de filas (~40 s medidos) y ademas perdia las razones sociales que
    el padron publica en minuscula.
    """

    def test_consulta_en_minuscula_encuentra_registro_en_mayuscula(self, indice: Path):
        r = p.buscar_por_nombre(p.conectar(indice), "comercial los andes")
        assert [c.ruc for c in r] == ["20123456786"]

    def test_consulta_en_mayuscula_encuentra_registro_en_minuscula(self, indice: Path):
        r = p.buscar_por_nombre(p.conectar(indice), "COMERCIAL MINUSCULA")
        assert [c.ruc for c in r] == ["20555888991"]

    def test_subcadena_tambien_ignora_mayusculas(self, indice: Path):
        r = p.buscar_por_nombre(p.conectar(indice), "%minuscula")
        assert [c.ruc for c in r] == ["20555888991"]

    def test_el_prefijo_usa_el_indice_no_un_scan(self, indice: Path):
        """La busqueda por prefijo debe resolverse con SEARCH, nunca con SCAN."""
        con = p.conectar(indice)
        plan = " ".join(
            fila[-1]
            for fila in con.execute(
                "EXPLAIN QUERY PLAN "
                "SELECT ruc FROM contribuyente "
                "WHERE razon_social >= ? COLLATE NOCASE "
                "AND razon_social < ? COLLATE NOCASE "
                "ORDER BY razon_social COLLATE NOCASE LIMIT 5",
                ("COMERCIAL", "COMERCIAL\U0010ffff"),
            )
        )
        assert "SEARCH" in plan, plan
        assert "idx_razon_nocase" in plan, plan
        assert "SCAN contribuyente" not in plan, plan

    def test_busqueda_por_subcadena_con_porcentaje(self, indice: Path):
        r = p.buscar_por_nombre(p.conectar(indice), "%ANDES")
        assert len(r) == 1
        assert r[0].ruc == "20123456786"

    def test_busqueda_respeta_limite(self, indice: Path):
        r = p.buscar_por_nombre(p.conectar(indice), "COMERCIAL", limite=1)
        assert len(r) == 1

    def test_busqueda_vacia_no_explota(self, indice: Path):
        assert p.buscar_por_nombre(p.conectar(indice), "   ") == []

    def test_provenance_registra_origen(self, indice: Path):
        prov = p.provenance(p.conectar(indice))
        assert prov["fuente_url"].startswith("https://")
        assert len(prov["sha256_zip"]) == 64
        assert prov["registros"] == str(len(FILAS))
        assert "fecha_ingesta_utc" in prov
        # Un ZIP reutilizado sin fecha guardada no recibe la fecha que SUNAT
        # informa hoy: eso sellaria datos viejos como actuales.
        assert prov["last_modified_sunat"] == "desconocido"


class TestRevisionProveedores:
    def test_preparar_quita_duplicados_y_vacios_conservando_orden(self):
        unicos, dup = rv.preparar(["20600000013", " ", "20123456786", "20.600.000.013"])
        assert unicos == ["20600000013", "20123456786"]
        assert dup == 1

    def test_clasifica_cada_caso(self, indice: Path):
        con = p.conectar(indice)
        r = {
            x.ruc: x
            for x in rv.revisar(
                con,
                ["20123456786", "20600000005", "20600000013", "20987654321", "20600000021"],
            )
        }
        assert r["20123456786"].resultado == rv.OK
        assert r["20123456786"].motivos == []
        assert r["20600000005"].resultado == rv.OBSERVADO
        assert r["20600000005"].motivos == ["Estado: BAJA DE OFICIO"]
        assert r["20600000013"].resultado == rv.OBSERVADO
        assert r["20600000013"].motivos == ["Condicion de domicilio: NO HABIDO"]
        assert r["20987654321"].resultado == rv.INVALIDO
        assert r["20600000021"].resultado == rv.NO_ENCONTRADO

    def test_valor_desconocido_nunca_cuenta_como_ok(self, indice: Path):
        """Lista blanca: un estado que no sea exactamente ACTIVO queda observado."""
        con = p.conectar(indice)
        assert rv.revisar(con, ["20100047218"])[0].resultado == rv.OK
        assert all(x.resultado != rv.OK for x in rv.revisar(con, ["20600000005", "20600000013"]))

    def test_herramienta_mcp_resume_y_expone_fecha_del_padron(self, indice: Path, monkeypatch):
        from sunat_mcp import server

        monkeypatch.setenv("SUNAT_MCP_DB", str(indice))
        monkeypatch.setattr(server, "_con", None)
        out = server.revisar_proveedores(
            ["20123456786", "20123456786", "20600000013", "123"]
        )
        assert out["duplicados_omitidos"] == 1
        assert out["total_revisados"] == 3
        assert out["resumen"] == {"ok": 1, "observado": 1, "invalido": 1, "no_encontrado": 0}
        assert [x["ruc"] for x in out["resultados"]] == ["20123456786", "20600000013", "123"]
        assert len(out["padron"]["sha256_zip"]) == 64
        assert "fecha_ingesta_utc" in out["padron"]

    def test_entrada_sin_digitos_se_reporta_invalida_no_se_pierde(self):
        unicos, dup = rv.preparar(["N/A", "", "  ", "20123456786", "N/A"])
        assert unicos == ["N/A", "20123456786"]
        assert dup == 1
        r = rv.revisar_uno(None, "N/A")
        assert r.resultado == rv.INVALIDO

    def test_digitos_no_ascii_no_rompen_el_lote(self):
        """'2' superindice pasa str.isdigit() pero rompe int(); debe ignorarse."""
        assert rv.revisar_uno(None, "2012345678²").resultado == rv.INVALIDO
        assert rv.revisar_uno(None, "２０123456786").resultado == rv.INVALIDO

    def test_estado_sin_dato_queda_observado(self, indice: Path):
        r = rv.revisar(p.conectar(indice), ["20600000048"])[0]
        assert r.resultado == rv.OBSERVADO
        assert r.motivos == ["Estado: sin dato", "Condicion de domicilio: sin dato"]

    def test_herramienta_mcp_acepta_rucs_numericos(self, indice: Path, monkeypatch):
        from sunat_mcp import server

        monkeypatch.setenv("SUNAT_MCP_DB", str(indice))
        monkeypatch.setattr(server, "_con", None)
        out = server.revisar_proveedores([20123456786])
        assert out["resumen"]["ok"] == 1

    def test_herramienta_mcp_rechaza_listas_demasiado_grandes(self, monkeypatch):
        from sunat_mcp import server

        rucs = [f"20{i:09d}" for i in range(rv.MAX_RUCS + 1)]
        out = server.revisar_proveedores(rucs)
        assert "maximo" in out["error"]


class TestErroresClaros:
    def test_indice_ausente_da_instruccion(self, tmp_path: Path):
        with pytest.raises(p.PadronNoDisponible) as e:
            p.conectar(tmp_path / "no-existe.sqlite3")
        assert "scripts/ingest.py" in str(e.value)


class TestEsquemaCambiante:
    def test_cabecera_distinta_aborta(self, tmp_path: Path):
        """Si SUNAT cambia las columnas, la ingesta debe fallar ruidosamente."""
        malo = tmp_path / "malo.zip"
        with zipfile.ZipFile(malo, "w") as z:
            z.writestr(
                "padron_reducido_ruc.txt",
                "RUC|OTRA COSA|\n20123456786|X|\n".encode("latin-1"),
            )
        proceso = subprocess.run(
            [
                sys.executable,
                str(RAIZ / "scripts" / "ingest.py"),
                "--zip", str(malo),
                "--db", str(tmp_path / "x.sqlite3"),
            ],
            capture_output=True, text=True, cwd=RAIZ,
        )
        assert proceso.returncode != 0
        assert "esquema del padron cambio" in (proceso.stdout + proceso.stderr).lower()
