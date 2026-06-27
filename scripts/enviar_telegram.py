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
import re
from datetime import datetime, timezone
from pathlib import Path

import geopandas as gpd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import matplotlib.patheffects as pe
import matplotlib.image as mpimg
from PIL import Image
import cairosvg
import requests

# ── Rutas ────────────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
META_FILE = DATA_DIR / "irdi_meta.json"

# ── Telegram ─────────────────────────────────────────────────────────────────
BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
CHAT_ID   = os.environ.get("TELEGRAM_CHAT_ID", "")
TELEGRAM_API = f"https://api.telegram.org/bot{BOT_TOKEN}"

# ── CRS de traballo (ETRS89 UTM 29N · proxección oficial Galicia) ─────────────
CRS_GALICIA = "EPSG:25829"

# ── Paleta IRDI ───────────────────────────────────────────────────────────────
CORES = {
    0: "#6b7f8e",
    1: "#0033CC",
    2: "#33CC00",
    3: "#FFCC00",
    4: "#FF6600",
    5: "#CC0000",
}
ETIQUETAS = {
    0: "Sen dato",
    1: "Baixo",
    2: "Moderado",
    3: "Alto",
    4: "Moi alto",
    5: "Extremo",
}

# ── Estilo ────────────────────────────────────────────────────────────────────
BG_FIGURE   = "#080f18"
BG_PANEL    = "#0d1520"
COR_BORDO   = "#1e2d3d"
COR_TEXTO   = "#e8eef4"
COR_SUAVE   = "#7a9bb5"
COR_LARANXA = "#E8590C"
COR_MAR     = "#a8c8e8"   # azul mar (fondo dos eixes)
COR_VECIÑOS = "#4a5568"   # gris para Portugal/Asturias/Castela

DIAS_NOMES = {
    "dia_1": "Hoxe",
    "dia_2": "Mañá",
    "dia_3": "Pasado mañá",
    "dia_4": "En 3 días",
}

# ── Logos ─────────────────────────────────────────────────────────────────────

def cargar_logo(nome_svg: str) -> "Image.Image | None":
    """Converte un SVG do repo a PIL Image (RGBA)."""
    ruta = BASE_DIR / nome_svg
    if not ruta.exists():
        print(f"  AVISO: non existe logo {ruta}", file=sys.stderr)
        return None
    try:
        png_bytes = cairosvg.svg2png(url=str(ruta), output_width=400)
        return Image.open(io.BytesIO(png_bytes)).convert("RGBA")
    except Exception as e:
        print(f"  AVISO: non se puido cargar {nome_svg}: {e}", file=sys.stderr)
        return None


def colocar_logos(fig, logo_vost, logo_alvora,
                  x_dereita: float, y_centro: float,
                  alto_frac: float, fig_w: float, fig_h: float,
                  alpha: float = 0.85):
    """Coloca VOST e ALVORA como eixes matplotlib, pegados á dereita.
    Coordenadas en fracción de figura (0-1)."""
    import numpy as np

    separacion = 0.010
    x_cursor   = x_dereita - 0.012   # marxe dereita

    for logo in [logo_alvora, logo_vost]:   # dereita → esquerda
        if logo is None:
            continue
        asp    = logo.width / logo.height
        w_frac = alto_frac * asp * (fig_h / fig_w)
        x0     = x_cursor - w_frac
        y0     = y_centro - alto_frac / 2

        ax_l = fig.add_axes([x0, y0, w_frac, alto_frac])
        ax_l.set_axis_off()
        ax_l.patch.set_alpha(0)

        arr = np.array(logo.convert("RGBA")).astype(np.uint8)
        a_ch = arr[:, :, 3].astype(float) * alpha
        arr[:, :, 3] = a_ch.clip(0, 255).astype(np.uint8)
        ax_l.imshow(arr, aspect="auto", interpolation="lanczos")

        x_cursor = x0 - separacion

# ── Utilidades ────────────────────────────────────────────────────────────────

def cargar_gdf(dia: str) -> gpd.GeoDataFrame | None:
    ruta = DATA_DIR / f"irdi_{dia}.geojson"
    if not ruta.exists():
        print(f"  AVISO: non existe {ruta}", file=sys.stderr)
        return None
    gdf = gpd.read_file(ruta)
    # Reproxectar a UTM 29N para proporcións correctas
    gdf = gdf.to_crs(CRS_GALICIA)
    gdf["_cor"] = gdf["risco_valor"].apply(
        lambda v: CORES.get(int(v) if v == v else 0, CORES[0])
    )
    return gdf


