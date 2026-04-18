"""Tests for AppleScript reader (subprocess mocked)."""
from unittest.mock import MagicMock, patch

import pytest

from gh_apple_notes_mcp.applescript_reader import (
    AppleScriptReader,
    AppleScriptPermissionError,
    NoteNotFoundError,
    clean_plaintext_body,
    extract_tags_from_body,
)


def test_extract_tags_simple():
    assert extract_tags_from_body("Text #claude more") == ["claude"]


def test_extract_tags_hierarchical():
    tags = extract_tags_from_body("a #claude/synced b #work/urgent")
    assert "claude/synced" in tags
    assert "work/urgent" in tags


def test_extract_tags_dedupe():
    assert extract_tags_from_body("#c #c #c") == ["c"]


def test_extract_tags_empty():
    assert extract_tags_from_body("") == []
    assert extract_tags_from_body("no tags") == []


def test_extract_tags_lowercase():
    assert "claudetag" in extract_tags_from_body("#ClaudeTag")


def test_clean_plaintext_strips_title_duplicate():
    body = "Shopping\nkup chleb\nkup mleko"
    assert clean_plaintext_body(body, "Shopping") == "kup chleb\nkup mleko"


def test_clean_plaintext_keeps_body_when_no_title_duplicate():
    body = "kup chleb\nkup mleko"
    assert clean_plaintext_body(body, "Shopping") == "kup chleb\nkup mleko"


def test_clean_plaintext_collapses_blank_runs():
    body = "Title\n\n\n\n\nline a\n\n\n\nline b"
    assert clean_plaintext_body(body, "Title") == "line a\n\nline b"


def test_clean_plaintext_removes_attachment_placeholder():
    body = "Note\nattachment \uFFFC here"
    assert clean_plaintext_body(body, "Note") == "attachment  here"


def test_clean_plaintext_empty_safe():
    assert clean_plaintext_body("", "T") == ""


@patch("gh_apple_notes_mcp.applescript_reader.subprocess.run")
def test_get_note_html_returns_raw_body(mock_run):
    mock_run.return_value = MagicMock(
        returncode=0,
        stdout="<div><h1>Title</h1></div><div>body</div>\n",
        stderr="",
    )
    r = AppleScriptReader()
    html = r.get_note_html("uuid-1")
    assert html == "<div><h1>Title</h1></div><div>body</div>"


@patch("gh_apple_notes_mcp.applescript_reader.subprocess.run")
def test_get_note_html_missing(mock_run):
    mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
    r = AppleScriptReader()
    with pytest.raises(NoteNotFoundError):
        r.get_note_html("nope")


# Format for mocked osascript list_notes output:
# Each note: id<US>title<US>folder<US>created<US>modified<US>body
# Notes separated by RS (\x1e)
RS = "\x1e"
US = "\x1f"


def _make_list_output(notes: list[dict]) -> str:
    """Build mocked osascript output for list_notes."""
    lines = []
    for n in notes:
        fields = [n["id"], n["title"], n["folder"], n["created"], n["modified"], n["body"]]
        lines.append(US.join(fields))
    return RS.join(lines)


@patch("gh_apple_notes_mcp.applescript_reader.subprocess.run")
def test_list_notes_parses_output(mock_run):
    mock_run.return_value = MagicMock(
        returncode=0,
        stdout=_make_list_output([
            {"id": "uuid-1", "title": "Shopping", "folder": "claude",
             "created": "2026-04-17T09:00:00Z", "modified": "2026-04-17T09:05:00Z",
             "body": "kup chleb #claude"},
            {"id": "uuid-2", "title": "Bug", "folder": "claude",
             "created": "2026-04-17T10:00:00Z", "modified": "2026-04-17T10:30:00Z",
             "body": "CosmicForge crash #claude #claude/synced"},
        ]),
        stderr="",
    )
    r = AppleScriptReader()
    notes = r.list_notes(folder="claude")
    assert len(notes) == 2
    assert notes[0]["id"] == "uuid-1"
    assert notes[0]["title"] == "Shopping"
    assert "claude" in notes[0]["tags"]
    assert "claude/synced" in notes[1]["tags"]


@patch("gh_apple_notes_mcp.applescript_reader.subprocess.run")
def test_list_notes_empty(mock_run):
    mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
    r = AppleScriptReader()
    assert r.list_notes() == []


