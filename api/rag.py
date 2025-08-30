from typing import List, Dict
from .embeddings import embed_single
from .vectorstore import search

def rrf_fuse(results_lists: List[List], k: int = 60) -> List:
    scores: Dict[str, float] = {}
    best_obj: Dict[str, object] = {}
    for results in results_lists:
        for rank, item in enumerate(results, start=1):
            pid = str(item.id)
            scores[pid] = scores.get(pid, 0.0) + 1.0 / (k + rank)
            if pid not in best_obj:
                best_obj[pid] = item
    fused = sorted(best_obj.values(), key=lambda x: scores[str(x.id)], reverse=True)
    return fused

async def hybrid_retrieve(query: str, top_k_each: int = 5) -> List:
    model_map = {"mxbai": "mxbai-embed-large", "jina": "jina-embeddings-v2-base-es"}
    vec_mxbai = await embed_single(query, model_map["mxbai"])
    vec_jina  = await embed_single(query, model_map["jina"])
    res_mxbai = await search({"mxbai": vec_mxbai}, top_k_each)
    res_jina  = await search({"jina": vec_jina},  top_k_each)
    return rrf_fuse([res_mxbai, res_jina])

def build_context(hits, max_chars: int = 1400) -> str:
    parts: List[str] = []
    used = 0
    for h in hits:
        payload = (h.payload or {})
        title = payload.get("title") or (payload.get("tags", [""]) or [""])[0]
        snippet = payload.get("text", "")[:400].replace("\n", " ").strip()
        item = f"- title: {title} | text: {snippet}"
        if used + len(item) > max_chars and parts:
            break
        parts.append(item)
        used += len(item)
    return "\n".join(parts)
