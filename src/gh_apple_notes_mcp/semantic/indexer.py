"""Incremental + full rebuild orchestrator for FTS5 index."""
import json
import logging
from dataclasses import dataclass
from pathlib import Path

from gh_apple_notes_mcp.semantic.config import SKIP_FOLDERS
from gh_apple_notes_mcp.semantic.fts_index import FtsIndex
from gh_apple_notes_mcp.semantic.markdown_reader import (
    parse_file, MalformedMarkdownError,
)
from gh_apple_notes_mcp.semantic.state import IndexState, load_state, save_state


logger = logging.getLogger(__name__)


@dataclass
class Indexer:
    vault_path: Path
    state_file: Path
    fts_index: FtsIndex

    def _iter_vault_files(self) -> list[Path]:
        """All *.md files in vault, excluding SKIP_FOLDERS at top level."""
        results = []
        for folder in self.vault_path.iterdir():
            if not folder.is_dir():
                continue
            if folder.name in SKIP_FOLDERS:
                continue
            results.extend(folder.rglob("*.md"))
        return sorted(results)

    def _index_file(self, f: Path) -> bool:
        """Parse + upsert one file. Returns True on success."""
        try:
            note = parse_file(f, vault_root=self.vault_path)
        except MalformedMarkdownError as e:
            logger.warning(f"Skipping malformed {f}: {e}")
            return False
        except OSError as e:
            logger.warning(f"Cannot read {f}: {e}")
            return False

        record = {
            "path": note.path,
            "title": note.title,
            "folder": note.folder,
            "tags": " ".join(note.tags + note.body_tags),
            "body": note.body,
            "classification": json.dumps(note.classification, ensure_ascii=False),
            "mtime": note.mtime,
        }
        self.fts_index.upsert(record)
        return True

    def full_rebuild(self) -> dict:
        """Nuke index + state, re-index everything."""
        if self.fts_index.db_path.exists():
            self.fts_index.db_path.unlink()
        self.fts_index.create_schema()

        stats = {"indexed": 0, "errors": 0}
        new_mtimes: dict[str, float] = {}
        for f in self._iter_vault_files():
            rel = str(f.relative_to(self.vault_path))
            if self._index_file(f):
                stats["indexed"] += 1
                new_mtimes[rel] = f.stat().st_mtime
            else:
                stats["errors"] += 1

        save_state(self.state_file, IndexState(file_mtimes=new_mtimes))
        return stats

    def ensure_fresh(self) -> dict:
        """Incremental update — only changed/new files, delete missing."""
        self.fts_index.create_schema()
        state = load_state(self.state_file)
        old_mtimes = state.file_mtimes
        new_mtimes: dict[str, float] = {}
        stats = {"indexed": 0, "deleted": 0, "errors": 0}

        current_files = {
            str(f.relative_to(self.vault_path)): f
            for f in self._iter_vault_files()
        }

        # Deletions
        for rel in old_mtimes:
            if rel not in current_files:
                self.fts_index.delete(rel)
                stats["deleted"] += 1

        # Updates / inserts
        for rel, f in current_files.items():
            new_m = f.stat().st_mtime
            old_m = old_mtimes.get(rel)
            if old_m is None or new_m > old_m:
                if self._index_file(f):
                    stats["indexed"] += 1
                    new_mtimes[rel] = new_m
                else:
                    stats["errors"] += 1
            else:
                new_mtimes[rel] = old_m

        save_state(self.state_file, IndexState(file_mtimes=new_mtimes))
        return stats
