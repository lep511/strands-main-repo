#!/usr/bin/env python3
"""
process.py — Procesador de datos de ventas
Ejecutado por el agente Strands mediante la skill 'procesar-ventas'
"""

import json
import sys
import csv
import statistics
from pathlib import Path
from datetime import datetime


def load_data(filepath: str) -> list[dict]:
    """Carga datos desde CSV o JSON."""
    path = Path(filepath)

    if not path.exists():
        print(json.dumps({"error": f"Archivo no encontrado: {filepath}"}))
        sys.exit(1)

    if path.suffix == ".json":
        with open(path) as f:
            data = json.load(f)
        # Acepta tanto lista directa como {"ventas": [...]}
        return data if isinstance(data, list) else data.get("ventas", [])

    elif path.suffix == ".csv":
        rows = []
        with open(path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                rows.append({
                    "mes":    row.get("mes", ""),
                    "monto":  float(row.get("monto", 0)),
                    "region": row.get("region", "Sin región"),
                })
        return rows

    else:
        print(json.dumps({"error": f"Formato no soportado: {path.suffix}"}))
        sys.exit(1)


def analyze(ventas: list[dict]) -> dict:
    """Calcula métricas sobre la lista de ventas."""
    montos = [v["monto"] for v in ventas]

    por_region: dict[str, list[float]] = {}
    for v in ventas:
        por_region.setdefault(v["region"], []).append(v["monto"])

    mejor_mes = max(ventas, key=lambda v: v["monto"])
    peor_mes  = min(ventas, key=lambda v: v["monto"])

    return {
        "resumen": {
            "total_registros": len(ventas),
            "total_ventas":    round(sum(montos), 2),
            "promedio":        round(statistics.mean(montos), 2),
            "mediana":         round(statistics.median(montos), 2),
            "maximo":          round(max(montos), 2),
            "minimo":          round(min(montos), 2),
            "desv_estandar":   round(statistics.stdev(montos), 2) if len(montos) > 1 else 0,
        },
        "mejor_mes": mejor_mes,
        "peor_mes":  peor_mes,
        "por_region": {
            region: {
                "total":    round(sum(montos_r), 2),
                "promedio": round(statistics.mean(montos_r), 2),
            }
            for region, montos_r in por_region.items()
        },
        "tendencia": "📈 Creciente" if montos[-1] > montos[0] else "📉 Decreciente",
        "generado_en": datetime.now().isoformat(),
    }


def main():
    if len(sys.argv) < 2:
        print(json.dumps({"error": "Uso: python process.py <ruta_al_archivo>"}))
        sys.exit(1)

    filepath = sys.argv[1]
    ventas = load_data(filepath)

    if not ventas:
        print(json.dumps({"error": "No se encontraron datos de ventas"}))
        sys.exit(1)

    resultado = analyze(ventas)
    print(json.dumps(resultado, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()