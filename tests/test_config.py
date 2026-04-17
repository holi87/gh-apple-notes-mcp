"""Tests for config constants."""
from pathlib import Path

from gh_apple_notes_mcp import config


def test_notes_sqlite_path():
    p = config.NOTES_SQLITE_PATH
    assert isinstance(p, Path)
    assert p.is_absolute()
    assert "group.com.apple.notes" in str(p)
    assert p.name == "NoteStore.sqlite"


def test_applescript_timeout():
    assert config.APPLESCRIPT_TIMEOUT_SECONDS > 0
    assert config.APPLESCRIPT_TIMEOUT_SECONDS <= 30


def test_sqlite_retry():
    assert config.SQLITE_LOCK_RETRIES >= 1
    assert config.SQLITE_LOCK_RETRY_DELAY_MS > 0


def test_server_info():
    assert config.SERVER_NAME == "gh-apple-notes-mcp"
    assert config.SERVER_VERSION


def test_default_limit():
    assert config.DEFAULT_LIST_LIMIT == 50
