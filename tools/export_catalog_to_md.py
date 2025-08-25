#!/usr/bin/env python3
from __future__ import annotations
import json, argparse
from pathlib import Path

TEMPLATE = """---
title: Catálogo de productos por categoría
lang: es
tags: [catalogo, categorias]
source: local
---

> **Nota:** Electrodomésticos soportados por el planificador: **sartén/placa**, **horno**, **airfryer**, **robot de cocina** y **microondas** (modo normal, **descongelado** y **grill**).

{body}
"""

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--products", default="data/catalog/products_es.json")
    ap.add_argument("--synonyms", default="data/catalog/synonyms_extra_es.json")
    ap.add_argument("--outdir", default="data/knowledge")
    args = ap.parse_args()

    products = json.loads(Path(args.products).read_text(encoding="utf-8"))
    syn = json.loads(Path(args.synonyms).read_text(encoding="utf-8")) if Path(args.synonyms).exists() else {}

    # Agrupar por categoría
    by_cat = {}
    for p in products:
        by_cat.setdefault(p["category"], []).append(p)

    lines = []
    for cat in sorted(by_cat.keys()):
        lines.append(f"## {cat}\n")
        for p in sorted(by_cat[cat], key=lambda x: x["name"]):
            s = p.get("synonyms", [])
            extra = syn.get(p["name"], [])
            allsyn = list(dict.fromkeys(s + extra))
            syn_str = f" _(sinónimos: {', '.join(allsyn)})_" if allsyn else ""
            lines.append(f"- **{p['name']}**{syn_str}")
        lines.append("")

    body = "\n".join(lines).strip()
    outdir = Path(args.outdir); outdir.mkdir(parents=True, exist_ok=True)
    (outdir / "catalogo_por_categoria.md").write_text(TEMPLATE.format(body=body), encoding="utf-8")
    print("Escrito data/knowledge/catalogo_por_categoria.md")

if __name__ == "__main__":
    main()
