from __future__ import annotations
from typing import List, Dict, Optional, Tuple
from sqlmodel import Session, select
from ..models_db import Product

# Categorías base recomendadas
BASE_CATEGORIES = [
    "verduras", "frutas", "lácteos", "huevos", "carnes", "pescado",
    "legumbres", "cereales/pastas", "panadería", "conservas",
    "especias/salsas", "aceites/vinagres", "dulces", "bebidas", "limpieza", "otros",
]

# Heurísticas simples por palabra clave
HEURISTICS: Dict[str, List[str]] = {
    "verduras": ["calabacín", "pimiento", "cebolla", "zanahoria", "lechuga", "tomate", "pepino", "ajo", "berenjena"],
    "frutas": ["manzana", "plátano", "pera", "naranja", "limón", "fresa", "melón", "sandía", "uva"],
    "lácteos": ["leche", "yogur", "queso", "mantequilla", "nata"],
    "huevos": ["huevo", "huevos"],
    "carnes": ["pollo", "ternera", "cerdo", "pavo", "cordero"],
    "pescado": ["salmón", "merluza", "atún", "bacalao", "gamba", "gambas"],
    "legumbres": ["garbanzo", "lenteja", "alubia", "judía"],
    "cereales/pastas": ["pasta", "arroz", "espagueti", "macarrón", "cuscús", "quinoa"],
    "panadería": ["pan", "harina", "levadura"],
    "conservas": ["atún en lata", "tomate frito", "maíz en lata"],
    "especias/salsas": ["sal", "pimienta", "pimentón", "comino", "curry", "ketchup", "mostaza", "mayonesa", "salsa"],
    "aceites/vinagres": ["aceite", "vinagre"],
    "dulces": ["azúcar", "chocolate", "galleta", "miel", "mermelada"],
    "bebidas": ["agua", "zumo", "refresco"],
    "limpieza": ["lavavajillas", "lejía", "detergente"],
}

def _norm(s: str) -> str:
    return " ".join(s.strip().lower().split())

def load_catalog(session: Session, user_id: str) -> List[Product]:
    # Trae catálogo del usuario + global
    rows = session.exec(
        select(Product).where((Product.user_id == user_id) | (Product.is_global == True))
    ).all()
    return rows

def best_category_for(name: str, catalog: List[Product]) -> Optional[str]:
    n = _norm(name)
    # 1) Exact match en catálogo
    for p in catalog:
        if _norm(p.name) == n:
            return p.category or "otros"
        # sinónimos
        if p.synonyms:
            for syn in p.synonyms:
                if _norm(str(syn)) == n:
                    return p.category or "otros"
    # 2) Heurística simple
    for cat, words in HEURISTICS.items():
        for w in words:
            if _norm(w) in n:
                return cat
    return "otros"

def categorize_names(session: Session, user_id: str, names: List[str]) -> Dict[str, str]:
    cat = load_catalog(session, user_id)
    out: Dict[str, str] = {}
    for name in names:
        out[name] = best_category_for(name, cat)
    return out
