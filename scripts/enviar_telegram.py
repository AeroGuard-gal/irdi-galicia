#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Enviar IRDI a Telegram · VOST Galicia × ALVORA
Segredos necesarios:
  TELEGRAM_BOT_TOKEN  → token do bot
  TELEGRAM_CHAT_ID    → ID do canal/grupo
"""

import io, json, os, re, sys
from datetime import datetime, timezone
from pathlib import Path

import cairosvg
import geopandas as gpd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import matplotlib.patheffects as pe
import numpy as np
import requests
from PIL import Image

# ── Rutas ────────────────────────────────────────────────────────────────────
BASE_DIR  = Path(__file__).resolve().parent.parent
DATA_DIR  = BASE_DIR / "data"
META_FILE = DATA_DIR / "irdi_meta.json"

# ── Telegram ─────────────────────────────────────────────────────────────────
BOT_TOKEN    = os.environ.get("TELEGRAM_BOT_TOKEN", "")
CHAT_ID      = os.environ.get("TELEGRAM_CHAT_ID", "")
TELEGRAM_API = f"https://api.telegram.org/bot{BOT_TOKEN}"

# ── Proxección oficial Galicia ────────────────────────────────────────────────
CRS_GALICIA = "EPSG:25829"

# ── Paleta IRDI ───────────────────────────────────────────────────────────────
CORES = {0:"#6b7f8e", 1:"#0033CC", 2:"#33CC00", 3:"#FFCC00", 4:"#FF6600", 5:"#CC0000"}
ETIQUETAS = {0:"Sen dato", 1:"Baixo", 2:"Moderado", 3:"Alto", 4:"Moi alto", 5:"Extremo"}
DIAS_NOMES = {"dia_1":"Hoxe", "dia_2":"Mañá", "dia_3":"Pasado mañá", "dia_4":"En 3 días"}

# ── Estilo ────────────────────────────────────────────────────────────────────
BG_FIGURE   = "#080f18"
BG_PANEL    = "#0d1520"
COR_BORDO   = "#1e2d3d"
COR_TEXTO   = "#e8eef4"
COR_SUAVE   = "#7a9bb5"
COR_LARANXA = "#E8590C"
COR_MAR     = "#a8c8e8"


# ── Datos ─────────────────────────────────────────────────────────────────────

def cargar_gdf(dia: str):
    ruta = DATA_DIR / f"irdi_{dia}.geojson"
    if not ruta.exists():
        return None
    gdf = gpd.read_file(ruta).to_crs(CRS_GALICIA)
    gdf["_cor"] = gdf["risco_valor"].apply(lambda v: CORES.get(int(v) if v==v else 0, CORES[0]))
    return gdf

def data_fmt(meta: dict) -> str:
    raw = meta.get("actualizacion_fonte", "")
    m = re.search(r"(\d{1,2}) de (\w+) de (\d{4})", raw)
    if m:
        meses = {"enero":"xaneiro","febrero":"febreiro","marzo":"marzo","abril":"abril",
                 "mayo":"maio","junio":"xuño","julio":"xullo","agosto":"agosto",
                 "septiembre":"setembro","octubre":"outubro","noviembre":"novembro","diciembre":"decembro"}
        return f"{m.group(1)} de {meses.get(m.group(2).lower(), m.group(2).lower())} de {m.group(3)}"
    return datetime.now(timezone.utc).strftime("%d/%m/%Y")

def contar_niveis(gdf) -> dict:
    return {v: (ETIQUETAS[v], int((gdf["risco_valor"]==v).sum()))
            for v in ETIQUETAS if v>0 and int((gdf["risco_valor"]==v).sum())>0}

def nivel_global(gdf):
    sub = gdf[gdf["risco_valor"]>0]["risco_valor"].astype(float)
    if sub.empty: return 0.0, "Sen dato", "⚪"
    m = sub.mean()
    if m < 1.5: return m, "Baixo",    "🔵"
    if m < 2.5: return m, "Moderado", "🟢"
    if m < 3.5: return m, "Alto",     "🟡"
    if m < 4.5: return m, "Moi alto", "🟠"
    return m, "Extremo", "🔴"

def cor_nivel_global(media: float) -> str:
    v = min(range(1,6), key=lambda x: abs(x - media))
    return CORES[v]

def concello_txt(n: int) -> str:
    return "concello" if n == 1 else "concellos"


# ── Logos ─────────────────────────────────────────────────────────────────────

def cargar_logo_pil(nome: str, px_alto: int) -> "Image.Image | None":
    ruta = BASE_DIR / nome
    if not ruta.exists():
        print(f"  AVISO: non existe {ruta}", file=sys.stderr)
        return None
    try:
        # Renderizamos a un alto fixo; o ancho axústase automaticamente
        png = cairosvg.svg2png(url=str(ruta), output_height=px_alto)
        return Image.open(io.BytesIO(png)).convert("RGBA")
    except Exception as e:
        print(f"  AVISO logo {nome}: {e}", file=sys.stderr)
        return None

def pegar_logos_dereita(img: Image.Image,
                         y_centro_px: int, alto_px: int,
                         alpha: float = 0.88) -> Image.Image:
    """Pega VOST e ALVORA centrados verticalmente en y_centro_px,
    pegados ao bordo dereito. Devolve imaxe RGBA."""
    img = img.convert("RGBA")
    w = img.width

    logos_nomes = ["logo-vost-dark.svg", "logo-alvora.svg"]
    logos = []
    for nome in logos_nomes:
        l = cargar_logo_pil(nome, alto_px)
        if l:
            # Aplicar alpha
            r,g,b,a = l.split()
            a = a.point(lambda p: int(p * alpha))
            logos.append(Image.merge("RGBA", (r,g,b,a)))

    if not logos:
        return img

    marxe_d     = 16   # marxe dereita en px
    separacion  = 10   # separación entre logos en px
    x_cursor    = w - marxe_d

    # Pegamos de dereita a esquerda: primeiro VOST, logo ALVORA
    for logo in logos:
        lw, lh = logo.size
        x0 = x_cursor - lw
        y0 = y_centro_px - lh // 2
        img.paste(logo, (x0, y0), logo)
        x_cursor = x0 - separacion

    return img


# ── Renderizado matplotlib ────────────────────────────────────────────────────

def debuxar_mapa(ax, gdf, titulo: str, mostrar_lenda: bool = True):
    ax.set_facecolor(COR_MAR)
    for val, cor in CORES.items():
        sub = gdf[gdf["risco_valor"]==val]
        if not sub.empty:
            sub.plot(ax=ax, color=cor, linewidth=0.3, edgecolor="#00000055", zorder=2)
    ax.set_axis_off()
    ax.set_title(titulo, fontsize=9.5, fontweight="bold", color=COR_TEXTO, pad=5,
                 path_effects=[pe.withStroke(linewidth=2, foreground=BG_FIGURE)])
    if mostrar_lenda:
        parches = [mpatches.Patch(color=CORES[v], label=ETIQUETAS[v]) for v in range(1,6)]
        ax.legend(handles=parches, loc="lower left", fontsize=7, frameon=True,
                  framealpha=0.88, facecolor=BG_PANEL, edgecolor=COR_BORDO,
                  labelcolor=COR_TEXTO, handlelength=1.2, handleheight=1.0, borderpad=0.6)


def xerar_imaxe_dia1(gdf, meta: dict) -> bytes:
    data              = data_fmt(meta)
    niveis            = contar_niveis(gdf)
    media, et_m, _    = nivel_global(gdf)
    cor_m             = cor_nivel_global(media)

    bounds  = gdf.total_bounds
    ratio   = (bounds[3]-bounds[1]) / (bounds[2]-bounds[0])
    DPI     = 150
    fig_w   = 8.5
    titulo_h = 0.08
    barra_h  = 0.13
    mapa_h   = 1.0 - titulo_h - barra_h
    fig_h   = fig_w * ratio + 2.2

    fig = plt.figure(figsize=(fig_w, fig_h), facecolor=BG_FIGURE, dpi=DPI)

    # Título
    ax_t = fig.add_axes([0, 1-titulo_h, 1, titulo_h])
    ax_t.set_facecolor(BG_FIGURE); ax_t.set_axis_off()
    ax_t.axhline(y=0.97, xmin=0.03, xmax=0.97, color=COR_LARANXA, linewidth=2.5)
    ax_t.text(0.5, 0.58, "IRDI · Índice de Risco Diario de Incendios",
              ha="center", va="center", fontsize=12, fontweight="bold",
              color=COR_TEXTO, transform=ax_t.transAxes)
    ax_t.text(0.5, 0.18, f"Galicia · {data}  ·  Fonte: Medio Rural, Xunta de Galicia",
              ha="center", va="center", fontsize=8, color=COR_SUAVE, transform=ax_t.transAxes)

    # Mapa
    ax_m = fig.add_axes([0.02, barra_h, 0.96, mapa_h])
    debuxar_mapa(ax_m, gdf, "Previsión para hoxe", mostrar_lenda=True)

    # Barra inferior
    ax_b = fig.add_axes([0, 0, 1, barra_h])
    ax_b.set_facecolor(BG_PANEL); ax_b.set_axis_off()
    ax_b.axhline(y=0.97, color=COR_BORDO, linewidth=0.8)
    ax_b.text(0.03, 0.65, "Nivel global:", ha="left", va="center",
              fontsize=8.5, color=COR_SUAVE, transform=ax_b.transAxes)
    ax_b.text(0.03, 0.28, f"{et_m.upper()}  {media:.1f}/5",
              ha="left", va="center", fontsize=15, fontweight="bold",
              color=cor_m, transform=ax_b.transAxes,
              path_effects=[pe.withStroke(linewidth=3, foreground=BG_PANEL)])
    x = 0.28
    for val, (et, n) in sorted(niveis.items()):
        ax_b.text(x, 0.65, et, ha="left", va="center", fontsize=7,
                  color=CORES[val], fontweight="bold", transform=ax_b.transAxes)
        ax_b.text(x, 0.28, f"{n} {concello_txt(n)}", ha="left", va="center",
                  fontsize=8.5, color=COR_TEXTO, transform=ax_b.transAxes)
        x += 0.155
        if x > 0.78: break   # deixamos espazo para os logos

    # Gardar sen tight para que as dimensións sexan exactas
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=DPI, facecolor=BG_FIGURE, pad_inches=0)
    plt.close(fig)
    buf.seek(0)

    # Pegar logos con PIL — posición exacta na barra inferior
    img = Image.open(buf)
    W, H = img.size
    barra_px   = int(H * barra_h)
    y_top_barra = H - barra_px
    logo_alto  = int(barra_px * 0.55)
    y_centro   = y_top_barra + barra_px // 2

    img = pegar_logos_dereita(img, y_centro_px=y_centro, alto_px=logo_alto)

    out = io.BytesIO()
    img.convert("RGB").save(out, format="PNG")
    out.seek(0)
    return out.read()


def xerar_imaxe_3dias(gdfs: dict, meta: dict) -> bytes:
    pares = [(d, gdfs[d]) for d in ["dia_2","dia_3","dia_4"] if d in gdfs]
    if not pares: return b""

    data  = data_fmt(meta)
    DPI   = 130
    fig_w = 14

    bounds     = pares[0][1].total_bounds
    ratio      = (bounds[3]-bounds[1]) / (bounds[2]-bounds[0])
    titulo_h_in = 0.85
    mapa_h_in   = fig_w * (0.96/len(pares)) * ratio
    fig_h       = mapa_h_in + titulo_h_in
    titulo_frac = titulo_h_in / fig_h

    fig = plt.figure(figsize=(fig_w, fig_h), facecolor=BG_FIGURE, dpi=DPI)

    # Título
    ax_t = fig.add_axes([0, 1-titulo_frac, 1, titulo_frac])
    ax_t.set_facecolor(BG_FIGURE); ax_t.set_axis_off()
    ax_t.axhline(y=0.95, xmin=0.02, xmax=0.98, color=COR_LARANXA, linewidth=2)
    ax_t.text(0.5, 0.60, "IRDI · Previsión próximos días",
              ha="center", va="center", fontsize=14, fontweight="bold",
              color=COR_TEXTO, transform=ax_t.transAxes)
    ax_t.text(0.5, 0.12, f"Galicia · {data}  ·  Fonte: Medio Rural, Xunta de Galicia",
              ha="center", va="center", fontsize=8, color=COR_SUAVE, transform=ax_t.transAxes)

    # Tres mapas
    n = len(pares)
    ancho = 0.96 / n
    for i, (dia, gdf) in enumerate(pares):
        media_d, et_d, _ = nivel_global(gdf)
        subtit = f"{DIAS_NOMES.get(dia, dia)}  ·  Nivel global: {et_d} ({media_d:.1f}/5)"
        ax = fig.add_axes([0.02 + i*ancho, 0, ancho-0.01, 1-titulo_frac])
        debuxar_mapa(ax, gdf, subtit, mostrar_lenda=(i==0))

    # Gardar sen tight
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=DPI, facecolor=BG_FIGURE, pad_inches=0)
    plt.close(fig)
    buf.seek(0)

    # Pegar logos con PIL — posición exacta na banda do título (arriba)
    img = Image.open(buf)
    W, H = img.size
    titulo_px = int(H * titulo_frac)
    logo_alto = int(titulo_px * 0.50)
    y_centro  = titulo_px // 2   # centro da banda do título desde o tope

    img = pegar_logos_dereita(img, y_centro_px=y_centro, alto_px=logo_alto)

    out = io.BytesIO()
    img.convert("RGB").save(out, format="PNG")
    out.seek(0)
    return out.read()


# ── Telegram ─────────────────────────────────────────────────────────────────

def enviar_foto(imaxe: bytes, caption: str, reply_to=None):
    params = {"chat_id": CHAT_ID, "caption": caption, "parse_mode": "HTML"}
    if reply_to: params["reply_to_message_id"] = reply_to
    r = requests.post(f"{TELEGRAM_API}/sendPhoto", params=params,
                      files={"photo": ("irdi.png", imaxe, "image/png")}, timeout=60)
    if r.ok:
        mid = r.json().get("result",{}).get("message_id")
        print(f"  ✓ Enviado (id={mid})")
        return mid
    print(f"  ✗ Erro: {r.status_code} {r.text}", file=sys.stderr)
    return None

def caption_dia1(gdf, meta) -> str:
    data = data_fmt(meta)
    niveis = contar_niveis(gdf)
    media, et_m, em_m = nivel_global(gdf)
    lines = [f"🔥 <b>IRDI Galicia · {data}</b>", "",
             f"{em_m} <b>Nivel global: {et_m}</b>  <i>({media:.1f} / 5)</i>", ""]
    emojis = {1:"🔵",2:"🟢",3:"🟡",4:"🟠",5:"🔴"}
    for val, (et, n) in sorted(niveis.items()):
        lines.append(f"{emojis.get(val,'⚪')} {et} · {n} {concello_txt(n)}")
    lines += ["", "<i>Fonte: Medio Rural, Xunta de Galicia</i>",
              "<i>VOST Galicia × ALVORA</i>"]
    return "\n".join(lines)

def caption_3dias(gdfs) -> str:
    lines = ["📅 <b>Previsión IRDI · Próximos días</b>", ""]
    emojis = {1:"🔵",2:"🟢",3:"🟡",4:"🟠",5:"🔴"}
    for dia in ["dia_2","dia_3","dia_4"]:
        if dia not in gdfs: continue
        media, et_m, em_m = nivel_global(gdfs[dia])
        lines.append(f"{em_m} <b>{DIAS_NOMES[dia]}</b> · Nivel global: {et_m} <i>({media:.1f} / 5)</i>")
    lines += ["", "<i>Fonte: Medio Rural, Xunta de Galicia · VOST Galicia × ALVORA</i>"]
    return "\n".join(lines)


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    if not BOT_TOKEN or not CHAT_ID:
        print("ERRO: faltan TELEGRAM_BOT_TOKEN ou TELEGRAM_CHAT_ID", file=sys.stderr)
        sys.exit(1)

    meta = json.loads(META_FILE.read_text()) if META_FILE.exists() else {}
    dias = meta.get("dias_disponibles", ["dia_1","dia_2","dia_3","dia_4"])

    gdfs = {d: cargar_gdf(d) for d in dias}
    gdfs = {d: g for d, g in gdfs.items() if g is not None}

    if "dia_1" not in gdfs:
        print("ERRO: sen datos de dia_1", file=sys.stderr); sys.exit(1)

    print("Xerando imaxe día 1...")
    mid = enviar_foto(xerar_imaxe_dia1(gdfs["dia_1"], meta), caption_dia1(gdfs["dia_1"], meta))

    tres = {d: gdfs[d] for d in ["dia_2","dia_3","dia_4"] if d in gdfs}
    if tres:
        print("Xerando imaxe 3 días...")
        enviar_foto(xerar_imaxe_3dias(tres, meta), caption_3dias(tres), reply_to=mid)

    print("✓ Completado.")

if __name__ == "__main__":
    main()
