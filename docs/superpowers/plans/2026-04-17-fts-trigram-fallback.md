# v0.2 FTS5 Trigram Fallback Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Dodać substring search fallback do `semantic.search` przez drugi FTS5 indeks (trigram tokenizer). Prefix-first; gdy <top_k wyników, dorzuć deduplicated trigram matches z polem `match_type`. Auto-migration przy pierwszym search.

**Architecture:** Single-module change w `fts_index.py`. Drugi virtual table `fts_trigram` obok istniejącej `fts`. Dual-write w `upsert`/`delete`. Publiczny `search()` z fill-to-top_k fallback. Lazy migration dla istniejących baz v0.1.

**Tech Stack:** Python 3.10+, SQLite3 ≥3.34 (trigram tokenizer, bundled z macOS 13+), pytest. Zero nowych deps.

**Spec:** `docs/superpowers/specs/2026-04-17-fts-trigram-fallback-design.md`

---

## File Structure

**Modify:**
- `src/gh_apple_notes_mcp/semantic/fts_index.py` — dodaj drugi table, dual-write, nowy search z fallback, lazy migration.
- `src/gh_apple_notes_mcp/semantic/indexer.py:full_rebuild` — drop/rebuild works via db_path unlink (already does it); no change needed, verified in Task 6.
- `tests/test_fts_index.py` — update 2-3 assertions dla nowego schema count + response shape.
- `README.md` — krótka nota "What's new in v0.2".
- `pyproject.toml` — bump version `0.1.0` → `0.2.0`.

**Create:**
- `tests/test_fts_trigram.py` — trigram-specific unit tests.
- `tests/test_fts_search_fallback.py` — fallback integration tests.
- `tests/test_fts_migration.py` — lazy migration + graceful degradation.

---

## Task 1: Dodaj schema dla `fts_trigram` + test create_schema

**Files:**
- Modify: `src/gh_apple_notes_mcp/semantic/fts_index.py` (lines 8-16, SCHEMA_SQL constant)
- Modify: `tests/test_fts_index.py` (add one assertion)

- [ ] **Step 1: Write failing test for 2-table schema**

Add to `tests/test_fts_index.py` after existing `test_create_schema`:

```python
def test_create_schema_creates_both_fts_and_trigram_tables(tmp_path):
    import sqlite3
    db = tmp_path / "fts.sqlite"
    idx = FtsIndex(db)
    idx.create_schema()
    with sqlite3.connect(db) as conn:
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()
    names = [r[0] for r in rows]
    assert "fts" in names
    assert "fts_trigram" in names
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /Users/grzegorzholak/Desktop/gh-apple-notes-mcp
source .venv/bin/activate
pytest tests/test_fts_index.py::test_create_schema_creates_both_fts_and_trigram_tables -v
```

Expected: FAIL with `assert "fts_trigram" in names`.

- [ ] **Step 3: Update SCHEMA_SQL**

Replace existing `SCHEMA_SQL` constant in `src/gh_apple_notes_mcp/semantic/fts_index.py`:

```python
SCHEMA_SQL = """
CREATE VIRTUAL TABLE IF NOT EXISTS fts USING fts5(
    path UNINDEXED,
    title,
    folder UNINDEXED,
    tags,
    body,
    classification UNINDEXED,
    mtime UNINDEXED,
    tokenize = 'unicode61 remove_diacritics 2'
);

CREATE VIRTUAL TABLE IF NOT EXISTS fts_trigram USING fts5(
    path UNINDEXED,
    title,
    folder UNINDEXED,
    tags,
    body,
    tokenize = 'trigram'
);
"""
```

Also update the `create_schema` method to use `executescript` (so both `CREATE` statements run):

```python
def create_schema(self) -> None:
    with self._connect() as conn:
        conn.executescript(SCHEMA_SQL)
```

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest tests/test_fts_index.py::test_create_schema_creates_both_fts_and_trigram_tables -v
```

Expected: PASS.

- [ ] **Step 5: Run full existing suite to verify no regressions**

```bash
pytest tests/test_fts_index.py -q
```

Expected: all existing tests pass + 1 new = green.

- [ ] **Step 6: Commit**

```bash
git add src/gh_apple_notes_mcp/semantic/fts_index.py tests/test_fts_index.py
git commit -m "feat(fts): add fts_trigram table to SCHEMA_SQL"
```

---

## Task 2: TDD dual-write w `upsert` + `delete`

**Files:**
- Modify: `src/gh_apple_notes_mcp/semantic/fts_index.py` (upsert + delete methods)
- Create: `tests/test_fts_trigram.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_fts_trigram.py`:

```python
"""Tests for FTS5 trigram table dual-write behavior."""
import sqlite3
from pathlib import Path

