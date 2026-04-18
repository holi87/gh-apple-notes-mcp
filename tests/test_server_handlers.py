"""Tests for MCP server handlers (mocked deps, no stdio)."""
from unittest.mock import MagicMock

import pytest

from gh_apple_notes_mcp.server import build_server_handlers


@pytest.fixture
def handlers():
    reader = MagicMock()
    writer = MagicMock()
    # Default reader responses
    reader.list_notes.return_value = [
        {"id": "uuid-001", "title": "Shopping", "folder": "claude",
         "created": "2026-04-17T09:00:00Z", "modified": "2026-04-17T09:05:00Z",
         "tags": ["claude"], "snippet": "kup chleb"},
        {"id": "uuid-002", "title": "Bug", "folder": "claude",
         "created": "2026-04-17T10:00:00Z", "modified": "2026-04-17T10:30:00Z",
         "tags": ["claude", "claude/synced"], "snippet": "CosmicForge crash"},
    ]
    reader.get_note.return_value = {
        "id": "uuid-001", "title": "Shopping", "body": "kup chleb #claude",
        "folder": "claude", "created": "2026-04-17T09:00:00Z",
        "modified": "2026-04-17T09:05:00Z", "tags": ["claude"],
        "has_attachments": False,
    }
    reader.get_note_html.return_value = "<div>kup chleb #claude</div>"
    reader.get_note_by_title.return_value = None
    reader.list_folders.return_value = [
        {"name": "Notes", "note_count": 0, "is_smart_folder": False},
        {"name": "claude", "note_count": 0, "is_smart_folder": False},
    ]
    # Default writer responses
    writer.create.return_value = {"id": "new-uuid-123"}
    writer.append_tag.return_value = {
        "success": True, "already_present": False, "new_body": "body #tag"
    }
    writer.update_body.return_value = {"success": True}
    writer.delete.return_value = {"success": True}
    return build_server_handlers(reader=reader, writer=writer), reader, writer


@pytest.mark.asyncio
async def test_list_notes(handlers):
    h, reader, _ = handlers
    result = await h["notes.list"]({"folder": "claude"})
    assert len(result) == 2
    reader.list_notes.assert_called_once()


@pytest.mark.asyncio
async def test_list_notes_invalid(handlers):
    h, _, _ = handlers
    with pytest.raises(Exception):
        await h["notes.list"]({"limit": 0})


@pytest.mark.asyncio
async def test_get_note(handlers):
    h, reader, _ = handlers
    result = await h["notes.get"]({"id": "uuid-001"})
    assert result["title"] == "Shopping"
    reader.get_note.assert_called_once_with(id="uuid-001")


@pytest.mark.asyncio
async def test_get_note_missing(handlers):
    from gh_apple_notes_mcp.applescript_reader import NoteNotFoundError
    h, reader, _ = handlers
    reader.get_note.side_effect = NoteNotFoundError("not found")
    with pytest.raises(LookupError):
        await h["notes.get"]({"id": "nope"})


@pytest.mark.asyncio
async def test_get_by_title_found(handlers):
    h, reader, _ = handlers
    reader.get_note_by_title.return_value = {
        "id": "uuid-001", "title": "X", "body": "b", "folder": "f",
        "created": "c", "modified": "m", "tags": [], "has_attachments": False,
    }
    result = await h["notes.get_by_title"]({"title": "X"})
    assert result["id"] == "uuid-001"


@pytest.mark.asyncio
async def test_get_by_title_none(handlers):
    h, _, _ = handlers
    assert await h["notes.get_by_title"]({"title": "nope"}) is None


@pytest.mark.asyncio
async def test_create(handlers):
    h, _, writer = handlers
    result = await h["notes.create"]({"title": "N", "body": "B", "folder": "Notes"})
    assert result["id"] == "new-uuid-123"
    writer.create.assert_called_once_with(title="N", body="B", folder="Notes")


