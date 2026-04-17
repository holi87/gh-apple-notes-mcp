"""LLM reranker — spawn `claude --print` with candidates, parse JSON response."""
import json
import logging
import shutil
import subprocess
from typing import Optional

from gh_apple_notes_mcp.semantic.config import LLM_TIMEOUT_SECONDS
from gh_apple_notes_mcp.semantic.search import Candidate


logger = logging.getLogger(__name__)


class ClaudeCliNotAvailableError(RuntimeError):
    """`claude` CLI not in PATH."""


class LlmTimeoutError(TimeoutError):
    """`claude --print` timed out."""


def build_prompt(query: str, candidates: list[Candidate], top_k: int) -> str:
    """Format LLM rerank prompt."""
    cands_json = [
        {
            "path": c.path,
            "title": c.title,
            "folder": c.folder,
            "tags": c.tags,
            "body": c.body,
        }
        for c in candidates
    ]
    return (
        f'Query: "{query}"\n\n'
        f"Candidate notes (BM25 prefilter results):\n"
        f"{json.dumps(cands_json, ensure_ascii=False, indent=2)}\n\n"
        f"Rank the top {top_k} most semantically relevant candidates to the query.\n"
        f"Return JSON array (and nothing else):\n"
        f'[{{"path": "<path>", "relevance": 0.0-1.0, "reason": "1-sentence why"}}]\n'
        f"Order by relevance descending. Include ONLY the top {top_k}."
    )


def _fallback_bm25_order(candidates: list[Candidate], top_k: int) -> list[dict]:
    """Fallback when LLM fails: candidates in BM25 order."""
    return [
        {
            "path": c.path, "title": c.title, "folder": c.folder,
            "relevance": 0.5,
            "reason": "fallback: BM25 order (LLM rerank unavailable)",
        }
        for c in candidates[:top_k]
    ]


def rank(
    query: str,
    candidates: list[Candidate],
    top_k: int = 5,
) -> list[dict]:
    """Rerank via `claude --print`. Fallback to BM25 order on errors."""
    if not candidates:
        return []

    claude_bin = shutil.which("claude")
    if claude_bin is None:
        raise ClaudeCliNotAvailableError(
            "`claude` CLI not found in PATH. Install Claude Code or use mode='candidates' "
            "to let the in-session LLM rank."
        )

    prompt = build_prompt(query=query, candidates=candidates, top_k=top_k)

    try:
        result = subprocess.run(
            [claude_bin, "--print", "-p", prompt],
            capture_output=True, text=True,
            timeout=LLM_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        raise LlmTimeoutError(
            f"claude --print timed out after {LLM_TIMEOUT_SECONDS}s"
        )

    if result.returncode != 0:
        logger.warning(f"claude --print failed: {result.stderr}")
        return _fallback_bm25_order(candidates, top_k)

    try:
        parsed = json.loads(result.stdout)
    except json.JSONDecodeError as e:
        logger.warning(f"LLM returned non-JSON: {e}")
        return _fallback_bm25_order(candidates, top_k)

    if not isinstance(parsed, list):
        return _fallback_bm25_order(candidates, top_k)

    return parsed[:top_k]