import pytest

from gh_apple_notes_mcp.semantic.fts_index import FtsIndex


def _row(path: str, title: str = "T", body: str = "body content") -> dict:
    return {
        "path": path,
        "title": title,
        "folder": "Ideas",
        "tags": "claude",
        "body": body,
        "classification": '{"folder":"Ideas","confidence":0.9}',
        "mtime": "2026-04-17T09:00:00Z",
    }


def test_upsert_writes_to_both_tables(tmp_path):
    idx = FtsIndex(tmp_path / "fts.sqlite")
    idx.create_schema()
    idx.upsert(_row("Ideas/x.md", title="X", body="microcosmos content"))
    with sqlite3.connect(tmp_path / "fts.sqlite") as conn:
        fts_count = conn.execute("SELECT COUNT(*) FROM fts").fetchone()[0]
        tri_count = conn.execute("SELECT COUNT(*) FROM fts_trigram").fetchone()[0]
    assert fts_count == 1
    assert tri_count == 1


def test_upsert_replaces_in_both_tables(tmp_path):
    idx = FtsIndex(tmp_path / "fts.sqlite")
    idx.create_schema()
    idx.upsert(_row("Ideas/x.md", title="first"))
    idx.upsert(_row("Ideas/x.md", title="second"))
    with sqlite3.connect(tmp_path / "fts.sqlite") as conn:
        fts_count = conn.execute("SELECT COUNT(*) FROM fts").fetchone()[0]
        tri_count = conn.execute("SELECT COUNT(*) FROM fts_trigram").fetchone()[0]
    assert fts_count == 1
    assert tri_count == 1


def test_delete_removes_from_both_tables(tmp_path):
    idx = FtsIndex(tmp_path / "fts.sqlite")
    idx.create_schema()
    idx.upsert(_row("Ideas/x.md"))
    idx.upsert(_row("Ideas/y.md"))
    idx.delete("Ideas/x.md")
    with sqlite3.connect(tmp_path / "fts.sqlite") as conn:
        fts_paths = [r[0] for r in conn.execute("SELECT path FROM fts").fetchall()]
        tri_paths = [r[0] for r in conn.execute("SELECT path FROM fts_trigram").fetchall()]
    assert fts_paths == ["Ideas/y.md"]
    assert tri_paths == ["Ideas/y.md"]
```

- [ ] **Step 2: Run tests to verify failure**

```bash
pytest tests/test_fts_trigram.py -v
```

Expected: 3 failures (fts_trigram has 0 rows — upsert nie dotyka nowego table).

- [ ] **Step 3: Update `upsert` and `delete` for dual-write**

Replace `upsert` and `delete` in `src/gh_apple_notes_mcp/semantic/fts_index.py`:

```python
def upsert(self, record: dict) -> None:
    """Insert or replace a note record into both fts and fts_trigram tables."""
    with self._connect() as conn:
        conn.execute("DELETE FROM fts WHERE path = ?", (record["path"],))
        conn.execute("DELETE FROM fts_trigram WHERE path = ?", (record["path"],))
        conn.execute(
            "INSERT INTO fts (path, title, folder, tags, body, classification, mtime) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                record["path"],
                _normalize(record["title"]),
                record["folder"],
                _normalize(record["tags"]),
                _normalize(record["body"]),
                record["classification"],
                record["mtime"],
            ),
        )
        conn.execute(
            "INSERT INTO fts_trigram (path, title, folder, tags, body) "
            "VALUES (?, ?, ?, ?, ?)",
            (
                record["path"],
                _normalize(record["title"]),
                record["folder"],
                _normalize(record["tags"]),
                _normalize(record["body"]),
            ),
        )


def delete(self, path: str) -> None:
    with self._connect() as conn:
        conn.execute("DELETE FROM fts WHERE path = ?", (path,))
        conn.execute("DELETE FROM fts_trigram WHERE path = ?", (path,))