def data_formatted(meta: dict) -> str:
    raw = meta.get("actualizacion_fonte", "")
    if raw:
        try:
            m = re.search(r"(\d{1,2}) de (\w+) de (\d{4})", raw)
            if m:
                meses = {
                    "enero":"xaneiro","febrero":"febreiro","marzo":"marzo",
                    "abril":"abril","mayo":"maio","junio":"xuño",
                    "julio":"xullo","agosto":"agosto","septiembre":"setembro",
                    "octubre":"outubro","noviembre":"novembro","diciembre":"decembro",
                }
                d, mes_es, a = m.group(1), m.group(2).lower(), m.group(3)
                return f"{d} de {meses.get(mes_es, mes_es)} de {a}"
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


def concello_txt(n: int) -> str:
    return "concello" if n == 1 else "concellos"


def nivel_global(gdf: gpd.GeoDataFrame) -> tuple[float, str, str]:
    """Media ponderada do IRDI sobre os concellos con dato.
    Devolve (valor_float, etiqueta, emoji)."""
    sub = gdf[gdf["risco_valor"] > 0]["risco_valor"].astype(float)
    if sub.empty:
        return 0.0, "Sen dato", "⚪"
    media = sub.mean()
    # Mapeo a nivel máis próximo
    if media < 1.5:
        et, em = "Baixo",    "🔵"
    elif media < 2.5:
        et, em = "Moderado", "🟢"
    elif media < 3.5:
        et, em = "Alto",     "🟡"
    elif media < 4.5:
        et, em = "Moi alto", "🟠"
    else:
        et, em = "Extremo",  "🔴"
    return media, et, em


# ── Renderizado ───────────────────────────────────────────────────────────────

def debuxar_mapa(ax, gdf: gpd.GeoDataFrame, titulo: str, mostrar_lenda: bool = True):
    """Debuja un mapa IRDI nun eixo matplotlib."""
    # Fondo cor mar (simula o océano Atlántico)
    ax.set_facecolor(COR_MAR)

    # Polígonos por nivel de risco
    for val, cor in CORES.items():
        sub = gdf[gdf["risco_valor"] == val]
        if not sub.empty:
            sub.plot(ax=ax, color=cor, linewidth=0.3,
                     edgecolor="#00000066", zorder=2)

    ax.set_axis_off()
    # NON poñemos set_aspect('equal') aquí; xa está implícito en geopandas con UTM

    # Título sobre o mapa
    ax.set_title(titulo, fontsize=10, fontweight="bold",
                 color=COR_TEXTO, pad=6,
                 path_effects=[pe.withStroke(linewidth=2, foreground=BG_FIGURE)])

    # Lenda
    if mostrar_lenda:
        parches = [
            mpatches.Patch(color=CORES[v], label=ETIQUETAS[v])
            for v in sorted(CORES) if v > 0
        ]
        ax.legend(
            handles=parches,
            loc="lower left",
            fontsize=7.5,
            frameon=True,
            framealpha=0.88,
            facecolor=BG_PANEL,
            edgecolor=COR_BORDO,
            labelcolor=COR_TEXTO,
            handlelength=1.2,
            handleheight=1.0,
            borderpad=0.6,
        )


