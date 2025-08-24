import asyncio, json
from pathlib import Path
from schemas import IngestRequest, Document
from config import settings
from embeddings import embed_dual, embed_single
from vectorstore import ensure_collection, upsert_documents

async def main():
    models = settings.embedding_models.split(',')
    dims = {m: len(await embed_single("test", m)) for m in models}
    name_map = {"mxbai-embed-large": "mxbai", "jina-embeddings-v2-base-es": "jina"}
    vector_dims = { name_map[k]: v for k, v in dims.items() }
    await ensure_collection(vector_dims)
    data = json.loads(Path("../seeds/recipes_min.json").read_text())
    docs = [Document(**d) for d in data]
    texts = [d.text for d in docs]
    payloads = [{**d.metadata, **({"id": d.id} if d.id else {})} for d in docs]
    embs = await embed_dual(texts, models)
    await upsert_documents(texts, payloads, embs)
    print(f"Ingestados: {len(texts)} documentos")

if __name__ == "__main__":
    asyncio.run(main())