```

- [ ] **Step 4: Run tests to verify pass**

```bash
pytest tests/test_fts_trigram.py -v
```

Expected: 3 passed.

- [ ] **Step 5: Run full existing suite — no regressions**

```bash
pytest tests/ -q
```

Expected: all existing + 4 new (1 from Task 1 + 3 from Task 2) pass.

- [ ] **Step 6: Commit**

```bash
git add src/gh_apple_notes_mcp/semantic/fts_index.py tests/test_fts_trigram.py
git commit -m "feat(fts): dual-write upsert and delete to fts_trigram"
```

---

## Task 3: TDD `_escape_trigram_query` helper

**Files:**
- Modify: `src/gh_apple_notes_mcp/semantic/fts_index.py` (add function)
- Modify: `tests/test_fts_trigram.py` (add tests)

- [ ] **Step 1: Write failing tests**

Append to `tests/test_fts_trigram.py`:

```python
from gh_apple_notes_mcp.semantic.fts_index import _escape_trigram_query


def test_escape_trigram_single_word():
    assert _escape_trigram_query("cosmos") == '"cosmos"'


def test_escape_trigram_multi_word_and():
    result = _escape_trigram_query("cosmos test")
    assert result == '"cosmos" AND "test"'


def test_escape_trigram_too_short_returns_empty():
    assert _escape_trigram_query("ab") == ""
    assert _escape_trigram_query("a") == ""
    assert _escape_trigram_query("") == ""


def test_escape_trigram_whitespace_only_returns_empty():
    assert _escape_trigram_query("   ") == ""


def test_escape_trigram_escapes_embedded_double_quote():
    # " becomes "" inside phrase per FTS5 spec
    assert _escape_trigram_query('he"llo') == '"he""llo"'


def test_escape_trigram_normalizes_polish_diacritics():
    # łódź → lodz (transliteration + NFD fold)
    assert _escape_trigram_query("łódź") == '"lodz"'
```

- [ ] **Step 2: Run tests to verify failure**

```bash
pytest tests/test_fts_trigram.py -v -k "escape"
```

Expected: `ImportError` — function not defined.

- [ ] **Step 3: Add `_escape_trigram_query`**

Add to `src/gh_apple_notes_mcp/semantic/fts_index.py` right after existing `_escape_fts5_query` function:

```python
def _escape_trigram_query(query: str) -> str:
    """Wrap tokens as phrase-match (no prefix *) for trigram tokenizer.

    Trigram requires ≥3 chars total after normalization — shorter queries
    return empty string (caller skips trigram stage).
    """
    normalized = _normalize(query)
    if len(normalized.strip()) < 3:
        return ""
    tokens = normalized.split()
    if not tokens:
        return ""
    escaped = []
    for t in tokens:
        safe = t.replace('"', '""')
        escaped.append(f'"{safe}"')
    return " AND ".join(escaped)
```

- [ ] **Step 4: Run tests — expect PASS**

```bash
pytest tests/test_fts_trigram.py -v -k "escape"
```

Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add src/gh_apple_notes_mcp/semantic/fts_index.py tests/test_fts_trigram.py
git commit -m "feat(fts): add _escape_trigram_query helper"
```

---

## Task 4: Refactor `search` — extract `_prefix_search` + add `_trigram_search`

**Files:**
- Modify: `src/gh_apple_notes_mcp/semantic/fts_index.py` (extract existing search logic → `_prefix_search`, add `_trigram_search`)

This task refactors **without** adding fallback logic. Public `search()` still returns only prefix results at this stage, but internally delegates to private helper. Task 5 adds the fallback on top.

- [ ] **Step 1: Write test for `_trigram_search` directly (integration)**

Append to `tests/test_fts_trigram.py`:

