from __future__ import annotations
from typing import List

def split_into_chunks(text: str, max_chars: int = 1000, overlap: int = 200) -> List[str]:
    """
    Particiona texto en trozos ~max_chars, respetando saltos de párrafo cuando sea posible.
    Añade solapamiento para preservar contexto entre chunks.
    """
    text = text.strip()
    if not text:
        return []
    paras = [p.strip() for p in text.split("\n\n") if p.strip()]
    chunks: List[str] = []
    buf: List[str] = []
    size = 0
    for p in paras:
        if size + len(p) + (2 if buf else 0) <= max_chars:
            buf.append(p)
            size += len(p) + (2 if len(buf) > 1 else 0)
        else:
            if buf:
                chunks.append("\n\n".join(buf))
            # Si el párrafo es muy largo, cortamos duro
            if len(p) > max_chars:
                s = 0
                while s < len(p):
                    e = min(s + max_chars, len(p))
                    chunks.append(p[s:e])
                    s = e - overlap if e < len(p) else e
                buf = []
                size = 0
            else:
                buf = [p]
                size = len(p)
    if buf:
        chunks.append("\n\n".join(buf))
    # Añadir solapamiento ligero entre chunks largos
    if overlap and len(chunks) > 1:
        out = []
        for i, c in enumerate(chunks):
            if i == 0:
                out.append(c)
                continue
            prev_tail = chunks[i-1][-overlap:] if len(chunks[i-1]) > overlap else chunks[i-1]
            combined = prev_tail + ("\n\n" if prev_tail and not prev_tail.endswith("\n") else "") + c
            out.append(combined)
        return out
    return chunks
