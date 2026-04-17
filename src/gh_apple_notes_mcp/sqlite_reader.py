"""Read-only SQLite reader for Apple Notes metadata that AppleScript doesn't expose.

Currently used for native hashtag tags (#claude, #claude/synced, ...) which are
stored as attachment records inside NoteStore.sqlite — AppleScript returns them
as \ufffc placeholders in plaintext, with the actual tag text absent from the
`body` and `plaintext` properties.

Schema reference (macOS 14+):
  ZICCLOUDSYNCINGOBJECT rows with
    ZTYPEUTI1 = 'com.apple.notes.inlinetextattachment.hashtag'
    ZNOTE1    = Z_PK of the owning note
    ZALTTEXT  = '#claude' (visible tag text incl. leading #)

Opened with mode=ro so a concurrently-running Notes.app cannot be disturbed.
"""
from __future__ import annotations

import os
import re
import sqlite3
from pathlib import Path
from typing import Optional


DEFAULT_NOTES_DB = Path(
    os.path.expanduser("~/Library/Group Containers/group.com.apple.notes/NoteStore.sqlite")
)

_NOTE_ID_PK_RE = re.compile(r"/ICNote/p(\d+)$")

_HASHTAG_UTI = "com.apple.notes.inlinetextattachment.hashtag"


def note_pk_from_id(note_id: str) -> Optional[int]:
    """Extract integer Z_PK from an AppleScript note id.

    `x-coredata://<store-uuid>/ICNote/p370` -> 370
    Returns None if the id does not match the expected shape.
    """
    if not note_id:
        return None
    m = _NOTE_ID_PK_RE.search(note_id)
    return int(m.group(1)) if m else None


def fetch_native_tags(db_path: Path = DEFAULT_NOTES_DB) -> dict[int, list[str]]:
    """Return mapping {note_pk: [tag, ...]} using native Apple Notes hashtags.

    Tag names are lowercased and returned without the leading '#', matching the
    format produced by `extract_tags_from_body()`. Duplicates (a note that uses
    the same tag multiple times) are collapsed while preserving first-seen order.

    Returns {} if the database cannot be opened (e.g. path missing, permission
    denied) so the caller can degrade gracefully to AppleScript-only behavior.
    """
    if not db_path.exists():
        return {}
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    except sqlite3.Error:
        return {}
    try:
        cur = conn.execute(
            """
            SELECT ZNOTE1, ZALTTEXT
            FROM ZICCLOUDSYNCINGOBJECT
            WHERE ZTYPEUTI1 = ?
              AND ZNOTE1 IS NOT NULL
              AND ZALTTEXT IS NOT NULL
            """,
            (_HASHTAG_UTI,),
        )
        tags_by_pk: dict[int, list[str]] = {}
        for pk, alt in cur:
            name = alt.lstrip("#").strip().lower()
            if not name:
                continue
            bucket = tags_by_pk.setdefault(pk, [])
            if name not in bucket:
                bucket.append(name)
        return tags_by_pk
    except sqlite3.Error:
        return {}
    finally:
        conn.close()
