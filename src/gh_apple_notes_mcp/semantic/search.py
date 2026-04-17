"""Prefilter layer — BM25 keyword search, truncate body for LLM context."""
import json
from dataclasses import dataclass
from typing import Optional

from gh_apple_notes_mcp.semantic.config import MAX_BODY_CHARS_FOR_LLM
from gh_apple_notes_mcp.semantic.fts_index import FtsIndex


@dataclass
class Candidate:
    path: str
    title: str
    folder: str
    tags: str
    body: str
    classification: dict
    mtime: str


def prefilter(
    fts_index: FtsIndex,
    query: str,
    top_k: int = 50,
    filter_folder: Optional[str] = None,
) -> list[Candidate]:
    """BM25 search + truncate body for LLM context."""
    rows = fts_index.search(query=query, limit=top_k, filter_folder=filter_folder)
    candidates = []
    for r in rows:
        try:
            classification = json.loads(r["classification"]) if r["classification"] else {}
        except (json.JSONDecodeError, TypeError):
            classification = {}
        body = r["body"]
        if len(body) > MAX_BODY_CHARS_FOR_LLM:
            body = body[:MAX_BODY_CHARS_FOR_LLM] + "\n...[truncated]"
        candidates.append(Candidate(
            path=r["path"], title=r["title"], folder=r["folder"],
            tags=r["tags"], body=body,
            classification=classification, mtime=r["mtime"],
        ))
    return candidates
