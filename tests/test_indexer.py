"""Tests for Indexer (incremental + full rebuild)."""
import time
from pathlib import Path

import pytest

from gh_apple_notes_mcp.semantic.indexer import Indexer
from gh_apple_notes_mcp.semantic.fts_index import FtsIndex
from gh_apple_notes_mcp.semantic.state import load_state


F2_SAMPLE = """---
title: {title}
classification:
  folder: {folder}
  confidence: 0.9
---

# {title}

<!-- APPLE-NOTES-START -->
{body}
<!-- APPLE-NOTES-END -->

## TODO

## Powiązane
"""


def _write(vault: Path, rel: str, title: str, body: str) -> Path:
    folder = rel.split("/")[0]
    f = vault / rel
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(F2_SAMPLE.format(title=title, folder=folder, body=body))
    return f


def _make_indexer(tmp_path: Path) -> Indexer:
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "_Reports").mkdir()
    idx = FtsIndex(vault / "_Reports" / "fts.sqlite")
    return Indexer(
        vault_path=vault,
        state_file=vault / "_Reports" / ".state.json",
        fts_index=idx,
    )


def test_full_rebuild_indexes_all_files(tmp_path):
    indexer = _make_indexer(tmp_path)
    _write(indexer.vault_path, "APP-Dev/a.md", "Bug A", "deploy crash")
    _write(indexer.vault_path, "Work/b.md", "Meeting", "retro sprint")
    stats = indexer.full_rebuild()
    assert stats["indexed"] == 2
    results = indexer.fts_index.search("crash", limit=10)
    assert len(results) == 1


def test_full_rebuild_skips_special_folders(tmp_path):
    indexer = _make_indexer(tmp_path)
    _write(indexer.vault_path, "APP-Dev/good.md", "good", "deploy")
    _write(indexer.vault_path, "_Reports/log.md", "log", "deploy")
    _write(indexer.vault_path, "_Sensitive-flagged/x.md", "x", "deploy")
    stats = indexer.full_rebuild()
    assert stats["indexed"] == 1


def test_full_rebuild_deletes_old_state(tmp_path):
    indexer = _make_indexer(tmp_path)
    _write(indexer.vault_path, "X/old.md", "old", "old content")
    indexer.full_rebuild()
    (indexer.vault_path / "X" / "old.md").unlink()
    _write(indexer.vault_path, "Y/new.md", "new", "new content")
    indexer.full_rebuild()
    assert indexer.fts_index.search("old content", limit=10) == []
    assert len(indexer.fts_index.search("new content", limit=10)) == 1


def test_ensure_fresh_incremental_skip_unchanged(tmp_path):
    indexer = _make_indexer(tmp_path)
    _write(indexer.vault_path, "X/a.md", "A", "body")
    indexer.full_rebuild()
    stats = indexer.ensure_fresh()
    assert stats["indexed"] == 0


def test_ensure_fresh_indexes_new_file(tmp_path):
    indexer = _make_indexer(tmp_path)
    _write(indexer.vault_path, "X/a.md", "A", "aaa")
    indexer.full_rebuild()
    _write(indexer.vault_path, "X/b.md", "B", "bbb")
    stats = indexer.ensure_fresh()
    assert stats["indexed"] == 1
    results = indexer.fts_index.search("bbb", limit=10)
    assert len(results) == 1


def test_ensure_fresh_reindexes_modified_file(tmp_path):
    indexer = _make_indexer(tmp_path)
    _write(indexer.vault_path, "X/a.md", "A", "original")
    indexer.full_rebuild()
    time.sleep(0.01)
    _write(indexer.vault_path, "X/a.md", "A", "updated content")
    stats = indexer.ensure_fresh()
    assert stats["indexed"] == 1
    assert len(indexer.fts_index.search("updated", limit=10)) == 1
    assert indexer.fts_index.search("original", limit=10) == []


def test_ensure_fresh_removes_deleted_file(tmp_path):
    indexer = _make_indexer(tmp_path)
    _write(indexer.vault_path, "X/a.md", "A", "aaa")
    _write(indexer.vault_path, "X/b.md", "B", "bbb")
    indexer.full_rebuild()
    (indexer.vault_path / "X" / "a.md").unlink()
    stats = indexer.ensure_fresh()
    assert stats["deleted"] == 1
    assert indexer.fts_index.search("aaa", limit=10) == []


def test_ensure_fresh_handles_malformed_file(tmp_path):
    indexer = _make_indexer(tmp_path)
    (indexer.vault_path / "X").mkdir()
    (indexer.vault_path / "X" / "bad.md").write_text("no frontmatter here")
    stats = indexer.ensure_fresh()
    assert stats.get("errors", 0) >= 1 or stats["indexed"] == 0


def test_state_persisted_after_full_rebuild(tmp_path):
    indexer = _make_indexer(tmp_path)
    _write(indexer.vault_path, "X/a.md", "A", "aaa")
    indexer.full_rebuild()
    state = load_state(indexer.state_file)
    assert "X/a.md" in state.file_mtimes
