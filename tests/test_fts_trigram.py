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
