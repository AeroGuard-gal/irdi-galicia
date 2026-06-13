#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Actualizar IRDI · Índice de Risco Diario de Incendios de Galicia
Fonte: https://mediorural.xunta.gal/es/temas/defensa-monte/irdi
"""

import json, re, sys, time, unicodedata
from datetime import datetime, timezone
from pathlib import Path
from bs4 import BeautifulSoup
import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

BASE = "https://mediorural.xunta.gal"
URL  = f"{BASE}/es/temas/defensa-monte/irdi"
AJAX = f"{BASE}/es/views/ajax"

DATA_DIR          = Path(__file__).resolve().parent.parent / "data"
CONCELLOS_GEOJSON = DATA_DIR / "concellos_galicia.geojson"

NIVEIS = {
    "baixo":    {"valor": 1, "cor": "#0033CC", "etiqueta": "Baixo"},
    "bajo":     {"valor": 1, "cor": "#0033CC", "etiqueta": "Baixo"},
    "moderado": {"valor": 2, "cor": "#33CC00", "etiqueta": "Moderado"},
    "alto":     {"valor": 3, "cor": "#FFCC00", "etiqueta": "Alto"},
    "moi alto": {"valor": 4, "cor": "#FF6600", "etiqueta": "Moi alto"},
    "muy alto": {"valor": 4, "cor": "#FF6600", "etiqueta": "Moi alto"},
    "extremo":  {"valor": 5, "cor": "#CC0000", "etiqueta": "Extremo"},
}

HEADERS_NAV = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Accept-Language": "gl,es;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

EQUIVALENCIAS = {
    "ALFOZ":              "ALFOZ DO CASTRODOURO",
    "CANGAS":             "CANGAS DE MORRAZO",
    "CASTRO CALDELAS":    "CASTRO DE CALDELAS",
    "CERDEDO-COTOBADE":   "CERDEDO COTOBADE",
    "MONDARIZ-BALNEARIO": "MONDARIZ BALNEARIO",
    "OZA-CESURAS":        "OZA CESURAS",
}


def limpar(txt):
    return re.sub(r"\s+", " ", (txt or "")).strip()

def normalizar(nome):
    if not nome: return ""
    s = unicodedata.normalize("NFKD", nome)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"^(O|A|AS|OS)\s+", "", s.upper().strip())
    s = re.sub(r"\s*\((O|A|AS|OS)\)$", "", s)
    return s.strip()

def normalizar_risco(texto):
    s = unicodedata.normalize("NFKD", texto or "")
    return "".join(c for c in s if not unicodedata.combining(c)).lower().strip()

def clasificar(texto, clases=""):
    t = normalizar_risco(texto)
    if t in NIVEIS: return NIVEIS[t]
    for chave in ("extremo","moi-alto","muy-alto","alto","moderado","baixo","bajo"):
        if f"irdi-{chave}" in clases.lower():
            return NIVEIS.get(chave.replace("-"," "), {"valor":0,"cor":"#95A5A6","etiqueta":texto})
    return {"valor":0,"cor":"#95A5A6","etiqueta":texto or "Sen dato"}

def extraer_filas(html, dia_tab):
    soup = BeautifulSoup(html, "html.parser")
    filas = []
    tabla = (soup.select_one(f"#{dia_tab} table")
             or soup.select_one("table.table-irdi-table")
             or soup.select_one("table"))
    if not tabla: return filas
    for tr in tabla.select("tbody tr"):
        tds = tr.select("td")
        if len(tds) < 2: continue
        concello = limpar(tds[0].get_text(" ", strip=True))
        risco_txt = limpar(tds[1].get_text(" ", strip=True))
        clases = " ".join(tds[1].get("class",[]) + tr.get("class",[]))
        if not concello: continue
        info = clasificar(risco_txt, clases)
        norm = normalizar(concello)
        filas.append({
            "concello": concello,
            "concello_norm": EQUIVALENCIAS.get(norm, norm),
            "risco": info["etiqueta"],
            "risco_valor": info["valor"],
            "cor": info["cor"],
        })
    return filas

def extraer_paginado(session, html_inicial, dia_tab):
    """Extrae todas as páxinas dunha pestana por paxinación ?page=N."""
    filas_dia = []
    for page in range(0, 20):
        if page == 0:
            html = html_inicial
        else:
            try:
                r = session.get(URL, params={"page": page}, timeout=30, verify=False)
                html = r.text
            except Exception:
                break
        filas = extraer_filas(html, dia_tab)
        if not filas: break
        filas_dia.extend(filas)
        print(f"  {dia_tab} pax {page}: {len(filas)} concellos")
        if len(filas) < 50: break
        time.sleep(0.3)
    return filas_dia

def extraer_ajax(session, dia_tab, dom_id):
    """Usa o endpoint AJAX de Drupal Views para cargar una pestana."""
    filas_dia = []
    nomes_vistos = set()  # Para detectar cando o servidor repite datos
    for page in range(0, 20):
        params = {
            "view_name": "tabla_irdi",
            "view_display_id": "block_1",
            "view_args": dia_tab,
            "view_path": "/node/1161",
            "view_base_path": "",
            "view_dom_id": dom_id,
            "pager_element": "0",
            "_drupal_ajax": "1",
            "ajax_page_state[theme]": "w_pormrm_bootstrap",
            "ajax_page_state[theme_token]": "",
            "ajax_page_state[libraries]": "",
        }
        try:
            # En Drupal Views AJAX, o número de páxina vai como parámetro GET na URL
            ajax_url = f"{AJAX}?page={page}" if page > 0 else AJAX
            r = session.post(
                ajax_url,
                data=params,
                headers={
                    "X-Requested-With": "XMLHttpRequest",
                    "Accept": "application/json, text/javascript, */*",
                    "Referer": URL,
                    "Content-Type": "application/x-www-form-urlencoded",
                },
                timeout=30,
                verify=False
            )
            data = r.json()
            html_frag = ""
            for cmd in data:
                if isinstance(cmd, dict) and cmd.get("command") == "insert":
                    html_frag += cmd.get("data", "")
            filas = extraer_filas(f"<div id='{dia_tab}'>{html_frag}</div>", dia_tab)
            if not filas:
                filas = extraer_filas(html_frag, dia_tab)
            if not filas:
                break
            # Detectar páxina repetida (o servidor segue devolvendo a última páxina)
            nomes_pax = frozenset(f["concello"] for f in filas)
            if nomes_pax in nomes_vistos:
                print(f"  {dia_tab} AJAX pax {page}: datos repetidos, parando")
                break
            nomes_vistos.add(nomes_pax)
            filas_dia.extend(filas)
            print(f"  {dia_tab} AJAX pax {page}: {len(filas)} concellos")
            if len(filas) < 50:
                break
            time.sleep(0.3)
        except Exception as e:
            print(f"  {dia_tab} AJAX pax {page} erro: {e}", file=sys.stderr)
            break
    return filas_dia


def scrape():
    session = requests.Session()
    session.headers.update(HEADERS_NAV)
    resultado = {"dias": {}, "actualizacion": None}

    # 1. Cargar a páxina principal (dia_1 + cookies de sesión)
    try:
        r = session.get(URL, timeout=30, verify=False)
        html = r.text
    except Exception as e:
        print(f"ERRO: {e}", file=sys.stderr)
        return resultado

    soup = BeautifulSoup(html, "html.parser")

    # Data de actualización
    data_el = soup.select_one(".data-modificacion")
    if data_el:
        resultado["actualizacion"] = limpar(data_el.get_text(" ", strip=True))

    # Detectar días e DOM ID
    dias = []
    for a in soup.select("ul.table-irdi a[href^='#dia_']"):
        d = a.get("href","").replace("#","")
        if d and d not in dias: dias.append(d)
    if not dias: dias = ["dia_1","dia_2","dia_3","dia_4"]

    # Extraer DOM ID para AJAX
    dom_id = ""
    settings_m = re.search(r'data-drupal-selector="drupal-settings-json">({.*?})</script>', html, re.DOTALL)
    if settings_m:
        try:
            s = json.loads(settings_m.group(1))
            ajax_views = s.get("views",{}).get("ajaxViews",{})
            if ajax_views: dom_id = list(ajax_views.keys())[0]
        except: pass

    # 2. Dia 1 por paxinación normal (xa está no HTML)
    filas_d1 = extraer_paginado(session, html, "dia_1")
    if filas_d1:
        resultado["dias"]["dia_1"] = filas_d1
        print(f"  dia_1 TOTAL: {len(filas_d1)} concellos")

    # 3. Días 2,3,4 por AJAX (non están no HTML inicial)
    for dia in [d for d in dias if d != "dia_1"]:
        filas = []
        if dom_id:
            filas = extraer_ajax(session, dia, dom_id)
        # Sen AJAX non hai datos reais para este día
        if not filas:
            print(f"  {dia}: sen datos AJAX, día omitido", file=sys.stderr)
        if filas:
            resultado["dias"][dia] = filas
            print(f"  {dia} TOTAL: {len(filas)} concellos")
        time.sleep(0.5)

    return resultado


def cargar_concellos():
    if not CONCELLOS_GEOJSON.exists():
        print(f"AVISO: non existe {CONCELLOS_GEOJSON}", file=sys.stderr)
        return {}
    with open(CONCELLOS_GEOJSON, encoding="utf-8") as f:
        gj = json.load(f)
    indice = {}
    campos = ["NAMEUNIT","CONCELLO","nome","NOME","NOMBRE","name","concello","CONCELLO","rotulo"]
    for feat in gj.get("features",[]):
        props = feat.get("properties",{})
        nome = next((props[c] for c in campos if props.get(c)), None)
        if nome: indice[normalizar(nome)] = feat
    return indice


def xerar_geojson(filas, indice, dia_tab, meta):
    por_norm = {f["concello_norm"]: f for f in filas}
    features = []
    sen_cruzar = []
    for norm, feat in indice.items():
        datos = por_norm.get(norm)
        nova = dict(feat.get("properties",{}))
        if datos:
            nova.update({"concello":datos["concello"],"risco":datos["risco"],
                         "risco_valor":datos["risco_valor"],"cor":datos["cor"]})
        else:
            nova.update({"risco":"Sen dato","risco_valor":0,"cor":"#95A5A6"})
        features.append({"type":"Feature","geometry":feat.get("geometry"),"properties":nova})
    for f in filas:
        if f["concello_norm"] not in indice:
            sen_cruzar.append(f["concello"])
    if sen_cruzar:
        print(f"  [{dia_tab}] sen cruzar: {', '.join(sen_cruzar[:8])}", file=sys.stderr)
    return {
        "type":"FeatureCollection",
        "metadata":{
            "dia":dia_tab,"actualizacion":meta.get("actualizacion"),
            "xerado":datetime.now(timezone.utc).isoformat(),
            "fonte":"IRDI · Medio Rural · Xunta de Galicia",
            "total_concellos":len(features),
            "con_dato":sum(1 for x in features if x["properties"]["risco_valor"]>0),
        },
        "features":features,
    }


def main():
    DATA_DIR.mkdir(exist_ok=True)
    print("Descargando IRDI de Medio Rural...")
    datos = scrape()
    if not datos["dias"]:
        print("Non se obtiveron datos.", file=sys.stderr); sys.exit(1)

    print(f"Dias obtidos: {', '.join(datos['dias'].keys())}")
    indice = cargar_concellos()
    print(f"Concellos na capa municipal: {len(indice)}")

    estado = {"actualizacion_fonte":datos.get("actualizacion"),
              "xerado":datetime.now(timezone.utc).isoformat(),"dias_disponibles":[]}

    for dia, filas in dados["dias"].items() if False else datos["dias"].items():
        gj = xerar_geojson(filas, indice, dia, datos) if indice else {
            "type":"FeatureCollection","metadata":{"dia":dia,"aviso":"sen capa municipal"},
            "features":[],"taboa":filas}
        saida = DATA_DIR / f"irdi_{dia}.geojson"
        with open(saida,"w",encoding="utf-8") as f:
            json.dump(gj,f,ensure_ascii=False)
        estado["dias_disponibles"].append(dia)
        print(f"OK {saida.name} ({len(filas)} concellos)")

    with open(DATA_DIR/"irdi_meta.json","w",encoding="utf-8") as f:
        json.dump(estado,f,ensure_ascii=False,indent=2)
    print("IRDI actualizado correctamente.")

if __name__ == "__main__":
    main()
