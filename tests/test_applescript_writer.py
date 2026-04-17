"""Tests for AppleScript writer (subprocess mocked)."""
from unittest.mock import MagicMock, patch

import pytest

from gh_apple_notes_mcp.applescript_writer import (
    AppleScriptWriter,
    AppleScriptPermissionError,
    AppleScriptTimeoutError,
    escape_applescript_string,
)


def test_escape_quotes():
    assert escape_applescript_string('say "hi"') == 'say \\"hi\\"'


def test_escape_backslash_first():
    assert escape_applescript_string("path\\to") == "path\\\\to"


def test_escape_newlines():
    assert escape_applescript_string("line1\nline2") == "line1\\nline2"


def test_escape_polish_chars():
    assert escape_applescript_string("ąćęłńóśźż") == "ąćęłńóśźż"


def test_escape_combined():
    r = escape_applescript_string('a\\b "c"\nd')
    assert '\\\\' in r
    assert '\\"' in r
    assert '\\n' in r


@patch("gh_apple_notes_mcp.applescript_writer.subprocess.run")
def test_update_body_success(mock_run):
    mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
    w = AppleScriptWriter()
    w.update_body(id="uuid-123", new_body="hello")
    cmd = mock_run.call_args[0][0]
    assert cmd[0] == "osascript"


@patch("gh_apple_notes_mcp.applescript_writer.subprocess.run")
def test_update_body_permission_denied(mock_run):
    mock_run.return_value = MagicMock(
        returncode=1, stdout="",
        stderr="execution error: Not authorized. (-1743)"
    )
    w = AppleScriptWriter()
    with pytest.raises(AppleScriptPermissionError, match="System Settings"):
        w.update_body(id="uuid", new_body="x")


@patch("gh_apple_notes_mcp.applescript_writer.subprocess.run")
def test_update_body_timeout(mock_run):
    import subprocess as sp
    mock_run.side_effect = sp.TimeoutExpired(cmd="osascript", timeout=10)
    w = AppleScriptWriter()
    with pytest.raises(AppleScriptTimeoutError):
        w.update_body(id="uuid", new_body="x")


@patch("gh_apple_notes_mcp.applescript_writer.subprocess.run")
def test_update_body_escapes_input(mock_run):
    mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
    w = AppleScriptWriter()
    w.update_body(id="uuid", new_body='a "quote" and\nnewline')
    script = mock_run.call_args[0][0][2]
    assert '\\"quote\\"' in script
    assert '\\n' in script


@patch("gh_apple_notes_mcp.applescript_writer.subprocess.run")
def test_append_tag_idempotent_present(mock_run):
    mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
    w = AppleScriptWriter()
    result = w.append_tag(
        id="uuid", tag="claude/synced",
        existing_body="Some text #claude/synced more",
    )
    assert result["already_present"] is True
    assert result["new_body"] == "Some text #claude/synced more"
    mock_run.assert_not_called()


@patch("gh_apple_notes_mcp.applescript_writer.subprocess.run")
def test_append_tag_missing(mock_run):
    mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
    w = AppleScriptWriter()
    result = w.append_tag(id="uuid", tag="claude/synced", existing_body="Text")
    assert result["already_present"] is False
    assert "#claude/synced" in result["new_body"]
    mock_run.assert_called_once()


@patch("gh_apple_notes_mcp.applescript_writer.subprocess.run")
def test_create_note(mock_run):
    mock_run.return_value = MagicMock(returncode=0, stdout="X9F2-ABCD", stderr="")
    w = AppleScriptWriter()
    result = w.create(title="T", body="B", folder="Notes")
    assert result["id"] == "X9F2-ABCD"
    script = mock_run.call_args[0][0][2]
    assert "make new note" in script


@patch("gh_apple_notes_mcp.applescript_writer.subprocess.run")
def test_delete(mock_run):
    mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
    w = AppleScriptWriter()
    w.delete(id="uuid-abc")
    script = mock_run.call_args[0][0][2]
    assert "delete" in script.lower()
    assert "uuid-abc" in script