```python
def test_trigram_search_finds_substring_match(tmp_path):
    idx = FtsIndex(tmp_path / "fts.sqlite")
    idx.create_schema()
    idx.upsert(_row("Ideas/a.md", title="microcosmos", body="nothing here"))
    idx.upsert(_row("Ideas/b.md", title="unrelated", body="zero overlap"))
    # Call private method directly
    results = idx._trigram_search("cosmos", limit=10)
    paths = [r["path"] for r in results]
    assert "Ideas/a.md" in paths
    assert "Ideas/b.md" not in paths


def test_trigram_search_respects_filter_folder(tmp_path):
    idx = FtsIndex(tmp_path / "fts.sqlite")
    idx.create_schema()
    idx.upsert(_row("Ideas/a.md", title="microcosmos"))
    idx.upsert({
        "path": "Work/b.md", "title": "microcosmos", "folder": "Work",
        "tags": "", "body": "body", "classification": "{}",
        "mtime": "2026-04-17T09:00:00Z",
    })
    results = idx._trigram_search("cosmos", limit=10, filter_folder="Ideas")
    paths = [r["path"] for r in results]
    assert paths == ["Ideas/a.md"]


def test_trigram_search_empty_query_returns_empty(tmp_path):
    idx = FtsIndex(tmp_path / "fts.sqlite")
    idx.create_schema()
    idx.upsert(_row("Ideas/a.md"))
    assert idx._trigram_search("", limit=10) == []
    assert idx._trigram_search("ab", limit=10) == []  # <3 chars


def test_trigram_search_returns_classification_and_mtime_via_join(tmp_path):
    idx = FtsIndex(tmp_path / "fts.sqlite")
    idx.create_schema()
    idx.upsert(_row("Ideas/a.md", title="microcosmos"))
    results = idx._trigram_search("cosmos", limit=10)
    assert len(results) == 1
    r = results[0]
    assert r["classification"] == '{"folder":"Ideas","confidence":0.9}'
    assert r["mtime"] == "2026-04-17T09:00:00Z"
```

- [ ] **Step 2: Run — expect FAIL**

```bash
pytest tests/test_fts_trigram.py -v -k "trigram_search"
```

Expected: `AttributeError: 'FtsIndex' object has no attribute '_trigram_search'`.

- [ ] **Step 3: Refactor `search` — add private helpers**

In `src/gh_apple_notes_mcp/semantic/fts_index.py` replace the public `search()` method with two private helpers and a temporary public `search` that delegates to `_prefix_search`:

```python
def _prefix_search(
    self,
    query: str,
    limit: int = 50,
    filter_folder: Optional[str] = None,
) -> list[dict]:
    """BM25-ranked prefix-match search on main fts table."""
    if not query.strip():
        return []
    escaped = _escape_fts5_query(query)
    if not escaped:
        return []
    sql = (
        "SELECT path, title, folder, tags, body, classification, mtime "
        "FROM fts WHERE fts MATCH ? "
    )
    params: list = [escaped]
    if filter_folder:
        sql += "AND folder = ? "
        params.append(filter_folder)
    sql += "ORDER BY rank LIMIT ?"
    params.append(limit)
    with self._connect() as conn:
        rows = conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]


def _trigram_search(
    self,
    query: str,
    limit: int = 50,
    filter_folder: Optional[str] = None,
) -> list[dict]:
    """BM25-ranked trigram substring search, joined with fts for classification/mtime."""
    if not query.strip():
        return []
    escaped = _escape_trigram_query(query)
    if not escaped:
        return []
    sql = (
        "SELECT ftr.path AS path, ftr.title AS title, ftr.folder AS folder, "
        "       ftr.tags AS tags, ftr.body AS body, "
        "       f.classification AS classification, f.mtime AS mtime "
        "FROM fts_trigram ftr "
        "LEFT JOIN fts f ON f.path = ftr.path "
        "WHERE fts_trigram MATCH ? "
    )
    params: list = [escaped]
    if filter_folder:
        sql += "AND ftr.folder = ? "
        params.append(filter_folder)
    sql += "ORDER BY ftr.rank LIMIT ?"
    params.append(limit)
    with self._connect() as conn:
        rows = conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]


def search(
    self,
    query: str,
    limit: int = 50,
    filter_folder: Optional[str] = None,
) -> list[dict]:
    """BM25-ranked full-text search (prefix-only at this stage; Task 5 adds fallback)."""
    return self._prefix_search(query, limit, filter_folder)
```

- [ ] **Step 4: Run new tests — expect PASS**

```bash
pytest tests/test_fts_trigram.py -v -k "trigram_search"
```

Expected: 4 passed.

- [ ] **Step 5: Run full suite — no regressions on existing prefix-search tests**

```bash
pytest tests/ -q
```

Expected: all previous + all new pass.

- [ ] **Step 6: Commit**

```bash
git add src/gh_apple_notes_mcp/semantic/fts_index.py tests/test_fts_trigram.py
git commit -m "refactor(fts): extract _prefix_search + add _trigram_search helpers"
```

---

## Task 5: TDD fallback logic w public `search()`