def xerar_imaxe_dia1(gdf: gpd.GeoDataFrame, meta: dict) -> bytes:
    data   = data_formatted(meta)
    niveis = contar_niveis(gdf)
    media, et_media, em_media = nivel_global(gdf)
    cor_media = CORES.get(
        min(range(6), key=lambda v: abs(v - media) if v > 0 else 99),
        CORES[2]
    )

    # Calcular proporción natural do mapa en UTM para non achatalo
    bounds = gdf.total_bounds  # [minx, miny, maxx, maxy]
    ancho_m = bounds[2] - bounds[0]
    alto_m  = bounds[3] - bounds[1]
    ratio   = alto_m / ancho_m   # ~1.15–1.25 para Galicia en UTM

    fig_w = 8.5
    fig_h = fig_w * ratio + 2.2   # +2.2 para título e barra inferior
    fig = plt.figure(figsize=(fig_w, fig_h), facecolor=BG_FIGURE)

    # Proporciones: título 8%, mapa central, barra 13%
    titulo_h = 0.08
    barra_h  = 0.13
    mapa_h   = 1.0 - titulo_h - barra_h

    # ── Área de título ────────────────────────────────────────────────────────
    ax_t = fig.add_axes([0, 1 - titulo_h, 1, titulo_h])
    ax_t.set_facecolor(BG_FIGURE)
    ax_t.set_axis_off()
    ax_t.axhline(y=0.97, xmin=0.03, xmax=0.97,
                 color=COR_LARANXA, linewidth=2.5)
    ax_t.text(0.5, 0.58,
              "IRDI · Índice de Risco Diario de Incendios",
              ha="center", va="center",
              fontsize=12, fontweight="bold", color=COR_TEXTO,
              transform=ax_t.transAxes)
    ax_t.text(0.5, 0.18,
              f"Galicia · {data}  ·  Fonte: Medio Rural, Xunta de Galicia",
              ha="center", va="center",
              fontsize=8, color=COR_SUAVE, transform=ax_t.transAxes)

    # ── Mapa ──────────────────────────────────────────────────────────────────
    ax_m = fig.add_axes([0.02, barra_h, 0.96, mapa_h])
    ax_m.set_facecolor(COR_MAR)
    debuxar_mapa(ax_m, gdf, "Previsión para hoxe", mostrar_lenda=True)

    # ── Barra inferior ────────────────────────────────────────────────────────
    ax_b = fig.add_axes([0, 0, 1, barra_h])
    ax_b.set_facecolor(BG_PANEL)
    ax_b.set_axis_off()
    ax_b.axhline(y=0.97, color=COR_BORDO, linewidth=0.8)

    ax_b.text(0.03, 0.65, "Nivel global:",
              ha="left", va="center", fontsize=8.5,
              color=COR_SUAVE, transform=ax_b.transAxes)
    ax_b.text(0.03, 0.28, f"{et_media.upper()}  {media:.1f}/5",
              ha="left", va="center", fontsize=15,
              fontweight="bold", color=cor_media,
              transform=ax_b.transAxes,
              path_effects=[pe.withStroke(linewidth=3, foreground=BG_PANEL)])

    x = 0.28
    for val, (et, n) in sorted(niveis.items()):
        if val == 0:
            continue
        ax_b.text(x, 0.65, et,
                  ha="left", va="center", fontsize=7,
                  color=CORES[val], fontweight="bold",
                  transform=ax_b.transAxes)
        ax_b.text(x, 0.28, f"{n} {concello_txt(n)}",
                  ha="left", va="center", fontsize=8.5,
                  color=COR_TEXTO, transform=ax_b.transAxes)
        x += 0.155
        if x > 0.95:
            break

    # ── Logos na barra inferior (dereita, centrados verticalmente) ───────────
    logo_vost   = cargar_logo("logo-vost-dark.svg")
    logo_alvora = cargar_logo("logo-alvora.svg")

    alto_logo = barra_h * 0.52        # 52% da altura da barra
    y_centro  = barra_h / 2           # centro da barra en coords figura
    colocar_logos(fig, logo_vost, logo_alvora,
                  x_dereita=0.99, y_centro=y_centro,
                  alto_frac=alto_logo, fig_w=fig_w, fig_h=fig_h)

    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=150, bbox_inches="tight",
                facecolor=BG_FIGURE, pad_inches=0.04)
    plt.close(fig)
    buf.seek(0)
    return buf.read()


def xerar_imaxe_3dias(gdfs: dict, meta: dict) -> bytes:
    pares = [(d, gdfs[d]) for d in ["dia_2", "dia_3", "dia_4"] if d in gdfs]
    n = len(pares)
    if n == 0:
        return b""

    data = data_formatted(meta)

    # Calcular altura proporcional baseada no primeiro mapa
    bounds = pares[0][1].total_bounds
    ratio  = (bounds[3] - bounds[1]) / (bounds[2] - bounds[0])

    fig_w = 14
    mapa_w_frac = 0.30   # cada mapa ocupa ~30% do ancho
    mapa_h_px   = fig_w * mapa_w_frac * ratio
    titulo_h_in = 0.9
    fig_h = mapa_h_px + titulo_h_in

    fig = plt.figure(figsize=(fig_w, fig_h), facecolor=BG_FIGURE)

    titulo_frac = titulo_h_in / fig_h

    # Título xeral
    ax_t = fig.add_axes([0, 1 - titulo_frac, 1, titulo_frac])
    ax_t.set_facecolor(BG_FIGURE)
    ax_t.set_axis_off()
    ax_t.axhline(y=0.95, xmin=0.02, xmax=0.98,
                 color=COR_LARANXA, linewidth=2)
    ax_t.text(0.5, 0.55,
              "IRDI · Previsión próximos días",
              ha="center", va="center",
              fontsize=14, fontweight="bold", color=COR_TEXTO,
              transform=ax_t.transAxes)
    ax_t.text(0.5, 0.10,
              f"Galicia · {data}  ·  Fonte: Medio Rural, Xunta de Galicia",
              ha="center", va="center",
              fontsize=8, color=COR_SUAVE, transform=ax_t.transAxes)

    # Tres mapas xustos sen marxe extra
    ancho  = 0.96 / n
    marxe_l = 0.02
    for i, (dia, gdf) in enumerate(pares):
        nome  = DIAS_NOMES.get(dia, dia)
        media_d, et_media_d, _ = nivel_global(gdf)
        subtit = f"{nome}  ·  Nivel global: {et_media_d} ({media_d:.1f}/5)"

        ax = fig.add_axes([marxe_l + i * ancho, 0, ancho - 0.01, 1 - titulo_frac])
        ax.set_facecolor(COR_MAR)
        debuxar_mapa(ax, gdf, subtit, mostrar_lenda=(i == 0))

    # ── Logos no título (dereita, centrados verticalmente) ───────────────────
    logo_vost   = cargar_logo("logo-vost-dark.svg")
    logo_alvora = cargar_logo("logo-alvora.svg")

    alto_logo = titulo_frac * 0.48
    y_centro  = 1.0 - titulo_frac / 2
    colocar_logos(fig, logo_vost, logo_alvora,
                  x_dereita=0.99, y_centro=y_centro,
                  alto_frac=alto_logo, fig_w=fig_w, fig_h=fig_h)

    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=130, bbox_inches="tight",
                facecolor=BG_FIGURE, pad_inches=0.04)
    plt.close(fig)
    buf.seek(0)
    return buf.read()