@pytest.mark.asyncio
async def test_append_tag(handlers):
    h, reader, writer = handlers
    result = await h["notes.append_tag"]({"id": "uuid-001", "tag": "claude/synced"})
    reader.get_note_html.assert_called_once_with(id="uuid-001")
    reader.get_note.assert_not_called()
    writer.append_tag.assert_called_once()
    kwargs = writer.append_tag.call_args.kwargs
    assert kwargs["existing_body"] == "<div>kup chleb #claude</div>"
    assert "success" in result


@pytest.mark.asyncio
async def test_delete_rejects_no_confirm(handlers):
    h, _, _ = handlers
    with pytest.raises(ValueError, match="confirm"):
        await h["notes.delete"]({"id": "uuid-001", "confirm": False})


@pytest.mark.asyncio
async def test_delete_with_confirm(handlers):
    h, _, writer = handlers
    result = await h["notes.delete"]({"id": "uuid-001", "confirm": True})
    assert result["success"] is True
    writer.delete.assert_called_once_with(id="uuid-001")


@pytest.mark.asyncio
async def test_list_folders(handlers):
    h, _, _ = handlers
    names = [f["name"] for f in await h["notes.list_folders"]({})]
    assert "claude" in names


@pytest.mark.asyncio
async def test_update_body(handlers):
    h, _, writer = handlers
    result = await h["notes.update_body"]({"id": "uuid-001", "new_body": "new"})
    assert result["success"] is True


@pytest.mark.asyncio
async def test_handle_semantic_search_candidates_mode_empty_vault(handlers, monkeypatch, tmp_path):
    h, _, _ = handlers
    from gh_apple_notes_mcp.semantic import config as cfg
    fake_vault = tmp_path / "vault"
    fake_vault.mkdir()
    (fake_vault / "_Reports").mkdir()
    monkeypatch.setattr(cfg, "VAULT_PATH", fake_vault)
    monkeypatch.setattr(cfg, "STATE_FILE", fake_vault / "_Reports" / ".state.json")
    monkeypatch.setattr(cfg, "INDEX_DB", fake_vault / "_Reports" / "fts.sqlite")

    result = await h["semantic.search"]({"query": "anything", "mode": "candidates"})
    assert result == []


@pytest.mark.asyncio
async def test_handle_semantic_reindex_full_empty(handlers, monkeypatch, tmp_path):
    h, _, _ = handlers
    from gh_apple_notes_mcp.semantic import config as cfg
    fake_vault = tmp_path / "vault"
    fake_vault.mkdir()
    (fake_vault / "_Reports").mkdir()
    monkeypatch.setattr(cfg, "VAULT_PATH", fake_vault)
    monkeypatch.setattr(cfg, "STATE_FILE", fake_vault / "_Reports" / ".state.json")
    monkeypatch.setattr(cfg, "INDEX_DB", fake_vault / "_Reports" / "fts.sqlite")

    result = await h["semantic.reindex"]({"full": True})
    assert result["indexed"] == 0
    assert "errors" in result


@pytest.mark.asyncio
async def test_handle_semantic_search_with_real_notes(handlers, monkeypatch, tmp_path):
    h, _, _ = handlers
    from gh_apple_notes_mcp.semantic import config as cfg
    fake_vault = tmp_path / "vault"
    fake_vault.mkdir()
    (fake_vault / "_Reports").mkdir()
    (fake_vault / "APP-Dev").mkdir()

    # Create one sample note
    (fake_vault / "APP-Dev" / "bug.md").write_text("""---
title: Deploy bug
classification:
  folder: APP-Dev
---

# Deploy bug

<!-- APPLE-NOTES-START -->
Deploy crash on production server.
<!-- APPLE-NOTES-END -->
""")

    monkeypatch.setattr(cfg, "VAULT_PATH", fake_vault)
    monkeypatch.setattr(cfg, "STATE_FILE", fake_vault / "_Reports" / ".state.json")
    monkeypatch.setattr(cfg, "INDEX_DB", fake_vault / "_Reports" / "fts.sqlite")

    result = await h["semantic.search"]({"query": "deploy crash", "mode": "candidates"})
    assert len(result) == 1
    assert result[0]["title"] == "Deploy bug"