@patch("gh_apple_notes_mcp.applescript_reader.subprocess.run")
def test_list_notes_permission_denied(mock_run):
    mock_run.return_value = MagicMock(
        returncode=1, stdout="",
        stderr="execution error: Not authorized. (-1743)"
    )
    r = AppleScriptReader()
    with pytest.raises(AppleScriptPermissionError, match="System Settings"):
        r.list_notes()


@patch("gh_apple_notes_mcp.applescript_reader.subprocess.run")
def test_list_notes_snippet_first_100(mock_run):
    long_body = "x" * 200
    mock_run.return_value = MagicMock(
        returncode=0,
        stdout=_make_list_output([
            {"id": "u", "title": "t", "folder": "f",
             "created": "c", "modified": "m", "body": long_body},
        ]),
        stderr="",
    )
    r = AppleScriptReader()
    notes = r.list_notes()
    assert len(notes[0]["snippet"]) == 100


@patch("gh_apple_notes_mcp.applescript_reader.subprocess.run")
def test_get_note_returns_detail(mock_run):
    mock_run.return_value = MagicMock(
        returncode=0,
        stdout=_make_list_output([
            {"id": "uuid-1", "title": "Shopping", "folder": "claude",
             "created": "2026-04-17T09:00:00Z", "modified": "2026-04-17T09:05:00Z",
             "body": "kup chleb #claude"},
        ]),
        stderr="",
    )
    r = AppleScriptReader()
    n = r.get_note("uuid-1")
    assert n["id"] == "uuid-1"
    assert n["body"] == "kup chleb #claude"
    assert "claude" in n["tags"]
    assert n["has_attachments"] is False


@patch("gh_apple_notes_mcp.applescript_reader.subprocess.run")
def test_get_note_not_found(mock_run):
    mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
    r = AppleScriptReader()
    with pytest.raises(NoteNotFoundError):
        r.get_note("does-not-exist")


@patch("gh_apple_notes_mcp.applescript_reader.subprocess.run")
def test_get_note_by_title(mock_run):
    mock_run.return_value = MagicMock(
        returncode=0,
        stdout=_make_list_output([
            {"id": "uuid-1", "title": "Shopping", "folder": "claude",
             "created": "c", "modified": "m", "body": "body"},
        ]),
        stderr="",
    )
    r = AppleScriptReader()
    n = r.get_note_by_title("Shopping")
    assert n["id"] == "uuid-1"


@patch("gh_apple_notes_mcp.applescript_reader.subprocess.run")
def test_get_note_by_title_missing(mock_run):
    mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
    r = AppleScriptReader()
    assert r.get_note_by_title("nope") is None


@patch("gh_apple_notes_mcp.applescript_reader.subprocess.run")
def test_list_folders(mock_run):
    # Folder format: name<US>folder_type (0=normal, 1=smart/system)
    mock_run.return_value = MagicMock(
        returncode=0,
        stdout=f"Notes{US}0{RS}claude{US}0{RS}Work{US}0",
        stderr="",
    )
    r = AppleScriptReader()
    folders = r.list_folders()
    assert len(folders) == 3
    names = [f["name"] for f in folders]
    assert "claude" in names
    for f in folders:
        assert "note_count" in f
        assert "is_smart_folder" in f


@patch("gh_apple_notes_mcp.applescript_reader.subprocess.run")
def test_list_notes_post_hoc_folder_filter(mock_run):
    """Smart Folder filtering: list_notes(folder="claude") keeps notes
    where physical folder matches OR #claude tag appears in body.
    Notes without either are excluded."""
    mock_run.return_value = MagicMock(
        returncode=0,
        stdout=_make_list_output([
            # Note 1: has #claude tag → must be included (Smart Folder match)
            {"id": "id-claude-tag", "title": "Claude Note", "folder": "Notes",
             "created": "2026-04-17T09:00:00Z", "modified": "2026-04-17T09:05:00Z",
             "body": "some content #claude"},
            # Note 2: different tag → must be excluded
            {"id": "id-other-tag", "title": "Other Note", "folder": "Notes",
             "created": "2026-04-17T10:00:00Z", "modified": "2026-04-17T10:30:00Z",
             "body": "some content #other"},
            # Note 3: no tags → must be excluded
            {"id": "id-no-tags", "title": "No Tag Note", "folder": "Notes",
             "created": "2026-04-17T11:00:00Z", "modified": "2026-04-17T11:05:00Z",
             "body": "no tags here"},
        ]),
        stderr="",
    )
    r = AppleScriptReader()
    notes = r.list_notes(folder="claude")
    assert len(notes) == 1
    assert notes[0]["id"] == "id-claude-tag"
    assert "claude" in notes[0]["tags"]


