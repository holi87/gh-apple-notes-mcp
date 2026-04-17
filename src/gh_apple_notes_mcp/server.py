"""MCP server handlers — wires tool calls to AppleScript reader + writer."""
from typing import Any, Awaitable, Callable, Optional

from gh_apple_notes_mcp.applescript_reader import AppleScriptReader
from gh_apple_notes_mcp.applescript_writer import AppleScriptWriter
from gh_apple_notes_mcp.schemas import (
    ListNotesInput, GetNoteInput, GetByTitleInput, CreateNoteInput,
    AppendTagInput, UpdateBodyInput, DeleteNoteInput,
    SemanticSearchInput, SemanticReindexInput,
)
from gh_apple_notes_mcp.semantic import config as semantic_config
from gh_apple_notes_mcp.semantic.fts_index import FtsIndex
from gh_apple_notes_mcp.semantic.indexer import Indexer
from gh_apple_notes_mcp.semantic.search import prefilter
from gh_apple_notes_mcp.semantic.llm_rank import rank


HandlerDict = dict[str, Callable[[dict], Awaitable[Any]]]


def _build_indexer() -> Indexer:
    """Build a fresh Indexer reading config dynamically (for test override)."""
    return Indexer(
        vault_path=semantic_config.VAULT_PATH,
        state_file=semantic_config.STATE_FILE,
        fts_index=FtsIndex(semantic_config.INDEX_DB),
    )


def build_server_handlers(
    reader: AppleScriptReader,
    writer: AppleScriptWriter,
) -> HandlerDict:
    """Build async handlers keyed by MCP tool name."""

    async def handle_list_notes(args: dict) -> list[dict]:
        inp = ListNotesInput(**args)
        return reader.list_notes(
            folder=inp.folder, since=inp.since,
            limit=inp.limit, include_trashed=inp.include_trashed,
        )

    async def handle_get_note(args: dict) -> dict:
        inp = GetNoteInput(**args)
        return reader.get_note(id=inp.id)

    async def handle_get_by_title(args: dict) -> Optional[dict]:
        inp = GetByTitleInput(**args)
        return reader.get_note_by_title(title=inp.title, folder=inp.folder)

    async def handle_create(args: dict) -> dict:
        inp = CreateNoteInput(**args)
        return writer.create(title=inp.title, body=inp.body, folder=inp.folder)

    async def handle_append_tag(args: dict) -> dict:
        inp = AppendTagInput(**args)
        existing = reader.get_note(id=inp.id)
        return writer.append_tag(
            id=inp.id, tag=inp.tag, existing_body=existing["body"]
        )

    async def handle_update_body(args: dict) -> dict:
        inp = UpdateBodyInput(**args)
        return writer.update_body(id=inp.id, new_body=inp.new_body)

    async def handle_delete(args: dict) -> dict:
        inp = DeleteNoteInput(**args)
        if not inp.confirm:
            raise ValueError("confirm=true required for delete")
        return writer.delete(id=inp.id)

    async def handle_list_folders(args: dict) -> list[dict]:
        return reader.list_folders()

    async def handle_semantic_search(args: dict) -> Any:
        inp = SemanticSearchInput(**args)
        indexer = _build_indexer()
        indexer.ensure_fresh()
        candidates = prefilter(
            indexer.fts_index,
            query=inp.query,
            top_k=semantic_config.PREFILTER_TOP_K,
            filter_folder=inp.filter_folder,
        )
        if inp.mode == "candidates":
            return [
                {
                    "path": c.path, "title": c.title, "folder": c.folder,
                    "tags": c.tags, "body": c.body,
                    "classification": c.classification, "mtime": c.mtime,
                }
                for c in candidates
            ]
        # mode == "auto"
        return rank(query=inp.query, candidates=candidates, top_k=inp.top_k)

    async def handle_semantic_reindex(args: dict) -> dict:
        inp = SemanticReindexInput(**args)
        indexer = _build_indexer()
        if inp.full:
            return indexer.full_rebuild()
        return indexer.ensure_fresh()

    return {
        "notes.list": handle_list_notes,
        "notes.get": handle_get_note,
        "notes.get_by_title": handle_get_by_title,
        "notes.create": handle_create,
        "notes.append_tag": handle_append_tag,
        "notes.update_body": handle_update_body,
        "notes.delete": handle_delete,
        "notes.list_folders": handle_list_folders,
        "semantic.search": handle_semantic_search,
        "semantic.reindex": handle_semantic_reindex,
    }
