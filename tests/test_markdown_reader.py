"""Tests for markdown_reader."""
from pathlib import Path

import pytest

from gh_apple_notes_mcp.semantic.markdown_reader import (
    ParsedNote,
    parse_file,
    parse_content,
    MalformedMarkdownError,
)


SAMPLE_F2 = """---
source: apple_notes
note_id: x-coredata://.../p123
title: Shopping list
created: '2026-04-17T09:00:00Z'
modified: '2026-04-17T09:05:00Z'
tags: [user_tag]
classification:
  folder: Personal
  confidence: 0.85
  reasoning: domestic
  likely_sensitive: false
---

# Shopping list

<!-- APPLE-NOTES-START -->
kup chleb
kup mleko
<!-- APPLE-NOTES-END -->

## TODO
- [ ] kupić chleb <!-- rem:AB12 -->

## Powiązane
[[other-note]]
"""


def test_parse_content_extracts_frontmatter():
    p = parse_content(SAMPLE_F2, path="Personal/2026-04-17-shopping.md")
    assert p.title == "Shopping list"
    assert p.folder == "Personal"
    assert p.tags == ["user_tag"]
    assert p.classification["folder"] == "Personal"
    assert p.classification["confidence"] == 0.85


def test_parse_content_extracts_body_without_markers():
    p = parse_content(SAMPLE_F2, path="Personal/f.md")
    assert "kup chleb" in p.body
    assert "<!-- APPLE-NOTES-START -->" not in p.body
    assert "<!-- APPLE-NOTES-END -->" not in p.body


def test_parse_content_preserves_todo_and_powiazane():
    p = parse_content(SAMPLE_F2, path="Personal/f.md")
    assert "## TODO" in p.body
    assert "kupić chleb" in p.body
    assert "## Powiązane" in p.body
    assert "[[other-note]]" in p.body


def test_parse_content_folder_from_path_when_classification_missing():
    content = """---
title: Bare note
---

# Bare note

body text
"""
    p = parse_content(content, path="APP-Dev/2026-04-17-bare.md")
    assert p.folder == "APP-Dev"


def test_parse_content_no_frontmatter_raises():
    with pytest.raises(MalformedMarkdownError):
        parse_content("# no frontmatter\nbody", path="x.md")


def test_parse_content_invalid_yaml_raises():
    bad = """---
invalid: [unclosed
---

body
"""
    with pytest.raises(MalformedMarkdownError):
        parse_content(bad, path="x.md")


def test_parse_file_reads_from_disk(tmp_path):
    f = tmp_path / "test.md"
    f.write_text(SAMPLE_F2)
    p = parse_file(f, vault_root=tmp_path)
    assert p.title == "Shopping list"
    assert p.path == "test.md"


def test_parse_file_path_relative_to_vault(tmp_path):
    (tmp_path / "APP-Dev").mkdir()
    f = tmp_path / "APP-Dev" / "x.md"
    f.write_text(SAMPLE_F2)
    p = parse_file(f, vault_root=tmp_path)
    assert p.path == "APP-Dev/x.md"


def test_parsed_note_mtime_from_stat(tmp_path):
    f = tmp_path / "t.md"
    f.write_text(SAMPLE_F2)
    p = parse_file(f, vault_root=tmp_path)
    assert "T" in p.mtime
    assert p.mtime.endswith("Z")


def test_parse_content_empty_body_ok():
    content = """---
title: Empty
---

# Empty
"""
    p = parse_content(content, path="Inbox/x.md")
    assert p.body.strip() != ""


def test_parse_content_tags_extracted_from_plaintext_body():
    content = """---
title: Bug fix
---

# Bug fix

The bug has #claude #claude/synced tags inline.
"""
    p = parse_content(content, path="x.md")
    assert "claude" in p.body_tags
    assert "claude/synced" in p.body_tags
