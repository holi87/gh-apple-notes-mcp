"""Configuration constants for gh-apple-notes-mcp."""
from pathlib import Path


NOTES_SQLITE_PATH = (
    Path.home()
    / "Library"
    / "Group Containers"
    / "group.com.apple.notes"
    / "NoteStore.sqlite"
)

APPLESCRIPT_TIMEOUT_SECONDS = 10
SQLITE_LOCK_RETRIES = 1
SQLITE_LOCK_RETRY_DELAY_MS = 100

SERVER_NAME = "gh-apple-notes-mcp"
SERVER_VERSION = "0.1.0"

DEFAULT_LIST_LIMIT = 50
