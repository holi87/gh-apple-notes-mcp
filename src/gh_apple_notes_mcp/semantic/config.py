"""Config constants for F3 semantic search."""
from pathlib import Path


VAULT_PATH = Path.home() / "Documents" / "Obsidian" / "SecondBrain" / "SecondBrain"
STATE_FILE = VAULT_PATH / "_Reports" / ".fts-state.json"
INDEX_DB = VAULT_PATH / "_Reports" / "fts-index.sqlite"

PREFILTER_TOP_K = 50
SKIP_FOLDERS = frozenset({"_Reports", "_Sensitive-flagged"})
LLM_TIMEOUT_SECONDS = 60
MAX_BODY_CHARS_FOR_LLM = 8000
