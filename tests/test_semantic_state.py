"""Tests for semantic state (JSON with file mtimes)."""
from pathlib import Path

from gh_apple_notes_mcp.semantic.state import load_state, save_state, IndexState


def test_load_missing_returns_default(tmp_path):
    p = tmp_path / "missing.json"
    state = load_state(p)
    assert isinstance(state, IndexState)
    assert state.file_mtimes == {}


def test_save_and_load_round_trip(tmp_path):
    p = tmp_path / "state.json"
    s = IndexState(file_mtimes={"APP-Dev/x.md": 1710000000.5})
    save_state(p, s)
    loaded = load_state(p)
    assert loaded.file_mtimes == {"APP-Dev/x.md": 1710000000.5}


def test_load_corrupt_json_returns_default(tmp_path):
    p = tmp_path / "bad.json"
    p.write_text("{not json")
    state = load_state(p)
    assert state.file_mtimes == {}


def test_load_wrong_schema_returns_default(tmp_path):
    p = tmp_path / "wrong.json"
    p.write_text('{"unexpected": "shape"}')
    state = load_state(p)
    assert state.file_mtimes == {}


def test_save_creates_parent_dir(tmp_path):
    nested = tmp_path / "a" / "b" / "state.json"
    s = IndexState(file_mtimes={"x.md": 1.0})
    save_state(nested, s)
    assert nested.exists()
