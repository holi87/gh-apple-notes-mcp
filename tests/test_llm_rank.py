"""Tests for LLM reranker (claude --print subprocess mocked)."""
import json
from unittest.mock import MagicMock, patch

import pytest

from gh_apple_notes_mcp.semantic.llm_rank import (
    rank,
    build_prompt,
    ClaudeCliNotAvailableError,
    LlmTimeoutError,
)
from gh_apple_notes_mcp.semantic.search import Candidate


def _make_candidates():
    return [
        Candidate(
            path="APP-Dev/a.md", title="CosmicForge Bug", folder="APP-Dev",
            tags="claude", body="Deploy crash bug",
            classification={"folder": "APP-Dev"}, mtime="t",
        ),
        Candidate(
            path="Ideas/b.md", title="PoC Contract Testing", folder="Ideas",
            tags="", body="Ideas for PoC contract testing with embeddings",
            classification={"folder": "Ideas"}, mtime="t",
        ),
    ]


def test_build_prompt_includes_query_and_candidates():
    candidates = _make_candidates()
    prompt = build_prompt(query="contract testing", candidates=candidates, top_k=1)
    assert "contract testing" in prompt
    assert "APP-Dev/a.md" in prompt
    assert "Ideas/b.md" in prompt
    assert "relevance" in prompt
    assert "reason" in prompt


@patch("gh_apple_notes_mcp.semantic.llm_rank.shutil.which")
def test_rank_raises_when_claude_missing(mock_which):
    mock_which.return_value = None
    with pytest.raises(ClaudeCliNotAvailableError):
        rank(query="x", candidates=_make_candidates(), top_k=5)


@patch("gh_apple_notes_mcp.semantic.llm_rank.shutil.which")
@patch("gh_apple_notes_mcp.semantic.llm_rank.subprocess.run")
def test_rank_returns_parsed_json(mock_run, mock_which):
    mock_which.return_value = "/usr/local/bin/claude"
    mock_run.return_value = MagicMock(
        returncode=0,
        stdout=json.dumps([
            {"path": "Ideas/b.md", "relevance": 0.9, "reason": "directly about contract testing"},
            {"path": "APP-Dev/a.md", "relevance": 0.1, "reason": "unrelated"},
        ]),
        stderr="",
    )
    results = rank(query="contract testing", candidates=_make_candidates(), top_k=2)
    assert len(results) == 2
    assert results[0]["path"] == "Ideas/b.md"
    assert results[0]["relevance"] == 0.9


@patch("gh_apple_notes_mcp.semantic.llm_rank.shutil.which")
@patch("gh_apple_notes_mcp.semantic.llm_rank.subprocess.run")
def test_rank_timeout_raises(mock_run, mock_which):
    mock_which.return_value = "/usr/local/bin/claude"
    import subprocess as sp
    mock_run.side_effect = sp.TimeoutExpired(cmd="claude", timeout=60)
    with pytest.raises(LlmTimeoutError):
        rank(query="x", candidates=_make_candidates(), top_k=5)


@patch("gh_apple_notes_mcp.semantic.llm_rank.shutil.which")
@patch("gh_apple_notes_mcp.semantic.llm_rank.subprocess.run")
def test_rank_broken_json_falls_back_to_bm25_order(mock_run, mock_which):
    mock_which.return_value = "/usr/local/bin/claude"
    mock_run.return_value = MagicMock(
        returncode=0,
        stdout="not valid json{{",
        stderr="",
    )
    results = rank(query="x", candidates=_make_candidates(), top_k=5)
    assert results[0]["path"] == "APP-Dev/a.md"
    assert results[1]["path"] == "Ideas/b.md"
    assert all("fallback" in r.get("reason", "").lower() for r in results)


@patch("gh_apple_notes_mcp.semantic.llm_rank.shutil.which")
@patch("gh_apple_notes_mcp.semantic.llm_rank.subprocess.run")
def test_rank_clamps_top_k(mock_run, mock_which):
    mock_which.return_value = "/usr/local/bin/claude"
    mock_run.return_value = MagicMock(
        returncode=0,
        stdout=json.dumps([
            {"path": "Ideas/b.md", "relevance": 0.9, "reason": "a"},
            {"path": "APP-Dev/a.md", "relevance": 0.5, "reason": "b"},
        ]),
        stderr="",
    )
    results = rank(query="x", candidates=_make_candidates(), top_k=1)
    assert len(results) == 1
