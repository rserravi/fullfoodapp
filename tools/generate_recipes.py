#!/usr/bin/env python3
from __future__ import annotations
import argparse, random, textwrap
from pathlib import Path
from typing import List

random.seed(42)

VEG = ["calabacín","berenjena","pimiento rojo","pimiento verde","zanahoria","brócoli","coliflor","champiñón","espinaca","kale","cebolla"]
PROT = ["pechuga de pollo","muslos de pollo","tofu firme","tempeh","lomo de cerdo","salmón","merluza","garbanzos cocidos","alubias blancas","huevo"]
STARCH = ["arroz basmati","pasta corta","espagueti","cuscús","quinoa","patata"]
SAUCE = ["salsa de soja","tomate triturado","nata para cocinar","leche de coco","pesto clásico","salsa teriyaki","salsa barbacoa"]
HERBS = ["albahaca","orégano","perejil","cilantro","romero","tomillo"]

# Conjunto de electrodomésticos soportados (incluye microondas)
APPLIANCE_SETS = [
    ["sartén"],
    ["airfryer"],
    ["horno"],
    ["robot"],
    ["sartén","airfryer"],
    ["microondas"],               # cocción normal / vapor
    ["microondas","grill"],       # micro + acabado grill
]

TEMPLATES = [
    ("Salteado de {veg1} y {veg2} con {prot}", ["sartén"]),
    ("Bandeja al horno de {veg1}, {veg2} y {prot}", ["horno"]),
    ("Bowl de {starch} con {prot}, {veg1} y {sauce}", ["sartén"]),
    ("Airfryer: {prot} con {veg1} y especias", ["airfryer"]),
    ("Curry rápido de {prot} con {veg1} y {sauce}", ["sartén","robot"]),
    ("Pasta con {sauce} y {veg1}", ["sartén"]),
    # Nuevas orientadas a microondas
    ("Microondas: verduras al vapor con {prot}", ["microondas"]),
    ("Microondas (grill): gratinado exprés de {prot} con {sauce}", ["microondas","grill"]),
    ("Arroz rápido en microondas con {prot} y {veg1}", ["microondas"]),
]

def pick2(lst: List[str]) -> tuple[str,str]:
    a, b = random.sample(lst, 2)
    return a, b

def build_steps(title: str, appliances: List[str], ingredients: List[str]) -> List[str]:
    base: List[str] = []
    # Preparación común
    prep_vegs = [i for i in ingredients if i in VEG]
    if prep_vegs:
        base.append(f"Preparar los ingredientes: cortar {', '.join(prep_vegs)} en dados; salar ligeramente.")
    else:
        base.append("Preparar los ingredientes y tener todo a mano; salar al gusto.")
    # Instrucciones específicas por aparato
    if "sartén" in appliances:
        base.append("Calentar 1 cda de aceite en sartén amplia a fuego medio-alto.")
        base.append("Saltear verduras 8–10 min; añadir proteína y cocinar 5–7 min más.")
    if "airfryer" in appliances:
        base.append("Precalentar airfryer 3 min a 190 °C; cocinar piezas 12–15 min, dar la vuelta a mitad.")
    if "horno" in appliances:
        base.append("Horno a 200 °C; disponer en bandeja y asar 22–28 min, mover a mitad.")
    if "robot" in appliances:
        base.append("Si se usa robot: cocción 20 min · 100 °C · vel media; al final triturar si procede.")
    if "microondas" in appliances:
        # Paso de descongelado opcional para ingredientes congelados
        base.append("Si algún ingrediente está congelado: descongelar en microondas al 30% de potencia 5–8 min, girando a mitad; reposar 2–3 min.")
        # Cocción vapor / normal
        if any(s in ingredients for s in ["arroz basmati","quinoa","cuscús"]):
            base.append("Cocer cereal en microondas: recipiente apto, líquido al doble de volumen, 800 W · 10–12 min; reposo 5 min tapado.")
        else:
            base.append("Cocer al vapor en microondas: 800 W · 4–6 min (verduras 250–300 g), remover a mitad; reposo 1–2 min.")
        # Grill si está disponible
        if "grill" in appliances:
            base.append("Acabado grill: gratinar 3–5 min hasta dorar la superficie (vigilar).")
    # Acabado
    base.append("Ajustar con hierbas/especias al gusto y servir caliente.")
    return base

def mk_md(title: str, portions: int, appliances: List[str], ingredients: List[str], steps: List[str], tags: List[str]) -> str:
    fm = textwrap.dedent(f"""\
    ---
    title: {title}
    lang: es
    portions: {portions}
    appliances: [{", ".join(appliances)}]
    tags: [{", ".join(tags)}]
    license: CC-BY-4.0
    source: synthetic
    ---
    """)
    ings = "\n".join([f"- {i}" for i in ingredients])
    stps = "\n".join([f"{idx+1}. {s}" for idx, s in enumerate(steps)])
    body = f"""
## Ingredientes
{ings}

## Pasos
{stps}
"""
    return fm + body.strip() + "\n"

def generate_one() -> tuple[str, str]:
    tpl, forced_appl = random.choice(TEMPLATES)
    veg1, veg2 = pick2(VEG)
    prot = random.choice(PROT)
    starch = random.choice(STARCH)
    sauce = random.choice(SAUCE)
    herbs = random.sample(HERBS, k=2)
    appliances = forced_appl if forced_appl else random.choice(APPLIANCE_SETS)
    title = tpl.format(veg1=veg1, veg2=veg2, prot=prot, starch=starch, sauce=sauce)
    # Lista de ingredientes base
    ingredients = [veg1, veg2, prot, random.choice(STARCH), random.choice(SAUCE), "aceite de oliva", "sal fina", "pimienta negra"] + herbs
    steps = build_steps(title, appliances, ingredients)
    tags = ["rápido","semana","económico"]
    md = mk_md(title, portions=random.choice([2,3,4]), appliances=appliances, ingredients=ingredients, steps=steps, tags=tags)
    # Slug simple sin tildes/espacios
    slug = (title.lower()
            .replace(" ", "_")
            .replace(":", "")
            .replace(",", "")
            .replace("á","a").replace("é","e").replace("í","i").replace("ó","o").replace("ú","u").replace("ñ","n")
            )
    return slug, md

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=str, default="data/generated_recipes", help="Directorio de salida")
    ap.add_argument("--count", type=int, default=200, help="Número de recetas a generar")
    args = ap.parse_args()

    outdir = Path(args.out)
    outdir.mkdir(parents=True, exist_ok=True)

    seen = set()
    n = 0
    while n < args.count:
        slug, md = generate_one()
        if slug in seen:
            continue
        seen.add(slug)
        (outdir / f"{slug}.md").write_text(md, encoding="utf-8")
        n += 1
    print(f"Generadas {n} recetas en {outdir}")

if __name__ == "__main__":
    main()