@patch("gh_apple_notes_mcp.applescript_reader.subprocess.run")
def test_list_notes_post_hoc_folder_filter_physical_folder(mock_run):
    """list_notes(folder="Work") keeps notes whose physical folder is "Work",
    even if the note has no #work tag."""
    mock_run.return_value = MagicMock(
        returncode=0,
        stdout=_make_list_output([
            # Note in the correct physical folder — no tag needed
            {"id": "id-work-folder", "title": "Work Note", "folder": "Work",
             "created": "2026-04-17T09:00:00Z", "modified": "2026-04-17T09:05:00Z",
             "body": "meeting notes"},
            # Note in a different folder — excluded
            {"id": "id-personal", "title": "Personal Note", "folder": "Notes",
             "created": "2026-04-17T10:00:00Z", "modified": "2026-04-17T10:30:00Z",
             "body": "personal stuff"},
        ]),
        stderr="",
    )
    r = AppleScriptReader()
    notes = r.list_notes(folder="Work")
    assert len(notes) == 1
    assert notes[0]["id"] == "id-work-folder"


@patch("gh_apple_notes_mcp.applescript_reader.subprocess.run")
def test_list_notes_deduplicates_by_id(mock_run):
    """When the same note id appears twice (e.g. multiple accounts), it's
    returned only once."""
    same_id = "dup-id-123"
    mock_run.return_value = MagicMock(
        returncode=0,
        stdout=_make_list_output([
            {"id": same_id, "title": "Dup Note", "folder": "Notes",
             "created": "2026-04-17T09:00:00Z", "modified": "2026-04-17T09:05:00Z",
             "body": "content"},
            {"id": same_id, "title": "Dup Note", "folder": "Notes",
             "created": "2026-04-17T09:00:00Z", "modified": "2026-04-17T09:05:00Z",
             "body": "content"},
        ]),
        stderr="",
    )
    r = AppleScriptReader()
    notes = r.list_notes()
    assert len(notes) == 1


@patch("gh_apple_notes_mcp.applescript_reader.subprocess.run")
def test_list_notes_excludes_trashed(mock_run):
    """By default (include_trashed=False), notes in Recently Deleted folder
    are excluded. When include_trashed=True, they are included."""
    mock_run.return_value = MagicMock(
        returncode=0,
        stdout=_make_list_output([
            {"id": "id-notes", "title": "In Notes", "folder": "Notes",
             "created": "2026-04-17T09:00:00Z", "modified": "2026-04-17T09:05:00Z",
             "body": "regular note"},
            {"id": "id-work", "title": "In Work", "folder": "Work",
             "created": "2026-04-17T10:00:00Z", "modified": "2026-04-17T10:30:00Z",
             "body": "work note"},
            {"id": "id-trash", "title": "In Trash", "folder": "Recently Deleted",
             "created": "2026-04-17T11:00:00Z", "modified": "2026-04-17T11:05:00Z",
             "body": "deleted note"},
        ]),
        stderr="",
    )
    r = AppleScriptReader()
    # Default: exclude Recently Deleted
    notes = r.list_notes()
    assert len(notes) == 2
    ids = {n["id"] for n in notes}
    assert "id-notes" in ids
    assert "id-work" in ids
    assert "id-trash" not in ids
    # With include_trashed=True: include Recently Deleted
    mock_run.return_value = MagicMock(
        returncode=0,
        stdout=_make_list_output([
            {"id": "id-notes", "title": "In Notes", "folder": "Notes",
             "created": "2026-04-17T09:00:00Z", "modified": "2026-04-17T09:05:00Z",
             "body": "regular note"},
            {"id": "id-work", "title": "In Work", "folder": "Work",
             "created": "2026-04-17T10:00:00Z", "modified": "2026-04-17T10:30:00Z",
             "body": "work note"},
            {"id": "id-trash", "title": "In Trash", "folder": "Recently Deleted",
             "created": "2026-04-17T11:00:00Z", "modified": "2026-04-17T11:05:00Z",
             "body": "deleted note"},
        ]),
        stderr="",
    )
    notes = r.list_notes(include_trashed=True)
    assert len(notes) == 3
    ids = {n["id"] for n in notes}
    assert "id-notes" in ids
    assert "id-work" in ids
    assert "id-trash" in ids
