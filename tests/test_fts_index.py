"""Tests for SQLite FTS5 wrapper."""
from pathlib import Path

import pytest

from gh_apple_notes_mcp.semantic.fts_index import FtsIndex


def test_create_schema(tmp_path):
    db = tmp_path / "fts.sqlite"
    idx = FtsIndex(db)
    idx.create_schema()
    idx.create_schema()  # idempotent
    assert db.exists()


def test_upsert_and_search(tmp_path):
    idx = FtsIndex(tmp_path / "fts.sqlite")
    idx.create_schema()
    idx.upsert({
        "path": "APP-Dev/cosmicforge.md",
        "title": "CosmicForge Bugs",
        "folder": "APP-Dev",
        "tags": "claude claude/synced",
        "body": "Crash on deploy. Race condition in auth flow.",
        "classification": '{"folder":"APP-Dev","confidence":0.9}',
        "mtime": "2026-04-17T09:00:00Z",
    })
    results = idx.search("crash", limit=10)
    assert len(results) == 1
    assert results[0]["path"] == "APP-Dev/cosmicforge.md"
    assert results[0]["title"] == "CosmicForge Bugs"


def test_search_polish_diacritics_normalized(tmp_path):
    idx = FtsIndex(tmp_path / "fts.sqlite")
    idx.create_schema()
    idx.upsert({
        "path": "Personal/zakupy.md",
        "title": "Zakupy",
        "folder": "Personal",
        "tags": "",
        "body": "Muszę kupić chleb i łódź na weekend.",
        "classification": "",
        "mtime": "2026-04-17T09:00:00Z",
    })
    r_ascii = idx.search("lodz", limit=10)
    assert len(r_ascii) == 1
    r_diac = idx.search("łódź", limit=10)
    assert len(r_diac) == 1


def test_upsert_replaces_existing(tmp_path):
    idx = FtsIndex(tmp_path / "fts.sqlite")
    idx.create_schema()
    record = {
        "path": "X/a.md", "title": "V1", "folder": "X",
        "tags": "", "body": "original body", "classification": "",
        "mtime": "2026-04-17T09:00:00Z",
    }
    idx.upsert(record)
    record["title"] = "V2"
    record["body"] = "updated body"
    idx.upsert(record)
    results = idx.search("updated", limit=10)
    assert len(results) == 1
    assert results[0]["title"] == "V2"
    assert idx.search("original", limit=10) == []


def test_delete_removes_note(tmp_path):
    idx = FtsIndex(tmp_path / "fts.sqlite")
    idx.create_schema()
    idx.upsert({
        "path": "X/a.md", "title": "T", "folder": "X",
        "tags": "", "body": "body", "classification": "",
        "mtime": "2026-04-17T09:00:00Z",
    })
    assert len(idx.search("body", limit=10)) == 1
    idx.delete("X/a.md")
    assert idx.search("body", limit=10) == []


def test_search_limit(tmp_path):
    idx = FtsIndex(tmp_path / "fts.sqlite")
    idx.create_schema()
    for i in range(20):
        idx.upsert({
            "path": f"X/note-{i}.md", "title": f"Note {i}", "folder": "X",
            "tags": "", "body": f"content term {i}", "classification": "",
            "mtime": "2026-04-17T09:00:00Z",
        })
    results = idx.search("term", limit=5)
    assert len(results) == 5


def test_search_folder_filter(tmp_path):
    idx = FtsIndex(tmp_path / "fts.sqlite")
    idx.create_schema()
    idx.upsert({
        "path": "APP-Dev/a.md", "title": "A", "folder": "APP-Dev",
        "tags": "", "body": "deploy bug", "classification": "",
        "mtime": "2026-04-17T09:00:00Z",
    })
    idx.upsert({
        "path": "Work/b.md", "title": "B", "folder": "Work",
        "tags": "", "body": "deploy issue", "classification": "",
        "mtime": "2026-04-17T09:00:00Z",
    })
    results = idx.search("deploy", limit=10, filter_folder="APP-Dev")
    assert len(results) == 1
    assert results[0]["folder"] == "APP-Dev"


def test_search_special_chars_escaped(tmp_path):
    idx = FtsIndex(tmp_path / "fts.sqlite")
    idx.create_schema()
    idx.upsert({
        "path": "X/a.md", "title": "T", "folder": "X",
        "tags": "", "body": "api endpoint test", "classification": "",
        "mtime": "t",
    })
    # Query with quotes — now treated as AND of api + endpoint
    results = idx.search('api "endpoint"', limit=10)
    assert len(results) == 1  # still finds it (AND of api + endpoint)


def test_search_prefix_match(tmp_path):
    idx = FtsIndex(tmp_path / "fts.sqlite")
    idx.create_schema()
    idx.upsert({
        "path": "Work/ailab2.md", "title": "AILAB2", "folder": "Work",
        "tags": "", "body": "notatka o konkursie ailab2 w tym roku", "classification": "",
        "mtime": "t",
    })
    # Prefix query "ailab" should match "ailab2" token
    results = idx.search("ailab", limit=10)
    assert len(results) == 1


def test_search_multi_word_and_semantics(tmp_path):
    idx = FtsIndex(tmp_path / "fts.sqlite")
    idx.create_schema()
    idx.upsert({
        "path": "Ideas/a.md", "title": "Pomysly", "folder": "Ideas",
        "tags": "", "body": "contest for ailab2 is a good idea", "classification": "",
        "mtime": "t",
    })
    idx.upsert({
        "path": "Ideas/b.md", "title": "Inne", "folder": "Ideas",
        "tags": "", "body": "only machine learning without any event", "classification": "",
        "mtime": "t",
    })
    # Query "contest ailab" — both must be present (AND)
    results = idx.search("contest ailab", limit=10)
    # Only Ideas/a.md has both "contest" and "ailab" (via prefix match for ailab2)
    assert len(results) == 1
    assert results[0]["path"] == "Ideas/a.md"


def test_search_adjacent_phrase_no_longer_required(tmp_path):
    """Previously phrase match required adjacency — should no longer."""
    idx = FtsIndex(tmp_path / "fts.sqlite")
    idx.create_schema()
    idx.upsert({
        "path": "X/a.md", "title": "T", "folder": "X",
        "tags": "", "body": "crash in prod, deploy failed", "classification": "",
        "mtime": "t",
    })
    # "deploy crash" non-adjacent — should still match
    results = idx.search("deploy crash", limit=10)
    assert len(results) == 1


def test_search_empty_query_returns_empty(tmp_path):
    idx = FtsIndex(tmp_path / "fts.sqlite")
    idx.create_schema()
    assert idx.search("", limit=10) == []


def test_search_results_ordered_by_rank(tmp_path):
    idx = FtsIndex(tmp_path / "fts.sqlite")
    idx.create_schema()
    idx.upsert({
        "path": "X/low.md", "title": "low", "folder": "X",
        "tags": "", "body": "crash", "classification": "", "mtime": "t",
    })
    idx.upsert({
        "path": "X/high.md", "title": "crash crash crash", "folder": "X",
        "tags": "", "body": "crash crash crash crash", "classification": "", "mtime": "t",
    })
    results = idx.search("crash", limit=10)
    assert results[0]["path"] == "X/high.md"
