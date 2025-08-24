from __future__ import annotations
from typing import List, Dict
from fastapi import APIRouter, Depends
from sqlmodel import Session
from ..db import get_session
from ..models_db import Product
from ..security import get_current_user
from ..schemas import Document, IngestRequest
from ..embeddings import embed_dual
from ..vectorstore import upsert_documents

router = APIRouter(prefix="/admin", tags=["admin"])

BASE_SEED = [
    ("calabacín", "verduras", ["zucchini"]),
    ("pimiento", "verduras", []),
    ("cebolla", "verduras", []),
    ("aceite de oliva", "aceites/vinagres", ["aceite"]),
    ("pasta", "cereales/pastas", ["espagueti", "macarrón"]),
    ("leche", "lácteos", []),
    ("huevo", "huevos", ["huevos"]),
]

@router.post("/seed-catalog")
def seed_catalog(
    session: Session = Depends(get_session),
    user_id: str = Depends(get_current_user),
):
    for name, cat, syn in BASE_SEED:
        exists = session.exec(
            Product.select().where(Product.user_id == user_id, Product.name == name)
        ).first()
        if exists:
            continue
        session.add(Product(user_id=user_id, name=name, category=cat, synonyms=syn, is_global=False))
    session.commit()
    return {"ok": True, "count": len(BASE_SEED)}

@router.post("/seed-rag")
async def seed_rag(
    session: Session = Depends(get_session),
    user_id: str = Depends(get_current_user),
):
    texts = [
        "Pesto clásico: albahaca, piñones, parmesano, aceite de oliva, ajo. Mezclar y usar con pasta.",
        "Salteado de calabacín y pimiento: cortar en dados, saltear con aceite y sal, 8-10 minutos."
    ]
    payloads = [{"source":"seed","user_id":user_id},{"source":"seed","user_id":user_id}]
    embs = await embed_dual(texts)
    await upsert_documents(texts, payloads, embs)
    return {"ok": True, "ingested": len(texts)}
