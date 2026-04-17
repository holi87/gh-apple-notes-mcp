"""E2E: real FTS5 + fixture vault + mock LLM."""
import json
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from tests.fixtures.build_vault_fixture import build_vault
from gh_apple_notes_mcp.semantic.fts_index import FtsIndex
from gh_apple_notes_mcp.semantic.indexer import Indexer
from gh_apple_notes_mcp.semantic.search import prefilter
from gh_apple_notes_mcp.semantic.llm_rank import rank


@pytest.fixture
def sample_vault(tmp_path):
    vault = tmp_path / "vault"
    build_vault(vault)
    return vault


@pytest.fixture
def indexer(sample_vault):
    return Indexer(
        vault_path=sample_vault,
        state_file=sample_vault / "_Reports" / ".state.json",
        fts_index=FtsIndex(sample_vault / "_Reports" / "fts.sqlite"),
    )


def test_e2e_full_pipeline(indexer):
    stats = indexer.full_rebuild()
    assert stats["indexed"] == 10

    # Search for "contract testing" — should match "PoC contract testing" note
    candidates = prefilter(indexer.fts_index, query="contract testing", top_k=50)
    paths = [c.path for c in candidates]
    assert any("contract" in p.lower() or "konkurs" in p.lower() for p in paths)


def test_e2e_incremental_picks_up_new_file(indexer):
    indexer.full_rebuild()
    # Add new file
    new = indexer.vault_path / "Inbox" / "2026-04-17-newly-added.md"
    new.write_text("""---
title: Newly added note
classification:
  folder: Inbox
---

# Newly added

<!-- APPLE-NOTES-START -->
This note talks about newly added special topic.
<!-- APPLE-NOTES-END -->
""")
    stats = indexer.ensure_fresh()
    assert stats["indexed"] == 1

    candidates = prefilter(indexer.fts_index, query="newly added", top_k=10)
    assert any("newly-added" in c.path for c in candidates)


@patch("gh_apple_notes_mcp.semantic.llm_rank.shutil.which")
@patch("gh_apple_notes_mcp.semantic.llm_rank.subprocess.run")
def test_e2e_rank_mode(mock_run, mock_which, indexer):
    mock_which.return_value = "/usr/local/bin/claude"
    indexer.full_rebuild()
    # "deploy crash" matches CosmicForge bug note (phrase: "Deploy crash on production")
    candidates = prefilter(indexer.fts_index, query="deploy crash", top_k=50)
    assert len(candidates) >= 1

    mock_run.return_value = MagicMock(
        returncode=0,
        stdout=json.dumps([
            {"path": candidates[0].path, "relevance": 0.95,
             "reason": "mock top rank"},
        ]),
        stderr="",
    )
    results = rank(query="deploy crash", candidates=candidates, top_k=1)
    assert len(results) == 1
    assert results[0]["relevance"] == 0.95


def test_e2e_full_rebuild_deletes_stale(indexer):
    indexer.full_rebuild()
    # Delete a file
    apps = list((indexer.vault_path / "APP-Dev").glob("*.md"))
    apps[0].unlink()
    stats = indexer.full_rebuild()
    assert stats["indexed"] == 9