**Files:**
- Modify: `src/gh_apple_notes_mcp/semantic/fts_index.py` (rewrite public `search`)
- Create: `tests/test_fts_search_fallback.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_fts_search_fallback.py`:

```python
"""Tests for FtsIndex.search() prefix-first + trigram-fallback behavior."""
from pathlib import Path

from gh_apple_notes_mcp.semantic.fts_index import FtsIndex


def _row(path: str, title: str = "T", body: str = "body", folder: str = "Ideas") -> dict:
    return {
        "path": path, "title": title, "folder": folder,
        "tags": "claude", "body": body,
        "classification": '{"folder":"' + folder + '","confidence":0.9}',
        "mtime": "2026-04-17T09:00:00Z",
    }


def test_prefix_match_tags_results_with_match_type_prefix(tmp_path):
    idx = FtsIndex(tmp_path / "fts.sqlite")
    idx.create_schema()
    idx.upsert(_row("Ideas/a.md", title="cosmos notes"))
    results = idx.search("cosmos", limit=5)
    assert len(results) == 1
    assert results[0]["match_type"] == "prefix"


def test_fallback_fills_to_top_k_with_trigram_matches(tmp_path):
    idx = FtsIndex(tmp_path / "fts.sqlite")
    idx.create_schema()
    # "cosmos" prefix-matches title exactly
    idx.upsert(_row("Ideas/prefix.md", title="cosmos"))
    # "microcosmos" does NOT prefix-match "cosmos" but contains it as substring
    idx.upsert(_row("Ideas/sub1.md", title="microcosmos"))
    idx.upsert(_row("Ideas/sub2.md", title="macrocosmos"))
    idx.upsert(_row("Ideas/unrelated.md", title="unrelated"))
    results = idx.search("cosmos", limit=5)
    paths = [r["path"] for r in results]
    types = [r["match_type"] for r in results]
    assert "Ideas/prefix.md" in paths
    assert "Ideas/sub1.md" in paths
    assert "Ideas/sub2.md" in paths
    assert "Ideas/unrelated.md" not in paths
    # Prefix match comes first
    assert types[0] == "prefix"
    assert all(t == "trigram" for t in types[1:])


def test_fallback_dedup_does_not_include_path_already_in_prefix(tmp_path):
    idx = FtsIndex(tmp_path / "fts.sqlite")
    idx.create_schema()
    # "cosmos" matches as prefix in title AND trigram substring in body
    idx.upsert(_row("Ideas/a.md", title="cosmos start", body="microcosmos embedded"))
    results = idx.search("cosmos", limit=5)
    paths = [r["path"] for r in results]
    # Same path should appear ONCE, tagged as prefix
    assert paths.count("Ideas/a.md") == 1
    assert results[0]["match_type"] == "prefix"


def test_fallback_not_triggered_when_prefix_fills_top_k(tmp_path):
    idx = FtsIndex(tmp_path / "fts.sqlite")
    idx.create_schema()
    for i in range(5):
        idx.upsert(_row(f"Ideas/{i}.md", title="cosmos note"))
    # Also add substring-only match that would appear if fallback ran
    idx.upsert(_row("Ideas/substr.md", title="microcosmos"))
    results = idx.search("cosmos", limit=5)
    assert len(results) == 5
    assert all(r["match_type"] == "prefix" for r in results)
    assert "Ideas/substr.md" not in [r["path"] for r in results]


def test_empty_query_returns_empty_list(tmp_path):
    idx = FtsIndex(tmp_path / "fts.sqlite")
    idx.create_schema()
    idx.upsert(_row("Ideas/a.md"))
    assert idx.search("", limit=5) == []
    assert idx.search("   ", limit=5) == []


def test_filter_folder_applied_to_both_stages(tmp_path):
    idx = FtsIndex(tmp_path / "fts.sqlite")
    idx.create_schema()
    idx.upsert(_row("Ideas/a.md", title="cosmos", folder="Ideas"))
    idx.upsert(_row("Work/b.md", title="microcosmos", folder="Work"))
    results = idx.search("cosmos", limit=5, filter_folder="Ideas")
    paths = [r["path"] for r in results]
    assert paths == ["Ideas/a.md"]


def test_polish_diacritics_work_across_both_stages(tmp_path):
    idx = FtsIndex(tmp_path / "fts.sqlite")
    idx.create_schema()
    # Title uses Polish diacritics; query uses ASCII
    idx.upsert(_row("Ideas/a.md", title="łódź podróże"))
    idx.upsert(_row("Ideas/b.md", body="opis zawiera slowo podlodzie"))
    results = idx.search("lodz", limit=5)
    paths = [r["path"] for r in results]
    assert "Ideas/a.md" in paths  # prefix match (lodz is prefix of lodz)
    # Both should be findable via normalization
```

