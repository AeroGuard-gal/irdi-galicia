#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Actualizar IRDI · Índice de Risco Diario de Incendios de Galicia
"""

import json
import re
import sys
import time
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

import requests
from bs4 import BeautifulSoup

BASE = "https://mediorural.xunta.gal"
URL = "https://mediorural.xunta.gal/es/temas/defensa-monte/irdi"
DATA_DIR = Path(__file__).resolve().parent.parent / "data"
CONCELLOS_GEOJSON = DATA_DIR / "concellos_galicia.geojson"

NIVEIS = {
    "baixo":     {"valor": 1, "cor": "#2ECC71", "etiqueta": "Baixo"},
    "bajo":      {"valor": 1, "cor": "#2ECC71", "etiqueta": "Baixo"},
    "moderado":  {"valor": 2, "cor": "#F1C40F", "etiqueta": "Moderado"},
    "alto":      {"valor": 3, "cor": "#E67E22", "etiqueta": "Alto"},
    "moi alto":  {"valor": 4, "cor": "#E74C3C", "etiqueta": "Moi alto"},
    "muy alto":  {"valor": 4, "cor": "#E74C3C", "etiqueta": "Moi alto"},
    "extremo":   {"valor": 5, "cor": "#8E44AD", "etiqueta": "Extremo"},
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (VOST-Galicia IRDI bot; uso de proteccion civil)",
    "Accept-Language": "gl,es;q=0.9",
}


def limpar(txt):
    return re.sub(r"\s+", " ", (txt or "")).strip()


def normalizar(nome):
    if not nome:
        return ""
    s = unicodedata.normalize("NFKD", nome)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.upper().strip()
    s = re.sub(r"\s+", " ", s)
    s = re.sub(r"^(O|A|AS|OS)\s+", "", s)
    s = re.sub(r"\s*\((O|A|AS|OS)\)$", "", s)
    return s.strip()


def normalizar_texto_risco(texto):
    s = unicodedata.normalize("NFKD", texto or "")
    s = "".join(c for c in s if not unicodedata.combining(c))
    return s.lower().strip()


def clasificar_risco(texto, clases_css=""):
    t = normalizar_texto_risco(texto)
    if t in NIVEIS:
        return NIVEIS[t]
    if clases_css:
        c = clases_css.lower()
        for chave in ("extremo", "moi-alto", "muy-alto", "alto", "moderado", "baixo", "bajo"):
            if f"irdi-{chave}" in c:
                return NIVEIS.get(chave.replace("-", " "), {"valor": 0, "cor": "#95A5A6", "etiqueta": texto})
    return {"valor": 0, "cor": "#95A5A6", "etiqueta": texto or "Sen dato"}


def extraer_filas(html, dia_tab):
    soup = BeautifulSoup(html, "html.parser")
    filas = []
    tabla = (
        soup.select_one(f"#{dia_tab} table")
        or soup.select_one("table.table-irdi-table")
        or soup.select_one("table")
    )
    if not tabla:
        return filas
    for tr in tabla.select("tbody tr"):
        tds = tr.select("td")
        if len(tds) < 2:
            continue
        concello = limpar(tds[0].get_text(" ", strip=True))
        risco_txt = limpar(tds[1].get_text(" ", strip=True))
        clases = " ".join(tds[1].get("class", []) + tr.get("class", []))
        if not concello:
            continue
        info = clasificar_risco(risco_txt, clases)
        filas.append({
            "concello": concello,
            "concello_norm": normalizar(concello),
            "risco": info["etiqueta"],
            "risco_valor": info["valor"],
            "cor": info["cor"],
        })
    return filas


def scrape():
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    session = requests.Session()
    session.headers.update(HEADERS)
    resultado = {"dias": {}, "actualizacion": None}

    try:
        html = session.get(URL, timeout=30, verify=False).text
    except Exception as e:
        print(f"ERRO ao descargar a paxina: {e}", file=sys.stderr)
        return resultado

    soup = BeautifulSoup(html, "html.parser")

    data_el = soup.select_one(".data-modificacion, .data-actualizacion, time")
    if data_el:
        resultado["actualizacion"] = limpar(data_el.get_text(" ", strip=True))

    dias = []
    for a in soup.select("a[href^='#dia_']"):
        d = a.get("href", "").replace("#", "")
        if d and d not in dias:
            dias.append(d)
    if not dias:
        dias = ["dia_1", "dia_2", "dia_3", "dia_4"]

    for dia in dias:
        filas = extraer_filas(html, dia)
        if filas:
            resultado["dias"][dia] = filas

    if len(resultado["dias"]) <= 1:
        for i, dia in enumerate(dias):
            if dia in resultado["dias"]:
                continue
            for params in ({"dia": dia}, {"page": i}, {"dia": dia, "ajax": 1}):
                try:
                    r = session.get(URL, params=params, timeout=30, verify=False)
                    filas = extraer_filas(r.text, dia)
                    if filas:
                        resultado["dias"][dia] = filas
                        break
                except Exception:
                    continue
                time.sleep(0.5)

    return resultado


def cargar_concellos():
    if not CONCELLOS_GEOJSON.exists():
        print(f"AVISO: non existe {CONCELLOS_GEOJSON}", file=sys.stderr)
        return {}
    with open(CONCELLOS_GEOJSON, encoding="utf-8") as f:
        gj = json.load(f)
    indice = {}
    campos_nome = ["NAMEUNIT", "nome", "NOME", "NOMBRE", "name", "concello",
                   "CONCELLO", "rotulo", "ROTULO", "Texto", "txt_nombre"]
    for feat in gj.get("features", []):
        props = feat.get("properties", {})
        nome = None
        for c in campos_nome:
            if props.get(c):
                nome = props[c]
                break
        if not nome:
            continue
        indice[normalizar(nome)] = feat
    return indice


def xerar_geojson(filas, indice, dia_tab, meta):
    por_norm = {f["concello_norm"]: f for f in filas}
    features = []
    sen_xeometria = []
    for norm, feat in indice.items():
        datos = por_norm.get(norm)
        nova_props = dict(feat.get("properties", {}))
        if datos:
            nova_props.update({
                "concello": datos["concello"],
                "risco": datos["risco"],
                "risco_valor": datos["risco_valor"],
                "cor": datos["cor"],
            })
        else:
            nova_props.update({"risco": "Sen dato", "risco_valor": 0, "cor": "#95A5A6"})
        features.append({
            "type": "Feature",
            "geometry": feat.get("geometry"),
            "properties": nova_props,
        })
    nomes_indice = set(indice.keys())
    for f in filas:
        if f["concello_norm"] not in nomes_indice:
            sen_xeometria.append(f["concello"])
    if sen_xeometria:
        print(f"  [{dia_tab}] sen cruzar: {', '.join(sen_xeometria[:8])}", file=sys.stderr)
    return {
        "type": "FeatureCollection",
        "metadata": {
            "dia": dia_tab,
            "actualizacion": meta.get("actualizacion"),
            "xerado": datetime.now(timezone.utc).isoformat(),
            "fonte": "IRDI · Medio Rural · Xunta de Galicia",
            "total_concellos": len(features),
            "con_dato": sum(1 for x in features if x["properties"]["risco_valor"] > 0),
        },
        "features": features,
    }


def main():
    DATA_DIR.mkdir(exist_ok=True)
    print("Descargando IRDI de Medio Rural...")
    datos = scrape()

    if not datos["dias"]:
        print("Non se obtiveron datos do IRDI.", file=sys.stderr)
        sys.exit(1)

    print(f"  Dias obtidos: {', '.join(datos['dias'].keys())}")
    indice = cargar_concellos()
    print(f"  Concellos na capa municipal: {len(indice)}")

    estado = {
        "actualizacion_fonte": datos.get("actualizacion"),
        "xerado": datetime.now(timezone.utc).isoformat(),
        "dias_dispoñibles": [],
    }

    for dia, filas in datos["dias"].items():
        if indice:
            gj = xerar_geojson(filas, indice, dia, datos)
        else:
            gj = {
                "type": "FeatureCollection",
                "metadata": {"dia": dia, "aviso": "sen capa municipal"},
                "features": [],
                "taboa": filas,
            }
        saida = DATA_DIR / f"irdi_{dia}.geojson"
        with open(saida, "w", encoding="utf-8") as f:
            json.dump(gj, f, ensure_ascii=False)
        estado["dias_dispoñibles"].append(dia)
        print(f"  OK {saida.name} ({len(filas)} concellos)")

    with open(DATA_DIR / "irdi_meta.json", "w", encoding="utf-8") as f:
        json.dump(estado, f, ensure_ascii=False, indent=2)

    print("IRDI actualizado correctamente.")


if __name__ == "__main__":
    main()
