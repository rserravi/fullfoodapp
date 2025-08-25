from __future__ import annotations
from typing import Tuple, Dict, Any
import re
import yaml

FRONT_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.S)

def parse_markdown_with_frontmatter(text: str) -> Tuple[Dict[str, Any], str]:
    """
    Devuelve (frontmatter_dict, body_md).
    Soporta YAML frontmatter al inicio delimitado por --- ... ---.
    """
    m = FRONT_RE.match(text)
    if not m:
        return {}, text
    fm_raw = m.group(1)
    try:
        fm = yaml.safe_load(fm_raw) or {}
        body = text[m.end():]
        return (fm if isinstance(fm, dict) else {}), body
    except Exception:
        return {}, text
