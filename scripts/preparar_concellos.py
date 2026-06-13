#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Descarga e prepara a capa municipal de Galicia desde o WFS do IGN.
Filtra os 313 concellos, simplifica a xeometría e garda en EPSG:4326.
"""

import json
import sys
import urllib.request
import urllib.parse
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
SAIDA = DATA_DIR / "concellos_galicia.geojson"

# WFS do IGN — servizo oficial, sen autenticación, CORS libre
WFS_URL = (
    "https://www.ign.es/wfs/unidades-administrativas"
    "?SERVICE=WFS&VERSION=2.0.0&REQUEST=GetFeature"
    "&TYPENAMES=unidadesAdministrativas:UnidadAdministrativa"
    "&CQL_FILTER=codNivelAdmin%3D%278%27"  # nivel 8 = municipio
    "&SRSNAME=EPSG:4326"
    "&OUTPUTFORMAT=application%2Fjson"
    "&count=400"
)

# Códigos INE de provincia de Galicia
PROVINCIAS = {"15", "27", "32", "36"}


def simplificar_coord(coords, tolerancia=0.002):
    """Simplificación Douglas-Peucker mínima para reducir peso."""
    if not coords or len(coords) <= 2:
        return coords
    # Versión simple: coger 1 de cada N puntos según tolerancia
    paso = max(1, int(len(coords) * tolerancia * 10))
    resultado = coords[::paso]
    if resultado[-1] != coords[-1]:
        resultado.append(coords[-1])
    return resultado


def simplificar_geometria(geom):
    if not geom:
        return geom
    tipo = geom.get("type", "")
    if tipo == "Polygon":
        return {"type": "Polygon", "coordinates": [simplificar_coord(r) for r in geom["coordinates"]]}
    if tipo == "MultiPolygon":
        return {"type": "MultiPolygon", "coordinates": [[simplificar_coord(r) for r in poly] for poly in geom["coordinates"]]}
    return geom


def main():
    DATA_DIR.mkdir(exist_ok=True)
    print("Descargando capa municipal do WFS do IGN...")

    try:
        req = urllib.request.Request(WFS_URL, headers={"User-Agent": "VOST-Galicia IRDI bot"})
        with urllib.request.urlopen(req, timeout=60) as resp:
            datos = json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        print(f"Erro descargando WFS IGN: {e}", file=sys.stderr)
        # Plan B: usar o endpoint ATOM do IGN para límites municipais
        try:
            print("Tentando fonte alternativa...")
            url_alt = "https://raw.githubusercontent.com/codeforgermany/click_that_hood/main/public/data/spain-comunidad.geojson"
            req2 = urllib.request.Request(url_alt, headers={"User-Agent": "VOST-Galicia"})
            with urllib.request.urlopen(req2, timeout=30) as r:
                datos = json.loads(r.read().decode("utf-8"))
        except Exception as e2:
            print(f"Tampouco a alternativa: {e2}", file=sys.stderr)
            sys.exit(1)

    total = len(datos.get("features", []))
    print(f"  Descargados {total} rexistros")

    # Filtrar Galicia
    galicia = []
    for feat in datos.get("features", []):
        props = feat.get("properties", {})
        # Buscar código de provincia en varios campos posibles
        cod = str(props.get("codProvincia", props.get("codMunicipio", props.get("NATCODE", props.get("id", ""))))).zfill(5)
        prov = cod[:2] if len(cod) >= 2 else ""
        if prov in PROVINCIAS:
            # Normalizar propiedades
            nome = props.get("nameUnit", props.get("nombre", props.get("name", "")))
            nova_feat = {
                "type": "Feature",
                "geometry": simplificar_geometria(feat.get("geometry")),
                "properties": {
                    "NAMEUNIT": nome,
                    "codMunicipio": cod,
                    "provincia": prov,
                }
            }
            galicia.append(nova_feat)

    if not galicia:
        # Se non filtramos nada, gardar todos e aceptar que o cruce irá por nome
        print("Non se puido filtrar por provincia, gardando todos os rexistros", file=sys.stderr)
        galicia = datos.get("features", [])

    gj = {"type": "FeatureCollection", "features": galicia}
    with open(SAIDA, "w", encoding="utf-8") as f:
        json.dump(gj, f, ensure_ascii=False)

    tamano = SAIDA.stat().st_size / 1024
    print(f"Gardados {len(galicia)} concellos en {SAIDA.name} ({tamano:.0f} KB)")


if __name__ == "__main__":
    main()
