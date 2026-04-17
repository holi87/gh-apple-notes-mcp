"""State management for F3 incremental indexing."""
import json
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class IndexState:
    file_mtimes: dict[str, float] = field(default_factory=dict)


def load_state(path: Path) -> IndexState:
    """Load state from JSON file. Missing/corrupt → empty default."""
    if not path.exists():
        return IndexState()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return IndexState()
    if not isinstance(raw, dict):
        return IndexState()
    mtimes = raw.get("file_mtimes")
    if not isinstance(mtimes, dict):
        return IndexState()
    return IndexState(file_mtimes={str(k): float(v) for k, v in mtimes.items()})


def save_state(path: Path, state: IndexState) -> None:
    """Persist state, creating parent dirs as needed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"file_mtimes": state.file_mtimes}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
