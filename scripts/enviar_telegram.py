#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Enviar IRDI a Telegram · VOST Galicia × ALVORA
Xera dúas imaxes:
  - Imaxe principal: mapa do día 1 (hoxe)
  - Imaxe extra: tres mapas (días 2, 3, 4) nunha fila
e envíaas ao canal/grupo de Telegram configurado.

Segredos necesarios (GitHub Secrets ou variables de entorno):
  TELEGRAM_BOT_TOKEN   → token do bot (@BotFather)
  TELEGRAM_CHAT_ID     → ID do canal/grupo (ex: -1001234567890 ou @micanal)
"""

import json
import os
import sys
import io
from datetime import datetime, timezone
from pathlib import Path

import geopandas as gpd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import matplotlib.patheffects as pe
import requests
import numpy as np

# ── Rutas ────────────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
META_FILE = DATA_DIR / "irdi_meta.json"

# ── Telegram ─────────────────────────────────────────────────────────────────
BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
CHAT_ID   = os.environ.get("TELEGRAM_CHAT_ID", "")

TELEGRAM_API = f"https://api.telegram.org/bot{BOT_TOKEN}"

# ── Paleta IRDI (igual que na web) ───────────────────────────────────────────
CORES = {
    0: "#6b7f8e",   # Sen dato
    1: "#0033CC",   # Baixo
    2: "#33CC00",   # Moderado
    3: "#FFCC00",   # Alto
    4: "#FF6600",   # Moi alto
    5: "#CC0000",   # Extremo
}
ETIQUETAS = {
    0: "Sen dato",
    1: "Baixo",
    2: "Moderado",
    3: "Alto",
    4: "Moi alto",
    5: "Extremo",
}

# Estilo xeral (escuro, como a web)
BG_FIGURE  = "#080f18"
BG_AXES    = "#080f18"
BG_PANEL   = "#0d1520"
COR_BORDO  = "#1e2d3d"
COR_TEXTO  = "#e8eef4"
COR_SUAVE  = "#7a9bb5"
COR_LARANXA = "#E8590C"

DIAS_NOMES = {
    "dia_1": "Hoxe",
    "dia_2": "Mañá",
    "dia_3": "Pasado mañá",
    "dia_4": "En 3 días",
}


# ── Utilidades ────────────────────────────────────────────────────────────────

def cargar_gdf(dia: str) -> gpd.GeoDataFrame | None:
    ruta = DATA_DIR / f"irdi_{dia}.geojson"
    if not ruta.exists():
        print(f"  AVISO: non existe {ruta}", file=sys.stderr)
        return None
    gdf = gpd.read_file(ruta)
    gdf["_cor"] = gdf["risco_valor"].apply(lambda v: CORES.get(int(v) if v == v else 0, CORES[0]))
    return gdf


def data_formatted(meta: dict) -> str:
    """Formatea a data de actualización de forma curta."""
    raw = meta.get("actualizacion_fonte", "")
    # Intentamos sacar só 'sábado 27 xuño 2026'
    if raw:
        # 'Actualizado el Sábado, 27 de Junio de 2026 a las 09:48'
        try:
            # Buscamos o patrón DD de Mes de AAAA
            import re
            m = re.search(r"(\d{1,2}) de (\w+) de (\d{4})", raw)
            if m:
                meses = {
                    "enero":"xaneiro","febrero":"febreiro","marzo":"marzo",
                    "abril":"abril","mayo":"maio","junio":"xuño",
                    "julio":"xullo","agosto":"agosto","septiembre":"setembro",
                    "octubre":"outubro","noviembre":"novembro","diciembre":"decembro",
                }
                dia_n, mes_es, ano = m.group(1), m.group(2).lower(), m.group(3)
                mes_gl = meses.get(mes_es, mes_es)
                return f"{dia_n} de {mes_gl} de {ano}"
        except Exception:
            pass
    return datetime.now(timezone.utc).strftime("%d/%m/%Y")


def contar_niveis(gdf: gpd.GeoDataFrame) -> dict:
    counts = {}
    for v, et in ETIQUETAS.items():
        n = int((gdf["risco_valor"] == v).sum())
        if n > 0:
            counts[v] = (et, n)
    return counts


# ── Renderizado ───────────────────────────────────────────────────────────────

def debuxar_mapa_dia(ax, gdf: gpd.GeoDataFrame, titulo: str, mostrar_leyenda: bool = True):
    """Debuja un mapa IRDI nun eixo matplotlib."""
    ax.set_facecolor(BG_AXES)

    # Polígonos
    for val, cor in CORES.items():
        sub = gdf[gdf["risco_valor"] == val]
        if not sub.empty:
            sub.plot(ax=ax, color=cor, linewidth=0.15,
                     edgecolor="#00000055", zorder=2)

    # Bordes internos suaves
    gdf.boundary.plot(ax=ax, linewidth=0.1, color="#00000033", zorder=3)

    ax.set_axis_off()
    ax.set_aspect("equal")

    # Título do mapa
    ax.text(
        0.5, 1.01, titulo,
        transform=ax.transAxes,
        ha="center", va="bottom",
        fontsize=10, fontweight="bold",
        color=COR_TEXTO,
        path_effects=[pe.withStroke(linewidth=2, foreground=BG_FIGURE)],
    )

    # Lenda compacta por baixo (só no mapa principal)
    if mostrar_leyenda:
        parches = [
            mpatches.Patch(color=cor, label=ETIQUETAS[v])
            for v, cor in CORES.items()
            if v > 0
        ]
        leg = ax.legend(
            handles=parches,
            loc="lower left",
            fontsize=7,
            frameon=True,
            framealpha=0.85,
            facecolor=BG_PANEL,
            edgecolor=COR_BORDO,
            labelcolor=COR_TEXTO,
            handlelength=1.2,
            handleheight=1.0,
            borderpad=0.5,
        )


def xerar_imaxe_dia1(gdf: gpd.GeoDataFrame, meta: dict) -> bytes:
    """Xera a imaxe principal: mapa do día de hoxe."""
    data = data_formatted(meta)
    niveis = contar_niveis(gdf)

    # Nivel máximo presente
    nivel_max = max((v for v in niveis if v > 0), default=0)
    cor_max   = CORES.get(nivel_max, CORES[0])
    et_max    = ETIQUETAS.get(nivel_max, "Sen dato")

    fig = plt.figure(figsize=(9, 10), facecolor=BG_FIGURE)

    # Área de título
    ax_title = fig.add_axes([0, 0.91, 1, 0.09])
    ax_title.set_facecolor(BG_FIGURE)
    ax_title.set_axis_off()

    # Liña laranxa superior
    ax_title.axhline(y=0.98, xmin=0.04, xmax=0.96,
                     color=COR_LARANXA, linewidth=2.5)

    ax_title.text(0.5, 0.55,
                  "IRDI · Índice de Risco Diario de Incendios",
                  ha="center", va="center",
                  fontsize=11, fontweight="bold",
                  color=COR_TEXTO, transform=ax_title.transAxes)
    ax_title.text(0.5, 0.15,
                  f"Galicia · {data}  ·  Fonte: Medio Rural, Xunta de Galicia",
                  ha="center", va="center",
                  fontsize=7.5, color=COR_SUAVE, transform=ax_title.transAxes)

    # Mapa principal
    ax_map = fig.add_axes([0.02, 0.13, 0.96, 0.78])
    ax_map.set_facecolor(BG_AXES)
    debuxar_mapa_dia(ax_map, gdf, "Previsión para hoxe", mostrar_leyenda=True)

    # Barra inferior con stats
    ax_bar = fig.add_axes([0, 0, 1, 0.13])
    ax_bar.set_facecolor(BG_PANEL)
    ax_bar.set_axis_off()
    ax_bar.axhline(y=0.98, color=COR_BORDO, linewidth=0.8)

    # Nivel máximo destacado
    ax_bar.text(0.04, 0.62,
                "Nivel máximo:",
                ha="left", va="center", fontsize=8.5,
                color=COR_SUAVE, transform=ax_bar.transAxes)
    ax_bar.text(0.04, 0.28,
                et_max.upper(),
                ha="left", va="center", fontsize=16,
                fontweight="bold", color=cor_max,
                transform=ax_bar.transAxes,
                path_effects=[pe.withStroke(linewidth=3, foreground=BG_PANEL)])

    # Reconto de concellos por nivel
    x = 0.30
    for val, (et, n) in sorted(niveis.items()):
        if val == 0:
            continue
        ax_bar.text(x, 0.62, et,
                    ha="left", va="center", fontsize=7,
                    color=CORES[val], transform=ax_bar.transAxes,
                    fontweight="bold")
        ax_bar.text(x, 0.28, f"{n} concellos",
                    ha="left", va="center", fontsize=8.5,
                    color=COR_TEXTO, transform=ax_bar.transAxes)
        x += 0.14
        if x > 0.95:
            break

    # Marca VOST + ALVORA
    ax_bar.text(0.99, 0.20,
                "VOST Galicia × ALVORA",
                ha="right", va="center", fontsize=7,
                color=COR_SUAVE, transform=ax_bar.transAxes)

    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=150, bbox_inches="tight",
                facecolor=BG_FIGURE, pad_inches=0.05)
    plt.close(fig)
    buf.seek(0)
    return buf.read()


def xerar_imaxe_3dias(gdfs: dict, meta: dict) -> bytes:
    """Xera a imaxe con días 2, 3 e 4 en tres columnas."""
    dias_dispoñibles = [(d, gdfs[d]) for d in ["dia_2", "dia_3", "dia_4"] if d in gdfs]
    n = len(dias_dispoñibles)
    if n == 0:
        return b""

    data = data_formatted(meta)

    fig = plt.figure(figsize=(14, 7), facecolor=BG_FIGURE)

    # Título xeral
    ax_title = fig.add_axes([0, 0.90, 1, 0.10])
    ax_title.set_facecolor(BG_FIGURE)
    ax_title.set_axis_off()
    ax_title.axhline(y=0.97, xmin=0.02, xmax=0.98,
                     color=COR_LARANXA, linewidth=2)
    ax_title.text(0.5, 0.55,
                  "IRDI · Previsión próximos días",
                  ha="center", va="center",
                  fontsize=13, fontweight="bold", color=COR_TEXTO,
                  transform=ax_title.transAxes)
    ax_title.text(0.5, 0.12,
                  f"Galicia · {data}  ·  Fonte: Medio Rural, Xunta de Galicia  ·  VOST Galicia × ALVORA",
                  ha="center", va="center",
                  fontsize=7.5, color=COR_SUAVE, transform=ax_title.transAxes)

    # Tres mapas en fila
    ancho = 0.94 / n
    for i, (dia, gdf) in enumerate(dias_dispoñibles):
        nome_dia = DIAS_NOMES.get(dia, dia)
        nivel_max = max((int(v) for v in gdf["risco_valor"] if v == v and v > 0), default=0)
        cor_max   = CORES.get(nivel_max, CORES[0])
        et_max    = ETIQUETAS.get(nivel_max, "Sen dato")
        subtitulo = f"{nome_dia}  ·  Máx: {et_max}"

        ax = fig.add_axes([0.03 + i * ancho, 0.08, ancho - 0.015, 0.82])
        ax.set_facecolor(BG_AXES)
        debuxar_mapa_dia(ax, gdf, subtitulo, mostrar_leyenda=(i == 0))

    # Barra de lenda inferior (só se non se puxo no primeiro mapa)
    # (a lenda vai xa no primeiro mapa, abonda)

    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=130, bbox_inches="tight",
                facecolor=BG_FIGURE, pad_inches=0.05)
    plt.close(fig)
    buf.seek(0)
    return buf.read()


# ── Telegram ─────────────────────────────────────────────────────────────────

def enviar_foto(imaxe_bytes: bytes, caption: str, reply_to: int | None = None) -> int | None:
    """Envía unha foto a Telegram. Devolve o message_id."""
    params = {"chat_id": CHAT_ID, "caption": caption, "parse_mode": "HTML"}
    if reply_to:
        params["reply_to_message_id"] = reply_to

    r = requests.post(
        f"{TELEGRAM_API}/sendPhoto",
        params=params,
        files={"photo": ("irdi.png", imaxe_bytes, "image/png")},
        timeout=60,
    )
    if r.ok:
        msg_id = r.json().get("result", {}).get("message_id")
        print(f"  ✓ Foto enviada (message_id={msg_id})")
        return msg_id
    else:
        print(f"  ✗ Erro Telegram: {r.status_code} {r.text}", file=sys.stderr)
        return None


def construir_caption_dia1(gdf: gpd.GeoDataFrame, meta: dict) -> str:
    data = data_formatted(meta)
    niveis = contar_niveis(gdf)
    nivel_max = max((v for v in niveis if v > 0), default=0)
    et_max = ETIQUETAS.get(nivel_max, "Sen dato")

    lines = [
        f"🔥 <b>IRDI Galicia · {data}</b>",
        f"Índice de Risco Diario de Incendios Forestais",
        "",
        f"<b>Nivel máximo:</b> {et_max.upper()}",
    ]
    for val, (et, n) in sorted(niveis.items()):
        if val == 0:
            continue
        emoji = {1:"🔵",2:"🟢",3:"🟡",4:"🟠",5:"🔴"}.get(val,"⚪")
        lines.append(f"{emoji} <b>{et}:</b> {n} concellos")

    lines += [
        "",
        "Fonte: Medio Rural · Xunta de Galicia",
        "VOST Galicia × ALVORA",
    ]
    return "\n".join(lines)


def construir_caption_3dias(gdfs: dict) -> str:
    lines = ["📅 <b>Previsión IRDI · Próximos 3 días</b>", ""]
    for dia in ["dia_2", "dia_3", "dia_4"]:
        if dia not in gdfs:
            continue
        gdf = gdfs[dia]
        nome = DIAS_NOMES.get(dia, dia)
        niveis = contar_niveis(gdf)
        nivel_max = max((v for v in niveis if v > 0), default=0)
        et_max = ETIQUETAS.get(nivel_max, "Sen dato")
        emoji = {1:"🔵",2:"🟢",3:"🟡",4:"🟠",5:"🔴"}.get(nivel_max,"⚪")
        lines.append(f"{emoji} <b>{nome}:</b> nivel máximo {et_max}")
    return "\n".join(lines)


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    # Validar segredos
    if not BOT_TOKEN or not CHAT_ID:
        print("ERRO: TELEGRAM_BOT_TOKEN e TELEGRAM_CHAT_ID son obrigatorios.", file=sys.stderr)
        sys.exit(1)

    # Cargar metadatos
    meta = {}
    if META_FILE.exists():
        with open(META_FILE, encoding="utf-8") as f:
            meta = json.load(f)

    dias_dispoñibles = meta.get("dias_disponibles", ["dia_1","dia_2","dia_3","dia_4"])
    print(f"Días dispoñibles: {dias_dispoñibles}")

    # Cargar GeoDataFrames
    gdfs = {}
    for dia in dias_dispoñibles:
        gdf = cargar_gdf(dia)
        if gdf is not None:
            gdfs[dia] = gdf

    if "dia_1" not in gdfs:
        print("ERRO: non se puido cargar dia_1.", file=sys.stderr)
        sys.exit(1)

    # ── Imaxe 1: mapa de hoxe ────────────────────────────────────────────────
    print("Xerando imaxe día 1...")
    imaxe1 = xerar_imaxe_dia1(gdfs["dia_1"], meta)
    caption1 = construir_caption_dia1(gdfs["dia_1"], meta)
    msg_id = enviar_foto(imaxe1, caption1)

    # ── Imaxe 2: próximos 3 días ─────────────────────────────────────────────
    tres_dias = {d: gdfs[d] for d in ["dia_2","dia_3","dia_4"] if d in gdfs}
    if tres_dias:
        print("Xerando imaxe próximos 3 días...")
        imaxe2 = xerar_imaxe_3dias(tres_dias, meta)
        if imaxe2:
            caption2 = construir_caption_3dias(tres_dias)
            # Enviamos como resposta ao primeiro para agrupalos
            enviar_foto(imaxe2, caption2, reply_to=msg_id)
    else:
        print("  Sen datos de días futuros, omitindo segunda imaxe.")

    print("✓ Proceso completado.")


if __name__ == "__main__":
    main()
