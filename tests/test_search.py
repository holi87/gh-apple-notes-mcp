"""Tests for search.prefilter."""
from pathlib import Path

import pytest

from gh_apple_notes_mcp.semantic.fts_index import FtsIndex
from gh_apple_notes_mcp.semantic.search import prefilter, Candidate


def _setup_idx(tmp_path, records):
    idx = FtsIndex(tmp_path / "fts.sqlite")
    idx.create_schema()
    for r in records:
        idx.upsert(r)
    return idx


def test_prefilter_returns_candidates(tmp_path):
    idx = _setup_idx(tmp_path, [
        {"path": "X/a.md", "title": "A", "folder": "X",
         "tags": "", "body": "deploy crash", "classification": "{}",
         "mtime": "2026-04-17T09:00:00Z"},
    ])
    results = prefilter(idx, query="crash", top_k=50)
    assert len(results) == 1
    c = results[0]
    assert isinstance(c, Candidate)
    assert c.path == "X/a.md"
    assert c.body == "deploy crash"


def test_prefilter_top_k_limit(tmp_path):
    records = [
        {"path": f"X/n-{i}.md", "title": f"N{i}", "folder": "X",
         "tags": "", "body": "term deploy", "classification": "{}", "mtime": "t"}
        for i in range(10)
    ]
    idx = _setup_idx(tmp_path, records)
    results = prefilter(idx, query="deploy", top_k=3)
    assert len(results) == 3


def test_prefilter_folder_filter(tmp_path):
    idx = _setup_idx(tmp_path, [
        {"path": "APP-Dev/a.md", "title": "A", "folder": "APP-Dev",
         "tags": "", "body": "deploy", "classification": "{}", "mtime": "t"},
        {"path": "Work/b.md", "title": "B", "folder": "Work",
         "tags": "", "body": "deploy", "classification": "{}", "mtime": "t"},
    ])
    results = prefilter(idx, query="deploy", top_k=50, filter_folder="APP-Dev")
    assert len(results) == 1
    assert results[0].folder == "APP-Dev"


def test_prefilter_empty_query_returns_empty(tmp_path):
    idx = _setup_idx(tmp_path, [
        {"path": "X/a.md", "title": "A", "folder": "X",
         "tags": "", "body": "body", "classification": "{}", "mtime": "t"},
    ])
    assert prefilter(idx, query="", top_k=50) == []


def test_prefilter_body_truncation(tmp_path):
    long_body = "word " * 5000
    idx = _setup_idx(tmp_path, [
        {"path": "X/big.md", "title": "Big", "folder": "X",
         "tags": "", "body": long_body, "classification": "{}", "mtime": "t"},
    ])
    results = prefilter(idx, query="word", top_k=10)
    from gh_apple_notes_mcp.semantic.config import MAX_BODY_CHARS_FOR_LLM
    assert len(results[0].body) <= MAX_BODY_CHARS_FOR_LLM + 20  # +20 for "\n...[truncated]"