- [ ] **Step 2: Run — expect FAIL**

```bash
pytest tests/test_fts_search_fallback.py -v
```

Expected: most tests fail with `KeyError: 'match_type'` or missing fallback results.

- [ ] **Step 3: Rewrite public `search()` with fallback logic**

Replace the current stub public `search()` in `fts_index.py`:

```python
def search(
    self,
    query: str,
    limit: int = 50,
    filter_folder: Optional[str] = None,
) -> list[dict]:
    """BM25-ranked search with prefix-first + trigram-fallback.

    Returns list of dicts with match_type = "prefix" | "trigram".
    Prefix matches come first (sorted by BM25), then trigram fills up to `limit`
    (dedup'd by path). Trigram stage skipped if <3 chars or already at limit.
    """
    self._ensure_trigram_table_exists()

    results = self._prefix_search(query, limit, filter_folder)
    for r in results:
        r["match_type"] = "prefix"

    if len(results) >= limit:
        return results

    seen_paths = {r["path"] for r in results}
    trigram_rows = self._trigram_search(query, limit, filter_folder)
    for r in trigram_rows:
        if r["path"] in seen_paths:
            continue
        r["match_type"] = "trigram"
        results.append(r)
        seen_paths.add(r["path"])
        if len(results) >= limit:
            break
    return results
```

Also add the stub `_ensure_trigram_table_exists` (full implementation in Task 6):

```python
def _ensure_trigram_table_exists(self) -> None:
    """No-op placeholder — Task 6 implements lazy migration. Schema already creates
    fts_trigram in fresh DBs, so this only matters for upgraded v0.1 databases."""
    pass
```

- [ ] **Step 4: Run fallback tests — expect PASS**

```bash
pytest tests/test_fts_search_fallback.py -v
```

Expected: 7 passed.

- [ ] **Step 5: Run full suite**

```bash
pytest tests/ -q
```

Expected: existing prefix-search tests now also have `match_type` in result — if any existing test asserts exact shape (not specific fields), may fail. Check Task 7 will fix those.

**Note:** If `tests/test_fts_index.py::test_upsert_and_search` fails because it now sees `match_type`, proceed to Step 6 regardless — Task 7 handles it. If any OTHER test fails, stop and investigate.

- [ ] **Step 6: Commit**

```bash
git add src/gh_apple_notes_mcp/semantic/fts_index.py tests/test_fts_search_fallback.py
git commit -m "feat(fts): prefix-first search with trigram fill-to-top_k fallback"
```

---

## Task 6: TDD lazy migration `_ensure_trigram_table_exists`

**Files:**
- Modify: `src/gh_apple_notes_mcp/semantic/fts_index.py` (replace stub with full migration)
- Create: `tests/test_fts_migration.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_fts_migration.py`:

