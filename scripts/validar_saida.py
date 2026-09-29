#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
EXPECTED_DAYS = ["dia_1", "dia_2", "dia_3", "dia_4"]
EXPECTED_MUNICIPALITIES = 313
MIN_WITH_DATA = 300


def fail(msg: str) -> None:
    print(f"ERRO: {msg}", file=sys.stderr)
    raise SystemExit(1)


def main() -> None:
    meta_path = DATA_DIR / "irdi_meta.json"
    if not meta_path.exists():
        fail("falta data/irdi_meta.json")

    with meta_path.open(encoding="utf-8") as f:
        meta = json.load(f)

    available = meta.get("dias_disponibles", [])
    if available != EXPECTED_DAYS:
        fail(f"días dispoñibles inesperados: {available!r}; esperados {EXPECTED_DAYS!r}")

    for day in EXPECTED_DAYS:
        path = DATA_DIR / f"irdi_{day}.geojson"
        if not path.exists():
            fail(f"falta {path.name}")

        with path.open(encoding="utf-8") as f:
            gj = json.load(f)

        features = gj.get("features", [])
        if len(features) != EXPECTED_MUNICIPALITIES:
            fail(f"{path.name}: {len(features)} concellos; esperados {EXPECTED_MUNICIPALITIES}")

        with_data = sum(
            1 for feat in features
            if int((feat.get("properties") or {}).get("risco_valor") or 0) > 0
        )
        if with_data < MIN_WITH_DATA:
            fail(f"{path.name}: só {with_data} concellos con dato; mínimo {MIN_WITH_DATA}")

        print(f"✓ {path.name}: {len(features)} concellos, {with_data} con dato")

    print("✓ Saída IRDI validada correctamente")


if __name__ == "__main__":
    main()
