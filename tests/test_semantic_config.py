"""Tests for semantic search config constants."""
from pathlib import Path

from gh_apple_notes_mcp.semantic import config


def test_vault_path_in_obsidian():
    assert isinstance(config.VAULT_PATH, Path)
    assert "SecondBrain" in str(config.VAULT_PATH)


def test_state_file_in_reports():
    assert config.STATE_FILE.parent.name == "_Reports"
    assert config.STATE_FILE.name == ".fts-state.json"


def test_index_db_in_reports():
    assert config.INDEX_DB.parent.name == "_Reports"
    assert config.INDEX_DB.name == "fts-index.sqlite"


def test_prefilter_top_k():
    assert config.PREFILTER_TOP_K == 50


def test_skip_folders():
    assert "_Reports" in config.SKIP_FOLDERS
    assert "_Sensitive-flagged" in config.SKIP_FOLDERS


def test_llm_timeout():
    assert config.LLM_TIMEOUT_SECONDS == 60


def test_max_body_chars():
    assert config.MAX_BODY_CHARS_FOR_LLM == 8000
