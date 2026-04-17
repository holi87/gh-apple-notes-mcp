"""Tests for pydantic schemas."""
import pytest
from pydantic import ValidationError

from gh_apple_notes_mcp.schemas import (
    ListNotesInput, GetNoteInput, GetByTitleInput, CreateNoteInput,
    AppendTagInput, UpdateBodyInput, DeleteNoteInput,
    NoteSummary, NoteDetail, FolderInfo,
    SemanticSearchInput,
)


def test_list_notes_defaults():
    inp = ListNotesInput()
    assert inp.folder is None
    assert inp.since is None
    assert inp.limit == 50
    assert inp.include_trashed is False


def test_list_notes_limit_validation():
    with pytest.raises(ValidationError):
        ListNotesInput(limit=0)
    with pytest.raises(ValidationError):
        ListNotesInput(limit=1001)


def test_get_note_required_id():
    with pytest.raises(ValidationError):
        GetNoteInput()
    assert GetNoteInput(id="abc").include_html is False


def test_get_by_title():
    assert GetByTitleInput(title="T").folder is None


def test_create_note_default_folder():
    assert CreateNoteInput(title="T", body="B").folder == "Notes"


def test_append_tag_rejects_hash():
    with pytest.raises(ValidationError):
        AppendTagInput(id="abc", tag="#claude")


def test_append_tag_accepts_slash():
    inp = AppendTagInput(id="abc", tag="claude/synced")
    assert inp.tag == "claude/synced"


def test_delete_requires_confirm():
    with pytest.raises(ValidationError):
        DeleteNoteInput(id="abc")
    assert DeleteNoteInput(id="abc", confirm=True).confirm is True


def test_note_summary():
    s = NoteSummary(id="a", title="T", folder="N",
                    created="2026-04-17T09:00:00Z",
                    modified="2026-04-17T09:00:00Z")
    assert s.tags == []
    assert s.snippet == ""


def test_note_detail_html_default_none():
    d = NoteDetail(id="a", title="T", body="B", folder="N",
                   created="x", modified="y")
    assert d.html is None
    assert d.has_attachments is False


def test_folder_info():
    f = FolderInfo(name="claude", note_count=5, is_smart_folder=True)
    assert f.is_smart_folder is True


def test_semantic_search_default_top_k():
    assert SemanticSearchInput(query="q").top_k == 5


def test_semantic_search_top_k_validation():
    with pytest.raises(ValidationError):
        SemanticSearchInput(query="q", top_k=0)
    with pytest.raises(ValidationError):
        SemanticSearchInput(query="q", top_k=200)


def test_semantic_search_mode_default_candidates():
    from gh_apple_notes_mcp.schemas import SemanticSearchInput
    inp = SemanticSearchInput(query="x")
    assert inp.mode == "candidates"


def test_semantic_search_mode_auto():
    from gh_apple_notes_mcp.schemas import SemanticSearchInput
    inp = SemanticSearchInput(query="x", mode="auto")
    assert inp.mode == "auto"


def test_semantic_search_mode_invalid_raises():
    from gh_apple_notes_mcp.schemas import SemanticSearchInput
    import pytest
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        SemanticSearchInput(query="x", mode="invalid")
