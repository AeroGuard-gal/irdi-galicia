#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Preparar capa municipal de Galicia
==================================
Descarga os límites municipais de España do CNIG (ou unha fonte alternativa),
filtra os 313 concellos de Galicia (provincias 15, 27, 32, 36), simplifica a
xeometría para web e garda data/concellos_galicia.geojson en EPSG:4326.

Execútase UNHA VEZ (ou cando se queira actualizar a capa base).
Require: geopandas, requests.

Se a descarga automática falla, pódese substituír o ficheiro
data/concellos_galicia.geojson manualmente (exportado desde QGIS en 4326).
"""

import sys
import zipfile
import io
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
SAIDA = DATA_DIR / "concellos_galicia.geojson"

# Provincias galegas (códigos INE de provincia)
PROVINCIAS_GALICIA = {"15", "27", "32", "36"}  # A Coruña, Lugo, Ourense, Pontevedra

# Fonte recomendada: límites municipais do IGN/CNIG (descarga directa de exemplo).
# O CNIG serve as liñas límite; aquí usamos unha fonte aberta espello en formato
# axeitado. Pódese cambiar pola URL oficial do Centro de Descargas do CNIG.
FONTES = [
    # GeoJSON de municipios de España (mantido pola comunidade, datos IGN)
    "https://raw.githubusercontent.com/inigoflores/ds-codigos-postales-meta/master/data/municipios.geojson",
]


def main():
    try:
        import geopandas as gpd
    except ImportError:
        print("✗ Falta geopandas. Instálase no workflow.", file=sys.stderr)
        sys.exit(1)

    import requests

    DATA_DIR.mkdir(exist_ok=True)

    gdf = None
    for url in FONTES:
        try:
            print(f"➤ Descargando capa municipal: {url}")
            gdf = gpd.read_file(url)
            print(f"  Cargados {len(gdf)} rexistros")
            break
        except Exception as e:
            print(f"  ✗ Fallou: {e}", file=sys.stderr)
            continue

    if gdf is None:
        print("✗ Non se puido descargar a capa municipal de ningunha fonte.",
              file=sys.stderr)
        print("  Sube manualmente data/concellos_galicia.geojson (EPSG:4326).",
              file=sys.stderr)
        sys.exit(1)

    # Detectar campo de código INE
    campos = {c.upper(): c for c in gdf.columns}
    cod_campo = None
    for posible in ("COD_INE", "CODIGOINE", "CMUN", "NATCODE", "INE", "COD_MUN",
                    "CODE", "ID", "CODIGO"):
        if posible in campos:
            cod_campo = campos[posible]
            break

    # Filtrar Galicia pola provincia (2 primeiros díxitos do código INE)
    if cod_campo:
        def es_galicia(v):
            s = str(v).zfill(5)
            return s[:2] in PROVINCIAS_GALICIA
        gdf_gal = gdf[gdf[cod_campo].apply(es_galicia)].copy()
        print(f"  Filtrados {len(gdf_gal)} concellos de Galicia por código INE")
    else:
        # Sen código: tentar por nome de provincia/comunidade
        col_ca = None
        for posible in ("acom_name", "CCAA", "comunidad", "autonomia"):
            if posible in gdf.columns:
                col_ca = posible
                break
        if col_ca:
            gdf_gal = gdf[gdf[col_ca].astype(str).str.contains("alic", case=False, na=False)].copy()
            print(f"  Filtrados {len(gdf_gal)} concellos de Galicia por nome de CA")
        else:
            print("  ⚠️ Non se atopou campo de código nin de CA; gárdase todo.",
                  file=sys.stderr)
            gdf_gal = gdf

    # Pasar a EPSG:4326 (lon/lat) para Leaflet
    if gdf_gal.crs and gdf_gal.crs.to_epsg() != 4326:
        gdf_gal = gdf_gal.to_crs(4326)

    # Simplificar xeometría para aliviar peso (tolerancia en graos ~ 50 m)
    gdf_gal["geometry"] = gdf_gal.geometry.simplify(0.0005, preserve_topology=True)

    gdf_gal.to_file(SAIDA, driver="GeoJSON")
    tamano = SAIDA.stat().st_size / 1024
    print(f"✓ Gardado {SAIDA.name} · {len(gdf_gal)} concellos · {tamano:.0f} KB")


if __name__ == "__main__":
    main()
