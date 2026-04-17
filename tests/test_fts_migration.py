"""Tests for lazy migration of v0.1 databases (single fts table) to v0.2."""
import sqlite3
from pathlib import Path
from unittest.mock import patch

import pytest

from gh_apple_notes_mcp.semantic.fts_index import FtsIndex


def _create_v01_database(db_path: Path):
    """Simulate a v0.1 database with only the main fts table populated."""
    with sqlite3.connect(db_path) as conn:
        conn.executescript("""
            CREATE VIRTUAL TABLE fts USING fts5(
                path UNINDEXED, title, folder UNINDEXED, tags, body,
                classification UNINDEXED, mtime UNINDEXED,
                tokenize = 'unicode61 remove_diacritics 2'
            );
        """)
        conn.execute(
            "INSERT INTO fts (path, title, folder, tags, body, classification, mtime) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("Ideas/legacy.md", "microcosmos", "Ideas", "",
             "old content", "{}", "2026-01-01T00:00:00Z"),
        )


def test_lazy_build_creates_trigram_from_existing_fts(tmp_path):
    db = tmp_path / "fts.sqlite"
    _create_v01_database(db)
    idx = FtsIndex(db)
    # First search triggers migration
    results = idx.search("cosmos", limit=5)
    # Verify trigram table now exists and has row
    with sqlite3.connect(db) as conn:
        names = [r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()]
        tri_count = conn.execute("SELECT COUNT(*) FROM fts_trigram").fetchone()[0]
    assert "fts_trigram" in names
    assert tri_count == 1
    # And the substring match works
    paths = [r["path"] for r in results]
    assert "Ideas/legacy.md" in paths


def test_lazy_build_idempotent_second_call_noop(tmp_path):
    db = tmp_path / "fts.sqlite"
    _create_v01_database(db)
    idx = FtsIndex(db)
    idx.search("cosmos", limit=5)  # migrates
    idx.search("cosmos", limit=5)  # should NOT re-copy
    with sqlite3.connect(db) as conn:
        tri_count = conn.execute("SELECT COUNT(*) FROM fts_trigram").fetchone()[0]
    assert tri_count == 1  # still 1, not 2


def test_lazy_build_skipped_when_fresh_db(tmp_path):
    """Fresh db (created_schema) already has fts_trigram — migration is no-op."""
    idx = FtsIndex(tmp_path / "fts.sqlite")
    idx.create_schema()
    # Should not raise or duplicate
    idx._ensure_trigram_table_exists()
    idx._ensure_trigram_table_exists()


def test_trigram_unavailable_graceful_degradation(tmp_path):
    """If SQLite build lacks trigram tokenizer, search falls back to prefix-only
    without crashing."""
    db = tmp_path / "fts.sqlite"
    _create_v01_database(db)
    idx = FtsIndex(db)

    real_connect = idx._connect

    class _ConnProxy:
        def __init__(self, conn):
            self._conn = conn

        def executescript(self, sql):
            if "trigram" in sql.lower():
                raise sqlite3.OperationalError("no such tokenizer: trigram")
            return self._conn.executescript(sql)

        def __getattr__(self, name):
            return getattr(self._conn, name)

        def __enter__(self):
            self._conn.__enter__()
            return self

        def __exit__(self, *args):
            return self._conn.__exit__(*args)

    def connect_with_broken_trigram():
        return _ConnProxy(real_connect())

    with patch.object(idx, "_connect", connect_with_broken_trigram):
        # Should NOT raise — logs warning and continues
        results = idx.search("cosmos", limit=5)
        # Prefix-only (no trigram fallback available)
        # "cosmos" is not a prefix of "microcosmos" — so 0 results here
        assert results == []