# ── Telegram ─────────────────────────────────────────────────────────────────

def enviar_foto(imaxe_bytes: bytes, caption: str, reply_to: int | None = None) -> int | None:
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
    data   = data_formatted(meta)
    niveis = contar_niveis(gdf)
    media, et_media, em_media = nivel_global(gdf)

    lines = [
        f"🔥 <b>IRDI Galicia · {data}</b>",
        "",
        f"{em_media} <b>Nivel global: {et_media}</b>  <i>({media:.1f} / 5)</i>",
        "",
    ]
    for val, (et, n) in sorted(niveis.items()):
        if val == 0:
            continue
        emoji = {1:"🔵",2:"🟢",3:"🟡",4:"🟠",5:"🔴"}.get(val,"⚪")
        lines.append(f"{emoji} {et} · {n} {concello_txt(n)}")
    lines += [
        "",
        "<i>Fonte: Medio Rural, Xunta de Galicia</i>",
        "<i>VOST Galicia × ALVORA</i>",
    ]
    return "\n".join(lines)


def construir_caption_3dias(gdfs: dict) -> str:
    lines = ["📅 <b>Previsión IRDI · Próximos días</b>", ""]
    for dia in ["dia_2", "dia_3", "dia_4"]:
        if dia not in gdfs:
            continue
        gdf  = gdfs[dia]
        nome = DIAS_NOMES.get(dia, dia)
        media, et_media, em_media = nivel_global(gdf)
        lines.append(
            f"{em_media} <b>{nome}</b> · Nivel global: {et_media} <i>({media:.1f} / 5)</i>"
        )
    lines += [
        "",
        "<i>Fonte: Medio Rural, Xunta de Galicia · VOST Galicia × ALVORA</i>",
    ]
    return "\n".join(lines)


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    if not BOT_TOKEN or not CHAT_ID:
        print("ERRO: TELEGRAM_BOT_TOKEN e TELEGRAM_CHAT_ID son obrigatorios.", file=sys.stderr)
        sys.exit(1)

    meta = {}
    if META_FILE.exists():
        with open(META_FILE, encoding="utf-8") as f:
            meta = json.load(f)

    dias_dispoñibles = meta.get("dias_disponibles", ["dia_1","dia_2","dia_3","dia_4"])
    print(f"Días dispoñibles: {dias_dispoñibles}")

    gdfs = {}
    for dia in dias_dispoñibles:
        gdf = cargar_gdf(dia)
        if gdf is not None:
            gdfs[dia] = gdf

    if "dia_1" not in gdfs:
        print("ERRO: non se puido cargar dia_1.", file=sys.stderr)
        sys.exit(1)

    print("Xerando imaxe día 1...")
    imaxe1  = xerar_imaxe_dia1(gdfs["dia_1"], meta)
    caption1 = construir_caption_dia1(gdfs["dia_1"], meta)
    msg_id  = enviar_foto(imaxe1, caption1)

    tres_dias = {d: gdfs[d] for d in ["dia_2","dia_3","dia_4"] if d in gdfs}
    if tres_dias:
        print("Xerando imaxe próximos 3 días...")
        imaxe2 = xerar_imaxe_3dias(tres_dias, meta)
        if imaxe2:
            caption2 = construir_caption_3dias(tres_dias)
            enviar_foto(imaxe2, caption2, reply_to=msg_id)

    print("✓ Proceso completado.")


if __name__ == "__main__":
    main()
