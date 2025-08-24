import asyncio, json
from pathlib import Path
from api.schemas import Document
from api.config import settings
from api.embeddings import embed_dual
from api.vectorstore import ensure_collection, upsert_documents

async def main():
    # Asegura la colección con dims desde .env (sin tocar Ollama)
    await ensure_collection(settings.parsed_vector_dims())

    # Ruta robusta al seed JSON (independiente del cwd)
    data_path = Path(__file__).resolve().parents[1] / "seeds" / "recipes_min.json"
    data = json.loads(data_path.read_text(encoding="utf-8"))

    docs = [Document(**d) for d in data]
    texts = [d.text for d in docs]
    payloads = [{**d.metadata, **({"id": d.id} if d.id else {})} for d in docs]

    models = settings.parsed_embedding_models()
    embs = await embed_dual(texts, models)
    await upsert_documents(texts, payloads, embs)
    print(f"Ingestados: {len(texts)} documentos")

if __name__ == "__main__":
    asyncio.run(main())