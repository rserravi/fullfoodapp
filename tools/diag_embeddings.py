#!/usr/bin/env python3
from __future__ import annotations
import asyncio
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from api.config import settings
from api.embeddings import embed_dual

TEXTS = [
    "pasta con salsa de albahaca y parmesano",
    "salteado de verduras en sartén",
    "microondas: arroz rápido y verduras"
]

async def main():
    models = settings.parsed_embedding_models()
    dims = settings.parsed_vector_dims()
    print("Modelos:", models)
    print("Dims esperadas:", dims)
    embs = await embed_dual(TEXTS, models=models)
    for k, vecs in embs.items():
        ok = all(isinstance(v, list) and len(v) == dims[k] for v in vecs)
        lens = [len(v) if isinstance(v, list) else -1 for v in vecs]
        print(f"- {k}: tamaños {lens} → {'OK' if ok else 'FAIL'}")
    print("Listo.")

if __name__ == "__main__":
    asyncio.run(main())