```python
"""Tests for lazy migration of v0.1 databases (single fts table) to v0.2."""
import sqlite3
from pathlib import Path
from unittest.mock import patch

import pytest

from gh_apple_notes_mcp.semantic.fts_index import FtsIndex


def _create_v01_database(db_path: Path):
    """Simulate a v0.1 database with only the main fts table populated."""
    with sqlite3.connect(db_path) as conn:
        conn.executescript("""
            CREATE VIRTUAL TABLE fts USING fts5(
                path UNINDEXED, title, folder UNINDEXED, tags, body,
                classification UNINDEXED, mtime UNINDEXED,
                tokenize = 'unicode61 remove_diacritics 2'
            );
        """)
        conn.execute(
            "INSERT INTO fts (path, title, folder, tags, body, classification, mtime) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("Ideas/legacy.md", "microcosmos", "Ideas", "",
             "old content", "{}", "2026-01-01T00:00:00Z"),
        )


def test_lazy_build_creates_trigram_from_existing_fts(tmp_path):
    db = tmp_path / "fts.sqlite"
    _create_v01_database(db)
    idx = FtsIndex(db)
    # First search triggers migration
    results = idx.search("cosmos", limit=5)
    # Verify trigram table now exists and has row
    with sqlite3.connect(db) as conn:
        names = [r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()]
        tri_count = conn.execute("SELECT COUNT(*) FROM fts_trigram").fetchone()[0]
    assert "fts_trigram" in names
    assert tri_count == 1
    # And the substring match works
    paths = [r["path"] for r in results]
    assert "Ideas/legacy.md" in paths


def test_lazy_build_idempotent_second_call_noop(tmp_path):
    db = tmp_path / "fts.sqlite"
    _create_v01_database(db)
    idx = FtsIndex(db)
    idx.search("cosmos", limit=5)  # migrates
    idx.search("cosmos", limit=5)  # should NOT re-copy
    with sqlite3.connect(db) as conn:
        tri_count = conn.execute("SELECT COUNT(*) FROM fts_trigram").fetchone()[0]
    assert tri_count == 1  # still 1, not 2


def test_lazy_build_skipped_when_fresh_db(tmp_path):
    """Fresh db (created_schema) already has fts_trigram — migration is no-op."""
    idx = FtsIndex(tmp_path / "fts.sqlite")
    idx.create_schema()
    # Should not raise or duplicate
    idx._ensure_trigram_table_exists()
    idx._ensure_trigram_table_exists()


def test_trigram_unavailable_graceful_degradation(tmp_path):
    """If SQLite build lacks trigram tokenizer, search falls back to prefix-only
    without crashing."""
    db = tmp_path / "fts.sqlite"
    _create_v01_database(db)
    idx = FtsIndex(db)

    # Patch executescript to raise the specific error the trigram tokenizer would raise
    real_connect = idx._connect
    def connect_with_broken_trigram():
        conn = real_connect()
        original_execute = conn.execute
        original_executescript = conn.executescript

        def fake_executescript(sql):
            if "trigram" in sql.lower():
                raise sqlite3.OperationalError("no such tokenizer: trigram")
            return original_executescript(sql)

        conn.executescript = fake_executescript
        return conn

    with patch.object(idx, "_connect", connect_with_broken_trigram):
        # Should NOT raise — logs warning and continues
        results = idx.search("cosmos", limit=5)
        # Prefix-only (no trigram fallback available)
        # "cosmos" is not a prefix of "microcosmos" — so 0 results here
        assert results == []
```

- [ ] **Step 2: Run — expect FAIL**

```bash
pytest tests/test_fts_migration.py -v
```

Expected: migration tests fail — `fts_trigram` not created.

- [ ] **Step 3: Replace `_ensure_trigram_table_exists` with real implementation**

In `src/gh_apple_notes_mcp/semantic/fts_index.py`, replace the stub with:

```python
def _ensure_trigram_table_exists(self) -> None:
    """Lazy-build fts_trigram from existing fts on v0.1→v0.2 upgrade.

    Idempotent: checks sqlite_master before creating. Graceful degradation
    if SQLite build lacks trigram tokenizer (logs warning, returns).
    """
    with self._connect() as conn:
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='fts_trigram'"
        ).fetchone()
        if row:
            return
        try:
            conn.executescript(SCHEMA_SQL)
            copied = conn.execute(
                "INSERT INTO fts_trigram (path, title, folder, tags, body) "
                "SELECT path, title, folder, tags, body FROM fts"
            ).rowcount
            logger.info(f"fts_trigram created, {copied} rows migrated from fts")
        except sqlite3.OperationalError as e:
            if "trigram" in str(e).lower():
                logger.warning(
                    "SQLite trigram tokenizer unavailable — substring fallback disabled"
                )
                return
            raise
```

Also ensure `logger` is defined at module top (if not already):

```python
import logging

logger = logging.getLogger(__name__)
```

(Add `import logging` and `logger = ...` right after existing imports at top of file, only if not already present.)

- [ ] **Step 4: Run migration tests — expect PASS**

```bash
pytest tests/test_fts_migration.py -v
```

Expected: 4 passed.

- [ ] **Step 5: Run full suite**

```bash
pytest tests/ -q
```

Expected: all pass (with the possible exception of legacy tests that need update — addressed in Task 7).

- [ ] **Step 6: Commit**

```bash
git add src/gh_apple_notes_mcp/semantic/fts_index.py tests/test_fts_migration.py
git commit -m "feat(fts): lazy migrate fts_trigram from fts on first search"
```

---

## Task 7: Update legacy tests for new `match_type` field

