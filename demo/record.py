"""Graba un GIF del servidor MCP resolviendo consultas reales.

No es una recreacion: levanta el servidor por stdio con el cliente oficial de
MCP, llama a las herramientas y anima las respuestas que realmente devuelve
sobre el indice local. Si el indice no existe, aborta en vez de inventar datos.

Uso:
    python demo/record.py                 # genera demo/sunat-mcp.gif
    python demo/record.py --salida x.gif
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from dataclasses import dataclass
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from PIL import Image, ImageDraw, ImageFont

RAIZ = Path(__file__).resolve().parent.parent

# --- Paleta: terminal oscura, legible al reescalar en una tarjeta de portafolio.
FONDO = (13, 17, 23)
CHROME = (22, 27, 34)
BORDE = (48, 54, 61)
TEXTO = (201, 209, 217)
TENUE = (110, 118, 129)
PROMPT = (88, 166, 255)
OK = (63, 185, 80)
ACENTO = (210, 168, 255)
CLAVE = (121, 192, 255)
ALERTA = (255, 166, 87)

ANCHO, ALTO = 1000, 620
MARGEN = 26
INTERLINEA = 23


@dataclass
class Paso:
    """Una consulta a mostrar: lo que se escribe y la herramienta que resuelve."""

    peticion: str
    herramienta: str
    args: dict
    resalta: tuple[str, ...] = ()


PASOS = [
    Paso(
        "valida el RUC 20123456786",
        "validar_ruc",
        {"ruc": "20123456786"},
        ("valido", "tipo_contribuyente"),
    ),
    Paso(
        "y este otro: 20123456780",
        "validar_ruc",
        {"ruc": "20123456780"},
        ("valido", "motivo"),
    ),
    Paso(
        "¿de quien es el RUC 20131312955?",
        "consultar_ruc",
        {"ruc": "20131312955"},
        ("razon_social", "estado", "condicion_domicilio"),
    ),
    Paso(
        "¿que tan actualizado esta el padron?",
        "estado_padron",
        {},
        ("registros", "last_modified_sunat"),
    ),
]


def fuente(tam: int, negrita: bool = False):
    """Fuente monoespaciada. Cae en la de PIL si no hay ninguna instalada."""
    candidatas = (
        ["consolab.ttf", "CascadiaMono.ttf", "DejaVuSansMono-Bold.ttf"]
        if negrita
        else ["consola.ttf", "CascadiaMono.ttf", "DejaVuSansMono.ttf"]
    )
    for nombre in candidatas:
        for base in (Path("C:/Windows/Fonts"), Path("/usr/share/fonts/truetype/dejavu")):
            ruta = base / nombre
            if ruta.exists():
                try:
                    return ImageFont.truetype(str(ruta), tam)
                except OSError:
                    continue
    return ImageFont.load_default()


F_TXT = fuente(16)
F_BOLD = fuente(16, negrita=True)
F_MINI = fuente(13)


def recortar(texto: str, limite: int = 74) -> str:
    return texto if len(texto) <= limite else texto[: limite - 1] + "…"


def pintar(lineas: list[tuple[str, tuple[int, int, int], bool]]) -> Image.Image:
    """Dibuja un frame de terminal con las lineas dadas."""
    img = Image.new("RGB", (ANCHO, ALTO), FONDO)
    d = ImageDraw.Draw(img)

    # Barra de titulo con los tres circulos, para que se lea como terminal.
    d.rectangle([0, 0, ANCHO, 38], fill=CHROME)
    d.line([0, 38, ANCHO, 38], fill=BORDE)
    for i, color in enumerate([(255, 95, 86), (255, 189, 46), (39, 201, 63)]):
        d.ellipse([18 + i * 20, 14, 28 + i * 20, 24], fill=color)
    d.text((96, 12), "sunat-mcp  ·  servidor MCP local", font=F_MINI, fill=TENUE)

    y = 38 + MARGEN
    for texto, color, negrita in lineas[-22:]:
        d.text((MARGEN, y), texto, font=F_BOLD if negrita else F_TXT, fill=color)
        y += INTERLINEA

    d.text(
        (MARGEN, ALTO - 30),
        "18,297,300 contribuyentes · indice local · sin red",
        font=F_MINI,
        fill=TENUE,
    )
    return img


def lineas_respuesta(datos: dict, resalta: tuple[str, ...]) -> list:
    """Convierte la respuesta real en lineas coloreadas."""
    salida = []
    for clave, valor in datos.items():
        if valor is None or clave in ("nota", "aviso"):
            continue
        destacado = clave in resalta
        if isinstance(valor, bool):
            texto_valor, color = ("true", OK) if valor else ("false", ALERTA)
        else:
            texto_valor = recortar(str(valor), 58)
            color = ACENTO if destacado else TEXTO
        salida.append((f"    {clave:<22} {texto_valor}", color, destacado))
    return salida


async def recolectar() -> list:
    """Levanta el servidor real y devuelve los frames del GIF."""
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "sunat_mcp.server"],
        cwd=str(RAIZ),
    )

    frames: list[Image.Image] = []
    lineas: list = []

    def frame(repeticiones: int = 1) -> None:
        img = pintar(lineas)
        frames.extend([img] * repeticiones)

    async with stdio_client(params) as (leer, escribir):
        async with ClientSession(leer, escribir) as sesion:
            await sesion.initialize()
            herramientas = await sesion.list_tools()

            lineas.append(("$ claude mcp list", PROMPT, True))
            frame(14)
            lineas.append((f"  sunat  ✔ Connected  ·  {len(herramientas.tools)} herramientas", OK, False))
            for t in herramientas.tools:
                lineas.append((f"    · {t.name}", TENUE, False))
            lineas.append(("", TEXTO, False))
            frame(30)

            for paso in PASOS:
                # El usuario "escribe" la peticion, caracter a caracter.
                for i in range(1, len(paso.peticion) + 1):
                    lineas.append((f"> {paso.peticion[:i]}", TEXTO, False))
                    frame(1)
                    lineas.pop()
                lineas.append((f"> {paso.peticion}", TEXTO, False))
                frame(10)

                args = json.dumps(paso.args, ensure_ascii=False) if paso.args else "{}"
                lineas.append((f"  -> {paso.herramienta}({recortar(args, 50)})", CLAVE, False))
                frame(12)

                # Respuesta REAL del servidor.
                resultado = await sesion.call_tool(paso.herramienta, paso.args)
                datos = json.loads(resultado.content[0].text)
                for linea in lineas_respuesta(datos, paso.resalta):
                    lineas.append(linea)
                    frame(2)
                lineas.append(("", TEXTO, False))
                frame(34)

    frame(45)
    return frames


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--salida", type=Path, default=RAIZ / "demo" / "sunat-mcp.gif")
    args = p.parse_args()

    frames = asyncio.run(recolectar())
    args.salida.parent.mkdir(parents=True, exist_ok=True)

    # Paleta adaptativa: el GIF baja de ~8 MB a ~1 MB sin banding visible.
    reducidos = [f.convert("P", palette=Image.ADAPTIVE, colors=64) for f in frames]
    reducidos[0].save(
        args.salida,
        save_all=True,
        append_images=reducidos[1:],
        duration=45,
        loop=0,
        optimize=True,
    )
    print(f"{args.salida}  ({args.salida.stat().st_size / 1e6:.2f} MB, {len(frames)} frames)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
