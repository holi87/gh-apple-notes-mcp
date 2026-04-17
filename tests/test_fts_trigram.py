"""Tests for FTS5 trigram table dual-write behavior."""
import sqlite3
from pathlib import Path

import pytest

from gh_apple_notes_mcp.semantic.fts_index import FtsIndex


def _row(path: str, title: str = "T", body: str = "body content") -> dict:
    return {
        "path": path,
        "title": title,
        "folder": "Ideas",
        "tags": "claude",
        "body": body,
        "classification": '{"folder":"Ideas","confidence":0.9}',
        "mtime": "2026-04-17T09:00:00Z",
    }


def test_upsert_writes_to_both_tables(tmp_path):
    idx = FtsIndex(tmp_path / "fts.sqlite")
    idx.create_schema()
    idx.upsert(_row("Ideas/x.md", title="X", body="microcosmos content"))
    with sqlite3.connect(tmp_path / "fts.sqlite") as conn:
        fts_count = conn.execute("SELECT COUNT(*) FROM fts").fetchone()[0]
        tri_count = conn.execute("SELECT COUNT(*) FROM fts_trigram").fetchone()[0]
    assert fts_count == 1
    assert tri_count == 1


def test_upsert_replaces_in_both_tables(tmp_path):
    idx = FtsIndex(tmp_path / "fts.sqlite")
    idx.create_schema()
    idx.upsert(_row("Ideas/x.md", title="first"))
    idx.upsert(_row("Ideas/x.md", title="second"))
    with sqlite3.connect(tmp_path / "fts.sqlite") as conn:
        fts_count = conn.execute("SELECT COUNT(*) FROM fts").fetchone()[0]
        tri_count = conn.execute("SELECT COUNT(*) FROM fts_trigram").fetchone()[0]
    assert fts_count == 1
    assert tri_count == 1


def test_delete_removes_from_both_tables(tmp_path):
    idx = FtsIndex(tmp_path / "fts.sqlite")
    idx.create_schema()
    idx.upsert(_row("Ideas/x.md"))
    idx.upsert(_row("Ideas/y.md"))
    idx.delete("Ideas/x.md")
    with sqlite3.connect(tmp_path / "fts.sqlite") as conn:
        fts_paths = [r[0] for r in conn.execute("SELECT path FROM fts").fetchall()]
        tri_paths = [r[0] for r in conn.execute("SELECT path FROM fts_trigram").fetchall()]
    assert fts_paths == ["Ideas/y.md"]
    assert tri_paths == ["Ideas/y.md"]


from gh_apple_notes_mcp.semantic.fts_index import _escape_trigram_query


def test_escape_trigram_single_word():
    assert _escape_trigram_query("cosmos") == '"cosmos"'


def test_escape_trigram_multi_word_and():
    result = _escape_trigram_query("cosmos test")
    assert result == '"cosmos" AND "test"'


def test_escape_trigram_too_short_returns_empty():
    assert _escape_trigram_query("ab") == ""
    assert _escape_trigram_query("a") == ""
    assert _escape_trigram_query("") == ""


def test_escape_trigram_whitespace_only_returns_empty():
    assert _escape_trigram_query("   ") == ""


def test_escape_trigram_escapes_embedded_double_quote():
    # " becomes "" inside phrase per FTS5 spec
    assert _escape_trigram_query('he"llo') == '"he""llo"'


def test_escape_trigram_normalizes_polish_diacritics():
    # łódź → lodz (transliteration + NFD fold)
    assert _escape_trigram_query("łódź") == '"lodz"'


def test_trigram_search_finds_substring_match(tmp_path):
    idx = FtsIndex(tmp_path / "fts.sqlite")
    idx.create_schema()
    idx.upsert(_row("Ideas/a.md", title="microcosmos", body="nothing here"))
    idx.upsert(_row("Ideas/b.md", title="unrelated", body="zero overlap"))
    results = idx._trigram_search("cosmos", limit=10)
    paths = [r["path"] for r in results]
    assert "Ideas/a.md" in paths
    assert "Ideas/b.md" not in paths


def test_trigram_search_respects_filter_folder(tmp_path):
    idx = FtsIndex(tmp_path / "fts.sqlite")
    idx.create_schema()
    idx.upsert(_row("Ideas/a.md", title="microcosmos"))
    idx.upsert({
        "path": "Work/b.md", "title": "microcosmos", "folder": "Work",
        "tags": "", "body": "body", "classification": "{}",
        "mtime": "2026-04-17T09:00:00Z",
    })
    results = idx._trigram_search("cosmos", limit=10, filter_folder="Ideas")
    paths = [r["path"] for r in results]
    assert paths == ["Ideas/a.md"]


def test_trigram_search_empty_query_returns_empty(tmp_path):
    idx = FtsIndex(tmp_path / "fts.sqlite")
    idx.create_schema()
    idx.upsert(_row("Ideas/a.md"))
    assert idx._trigram_search("", limit=10) == []
    assert idx._trigram_search("ab", limit=10) == []  # <3 chars


def test_trigram_search_returns_classification_and_mtime_via_join(tmp_path):
    idx = FtsIndex(tmp_path / "fts.sqlite")
    idx.create_schema()
    idx.upsert(_row("Ideas/a.md", title="microcosmos"))
    results = idx._trigram_search("cosmos", limit=10)
    assert len(results) == 1
    r = results[0]
    assert r["classification"] == '{"folder":"Ideas","confidence":0.9}'
    assert r["mtime"] == "2026-04-17T09:00:00Z"