**Files:**
- Modify: `tests/test_fts_index.py`
- Possibly modify: `tests/test_search.py`, `tests/test_semantic_e2e.py`

- [ ] **Step 1: Run suite, identify failing tests**

```bash
pytest tests/ -q 2>&1 | tail -20
```

Any test that asserts exact dict equality on search results will fail (`match_type` field now present). Scan output.

- [ ] **Step 2: Update `tests/test_fts_index.py::test_upsert_and_search`**

If it asserts dict shape directly (e.g. `assert results[0] == {...}`), change to field-level assertions:

Find (approximate):
```python
results = idx.search("crash", limit=10)
assert len(results) == 1
# (rest of the assertion)
```

Verify it doesn't check exact dict — if it does, change to:

```python
results = idx.search("crash", limit=10)
assert len(results) == 1
assert results[0]["path"] == "APP-Dev/cosmicforge.md"
assert results[0]["match_type"] == "prefix"
```

If the existing test already uses field-level asserts only, no change needed.

- [ ] **Step 3: Check `tests/test_search.py` and `tests/test_semantic_e2e.py`**

```bash
pytest tests/test_search.py tests/test_semantic_e2e.py -v
```

If they fail on `match_type`, update similarly. If they pass, do nothing.

- [ ] **Step 4: Run full suite — zero failures**

```bash
pytest tests/ -q
```

Expected: all tests pass (pre-existing environment-dependent fails like `test_e2e_mcp` can still skip/fail — unrelated to this work).

- [ ] **Step 5: Commit**

```bash
git add tests/
git commit -m "test(fts): update legacy assertions for match_type field"
```

---

## Task 8: Version bump + README update

**Files:**
- Modify: `pyproject.toml` (version: `0.1.0` → `0.2.0`)
- Modify: `README.md` (add "What's new in v0.2")

- [ ] **Step 1: Bump version in pyproject.toml**

Find the line:
```toml
version = "0.1.0"
```

Replace with:
```toml
version = "0.2.0"
```

- [ ] **Step 2: Add "What's new" section to README.md**

Insert immediately after the `# gh-apple-notes-mcp` title heading and the one-sentence description. Add:

```markdown
## What's new in v0.2

**FTS5 substring-fallback search.** `semantic.search` now dorzuca wyniki substring-match (trigram tokenizer) gdy prefix search zwrócił mniej niż `top_k` trafień. Każdy wynik oznaczony `match_type: "prefix" | "trigram"` — Claude-side rerank może wziąć to pod uwagę.

**Auto-migration.** Bazy v0.1 automatycznie dostają nowy `fts_trigram` indeks przy pierwszym `semantic.search` po update. Zero manual steps — po `git pull && ./setup.sh` wszystko działa.

**Brak breaking changes.** Istniejące konsumenty (Claude Code skille) ignorują nowe pole — safe upgrade.
```

- [ ] **Step 3: Smoke test — verify full suite + version**

```bash
pytest tests/ -q
grep '^version' pyproject.toml
```

Expected: all tests pass; `version = "0.2.0"`.

- [ ] **Step 4: Commit + tag**

```bash
git add pyproject.toml README.md
git commit -m "chore: bump to v0.2.0 + README what's new"
git tag v0.2.0
git log --oneline -5
```

Expected: new tag `v0.2.0` pointing at latest commit.

- [ ] **Step 5: Push to origin**

```bash
git push origin main
git push origin v0.2.0
```

---

## Completion Checklist

After all tasks:

- [ ] **Test count:** ≥17 new tests (3 Task 2 + 6 Task 3 + 4 Task 4 + 7 Task 5 + 4 Task 6), all passing.
- [ ] **No regressions:** previous ~127 tests still pass.
- [ ] **Schema:** `fts` + `fts_trigram` tables both exist, both populated via `upsert`.
- [ ] **Search API:** prefix-first, trigram fills to top_k, `match_type` field on every result.
- [ ] **Migration:** v0.1 databases lazily upgrade on first `search()`.
- [ ] **Graceful degradation:** SQLite without trigram logs warning, search works prefix-only.
- [ ] **Version:** pyproject `0.2.0`, git tag `v0.2.0`, pushed to origin.
- [ ] **README:** "What's new in v0.2" section added.
- [ ] **Smoke test na live vault:** `semantic.search("cosmos")` znajduje "microcosmos" jeśli istnieje (lub równoważny substring scenario).
