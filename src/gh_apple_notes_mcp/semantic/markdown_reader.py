"""Parse vault markdown files — frontmatter + cleaned body."""
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import yaml


APPLE_NOTES_START = "<!-- APPLE-NOTES-START -->"
APPLE_NOTES_END = "<!-- APPLE-NOTES-END -->"


class MalformedMarkdownError(ValueError):
    """File doesn't have expected F2/F2.5 markdown structure."""


@dataclass
class ParsedNote:
    path: str
    title: str
    folder: str
    tags: list[str] = field(default_factory=list)
    body: str = ""
    body_tags: list[str] = field(default_factory=list)
    classification: dict = field(default_factory=dict)
    mtime: str = ""


def _extract_plaintext_tags(body: str) -> list[str]:
    """Extract #tag / #tag/subtag from body, lowercase + dedupe, preserve order."""
    if not body:
        return []
    seen = []
    for m in re.finditer(r"#([\w/-]+)", body):
        tag = m.group(1).lower()
        if tag not in seen:
            seen.append(tag)
    return seen


def _strip_markers(body: str) -> str:
    """Remove APPLE-NOTES-START/END markers but keep inner content."""
    body = body.replace(APPLE_NOTES_START + "\n", "")
    body = body.replace("\n" + APPLE_NOTES_END, "")
    body = body.replace(APPLE_NOTES_START, "")
    body = body.replace(APPLE_NOTES_END, "")
    return body


def parse_content(content: str, path: str) -> ParsedNote:
    """Parse markdown string. `path` is relative to vault root (for folder derivation)."""
    if not content.startswith("---\n"):
        raise MalformedMarkdownError(f"No frontmatter: {path}")

    parts = content.split("---", 2)
    if len(parts) < 3:
        raise MalformedMarkdownError(f"Incomplete frontmatter: {path}")

    try:
        fm = yaml.safe_load(parts[1])
    except yaml.YAMLError as e:
        raise MalformedMarkdownError(f"Invalid YAML in {path}: {e}")

    if not isinstance(fm, dict):
        raise MalformedMarkdownError(f"Frontmatter not a dict in {path}")

    title = str(fm.get("title") or "Untitled")
    tags = list(fm.get("tags") or [])
    classification = dict(fm.get("classification") or {})

    # Folder: prefer classification, fallback to path
    folder = classification.get("folder")
    if not folder:
        path_parts = Path(path).parts
        folder = path_parts[0] if len(path_parts) > 1 else "Inbox"

    body = _strip_markers(parts[2]).strip()
    body_tags = _extract_plaintext_tags(body)

    return ParsedNote(
        path=path, title=title, folder=folder, tags=tags,
        body=body, body_tags=body_tags,
        classification=classification, mtime="",
    )


def parse_file(file_path: Path, vault_root: Path) -> ParsedNote:
    """Read + parse a vault markdown file. Populate mtime from file stat."""
    rel_path = str(file_path.relative_to(vault_root))
    content = file_path.read_text(encoding="utf-8")
    note = parse_content(content, path=rel_path)
    mtime_ts = file_path.stat().st_mtime
    note.mtime = datetime.fromtimestamp(mtime_ts, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return note
