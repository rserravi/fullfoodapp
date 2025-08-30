#!/usr/bin/env python3
from __future__ import annotations
import argparse
import asyncio
import json
from pathlib import Path
from typing import List, Dict, Any
import unicodedata
import re
import sys

# Asegura que el repo raíz está en sys.path aunque no se exporte PYTHONPATH=.
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from api.config import settings
from api.vectorstore import upsert_documents
from api.embeddings import embed_dual
from api.utils.markdown import parse_markdown_with_frontmatter
from api.utils.chunk import split_into_chunks
from qdrant_client import QdrantClient
from qdrant_client.models import VectorParams, Distance

def slugify(s: str) -> str:
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    s = re.sub(r"[^a-zA-Z0-9]+", "-", s).strip("-").lower()
    return s or "doc"

def discover_files(root: Path) -> List[Path]:
    return [p for p in root.rglob("*") if p.suffix.lower() in {".md", ".txt", ".json"} and p.is_file()]

def parse_file(path: Path) -> List[Dict[str, Any]]:
    """
    Devuelve lista de documentos ya chunked:
    [{ "id": ..., "text": ..., "metadata": {...}}]
    """
    raw = path.read_text(encoding="utf-8")
    base_meta: Dict[str, Any] = {
        "source": "local",
        "path": str(path),
        "lang": "es",
    }
    docs: List[Dict[str, Any]] = []

    if path.suffix.lower() == ".json":
        data = json.loads(raw)
        items = data if isinstance(data, list) else [data]
        for it in items:
            text = (it.get("text") or "").strip()
            if not text:
                continue
            meta = base_meta | {k: v for k, v in it.items() if k != "text"}
            chunks = split_into_chunks(text, max_chars=900, overlap=180)
            doc_id = meta.get("id") or slugify(meta.get("title", path.stem))
            for i, ch in enumerate(chunks):
                docs.append({
                    "id": f"{doc_id}#c{i+1}",
                    "text": ch,
                    "metadata": meta | {"chunk": i+1}
                })
        return docs

    if path.suffix.lower() in {".md", ".txt"}:
        fm, body = parse_markdown_with_frontmatter(raw)
        meta = base_meta | fm
        # título
        title = fm.get("title")
        if not title:
            for line in body.splitlines():
                if line.strip().startswith("#"):
                    title = line.strip("# ").strip()
                    break
        meta["title"] = title or path.stem.replace("_", " ").replace("-", " ").title()
        text = (body if body.strip() else raw).strip()
        if not text:
            return docs
        chunks = split_into_chunks(text, max_chars=900, overlap=180)
        doc_id = slugify(meta["title"])
        for i, ch in enumerate(chunks):
            docs.append({
                "id": f"{doc_id}#c{i+1}",
                "text": ch,
                "metadata": meta | {"chunk": i+1}
            })
        return docs

    return docs

def ensure_collection(recreate: bool):
    client = QdrantClient(url=settings.qdrant_url, timeout=settings.rag_timeout_s)
    dims = settings.parsed_vector_dims()
    cfg = {name: VectorParams(size=dim, distance=Distance.COSINE) for name, dim in dims.items()}

    if recreate:
        if client.collection_exists(settings.collection_name):
            client.delete_collection(settings.collection_name)
        client.create_collection(collection_name=settings.collection_name, vectors_config=cfg)
    else:
        if not client.collection_exists(settings.collection_name):
            client.create_collection(collection_name=settings.collection_name, vectors_config=cfg)

async def ingest_root(root: Path, recreate: bool):
    ensure_collection(recreate=recreate)
    files = discover_files(root)
    if not files:
        print("No se han encontrado ficheros en", root)
        return
    all_docs: List[Dict[str, Any]] = []
    for p in files:
        all_docs.extend(parse_file(p))
    if not all_docs:
        print("No se generaron chunks para ingerir.")
        return
    texts = [d["text"] for d in all_docs]
    payloads = [d["metadata"] | {"source_id": d["id"]} for d in all_docs]

    # Embeddings multi-modelo (usa settings si no pasas models)
    embs = await embed_dual(texts)

    # Inserción
    await upsert_documents(texts, payloads, embs)
    print(f"Ingeridos {len(texts)} chunks de {len(files)} fichero(s) desde {root}")

def main():
    ap = argparse.ArgumentParser(description="Ingesta local para RAG (MD/JSON/TXT)")
    ap.add_argument("--root", type=str, default="data", help="Directorio raíz con recetas y textos")
    ap.add_argument("--recreate", action="store_true", help="Recrear colección antes de ingerir")
    args = ap.parse_args()
    asyncio.run(ingest_root(Path(args.root), recreate=args.recreate))

if __name__ == "__main__":
    main()
