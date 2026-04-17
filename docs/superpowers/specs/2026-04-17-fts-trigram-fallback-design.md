# v0.2 — FTS5 trigram fallback for substring search

**Status:** Design · 2026-04-17
**Scope:** `gh-apple-notes-mcp` (public repo)
**Depends on:** v0.1 (current release with prefix-only FTS5 + semantic search)

---

## 1. Problem i cel

Current `semantic.search` używa FTS5 z `unicode61 remove_diacritics 2` tokenizerem i prefix-match query escaping (`"{token}"*`). To daje szybki, precyzyjny word-boundary match, ale gubi **substring matches**: query `cosmos` nie znajdzie notatki "microcosmos", bo `cosmos` to nie jest prefix żadnego z tokenów w "microcosmos" (tokeny to `microcosmos` jako całość).

**Scenariusz reportowany przez usera:** `cosmos` nie match'uje `cosmicforge` (user szukał prawdopodobnie swojego projektu). Choć ten konkretny przykład nie byłby substring-match (`cosmos` nie występuje w `cosmicforge`), ujawnił brak fallback dla przypadków `microcosmos` / `macrocosmos` / podciąg w tagu etc.

**Cel:** Dodać drugi FTS5 indeks z `tokenize='trigram'` który dorzuca substring matches gdy prefix search nie wypełnił żądanego `top_k`. Nie zmieniać istniejącego zachowania (prefix match dalej pierwszy), nie wymagać konfiguracji.

**Non-goals:**
- Fuzzy / Levenshtein-edit-distance matching (inne narzędzie — trigram daje tylko substring).
- Typo autocorrect (można emulować przez trigram, ale tu nie celujemy).
- Scoring ranking re-tuning — BM25 zostaje, trigram matches oznaczane `match_type` dla caller'a (Claude).
- Per-query / per-install opt-out toggle — YAGNI, może dodać gdy ktoś zgłosi problem.

---

## 2. Decyzje projektowe

| # | Decyzja | Wariant |
|---|---|---|
| 1 | Strategia queryowania | Prefix-first z fallback do trigram |
| 2 | Próg fallback | Fill do `top_k` (jeśli prefix zwrócił <top_k, dorzuć trigram) |
| 3 | Scoring | Zachowaj BM25, dodaj `match_type: "prefix" \| "trigram"` w response |
| 4 | Konfigurabilność | Zawsze on, brak env / query toggle (YAGNI) |
| 5 | Migracja | Auto-detect missing `fts_trigram` + lazy build przy pierwszym `search()` |

---

## 3. Architektura i komponenty

### 3.1 Schema — dwa FTS5 tables

**`src/gh_apple_notes_mcp/semantic/fts_index.py`**:

```python
SCHEMA_SQL = """
CREATE VIRTUAL TABLE IF NOT EXISTS fts USING fts5(
    path UNINDEXED, title, folder UNINDEXED, tags, body,
    classification UNINDEXED, mtime UNINDEXED,
    tokenize = 'unicode61 remove_diacritics 2'
);

CREATE VIRTUAL TABLE IF NOT EXISTS fts_trigram USING fts5(
    path UNINDEXED, title, folder UNINDEXED, tags, body,
    tokenize = 'trigram'
);
"""
```

**Uwagi:**
- `fts_trigram` nie ma `classification` ani `mtime` — nie potrzebne dla substring search, dorzucamy te pola w wyniku merge-by-path z głównego `fts`.
- Oba indeksy mają `path UNINDEXED, folder UNINDEXED` dla filter + dedup.
- `tokenize = 'trigram'` wymaga SQLite ≥3.34 (2020). macOS 13+ ma natywnie 3.43+; SQLite w Python na Pythonie 3.10+ (systemowym albo venv) na nowoczesnym macOS — OK. Graceful degradation gdyby nie (sekcja 6).

### 3.2 Upsert — insert do obu tabel atomicznie

```python
def upsert(self, record: dict) -> None:
    with self._connect() as conn:
        conn.execute("DELETE FROM fts WHERE path = ?", (record["path"],))
        conn.execute("DELETE FROM fts_trigram WHERE path = ?", (record["path"],))
        # Insert main (all fields)
        conn.execute(
            "INSERT INTO fts (path, title, folder, tags, body, classification, mtime) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (..., _normalize(record["title"]), record["folder"], _normalize(record["tags"]),
             _normalize(record["body"]), record["classification"], record["mtime"]),
        )
        # Insert trigram (searchable only)
        conn.execute(
            "INSERT INTO fts_trigram (path, title, folder, tags, body) "
            "VALUES (?, ?, ?, ?, ?)",
            (record["path"], _normalize(record["title"]), record["folder"],
             _normalize(record["tags"]), _normalize(record["body"])),
        )
```

Transaction isolation: jedna `with self._connect()` obejmuje oba inserty. Failure jednego → rollback obu (spójność gwarantowana przez SQLite default auto-commit-on-close behavior).

`delete(path)` — analogicznie, usuwa z obu tabel.

### 3.3 Search — prefix-first z fill-to-top_k

```python
def search(
    self,
    query: str,
    limit: int = 50,
    filter_folder: Optional[str] = None,
) -> list[dict]:
    if not query.strip():
        return []

    self._ensure_trigram_table_exists()  # migration check (idempotent)

    prefix_rows = self._prefix_search(query, limit, filter_folder)
    for r in prefix_rows:
        r["match_type"] = "prefix"

    if len(prefix_rows) < limit:
        seen_paths = {r["path"] for r in prefix_rows}
        remaining = limit - len(prefix_rows)
        trigram_rows = self._trigram_search(query, limit, filter_folder)
        for r in trigram_rows:
            if r["path"] in seen_paths:
                continue
            r["match_type"] = "trigram"
            prefix_rows.append(r)
            if len(prefix_rows) >= limit:
                break
    return prefix_rows
```

### 3.4 Private helpers

**`_prefix_search(query, limit, filter_folder)`** — current logic, extracted from public `search`:

```python
escaped = _escape_fts5_query(query)  # "{t}"* AND ...
if not escaped:
    return []
sql = "SELECT path, title, folder, tags, body, classification, mtime FROM fts WHERE fts MATCH ? "
# ... (filter_folder, ORDER BY rank, LIMIT)
```

**`_trigram_search(query, limit, filter_folder)`** — new:

```python
escaped = _escape_trigram_query(query)  # "{t}" (no *) AND ... 
if not escaped:
    return []
sql = (
    "SELECT ftr.path, ftr.title, ftr.folder, ftr.tags, ftr.body, "
    "       f.classification, f.mtime "
    "FROM fts_trigram ftr "
    "LEFT JOIN fts f ON f.path = ftr.path "
    "WHERE fts_trigram MATCH ? "
)
# ... (filter_folder na ftr.folder, ORDER BY ftr.rank, LIMIT)
```

Uwaga: JOIN na `fts` dostarcza `classification` i `mtime` (które są UNINDEXED w `fts`, nie są w `fts_trigram`). `LEFT JOIN` bo hipotetycznie notatka może być w trigram ale nie w fts (nie powinno się zdarzyć przy integralnym upsert, ale defensywnie).

### 3.5 Escape queries

**`_escape_fts5_query(query)`** — bez zmian (existing prefix escape).

**`_escape_trigram_query(query)`** — nowy:

```python
def _escape_trigram_query(query: str) -> str:
    """Wrap tokens as phrase-match (no prefix *) for trigram tokenizer."""
    normalized = _normalize(query)
    if len(normalized.strip()) < 3:
        return ""  # trigram needs ≥3 chars
    tokens = normalized.split()
    if not tokens:
        return ""
    escaped = [f'"{t.replace(chr(34), chr(34)*2)}"' for t in tokens]
    return " AND ".join(escaped)
```

Kluczowa różnica: brak `*` po phrase. Trigram tokenizer sam obsługuje substring matching — każda sekwencja 3 znaków w indexed text staje się tokenem, więc plain phrase query wystarczy.

### 3.6 Auto-migration — `_ensure_trigram_table_exists`

```python
def _ensure_trigram_table_exists(self) -> None:
    """Lazy-build fts_trigram from existing fts if missing.
    Idempotent — second call is no-op."""
    with self._connect() as conn:
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='fts_trigram'"
        ).fetchone()
        if row:
            return
        try:
            conn.executescript(SCHEMA_SQL)  # creates fts_trigram; fts is IF NOT EXISTS
            copied = conn.execute(
                "INSERT INTO fts_trigram (path, title, folder, tags, body) "
                "SELECT path, title, folder, tags, body FROM fts"
            ).rowcount
            logger.info(f"fts_trigram table created, {copied} rows migrated")
        except sqlite3.OperationalError as e:
            if "no such tokenizer: trigram" in str(e):
                logger.warning(
                    "SQLite trigram tokenizer unavailable — substring fallback disabled"
                )
                return
            raise
```

Performance: jednorazowy cost przy pierwszym `search()` po upgrade. Dla ~10k notek po 3kB body: kilka sekund. Jednorazowy.

### 3.7 Full reindex — update

`Indexer.full_rebuild` musi drop'ować obie tabele:

```python
def full_rebuild(self) -> dict:
    with self.fts_index._connect() as conn:
        conn.execute("DROP TABLE IF EXISTS fts")
        conn.execute("DROP TABLE IF EXISTS fts_trigram")
    self.fts_index.create_schema()  # recreates both
    return self._rebuild_from_vault()
```

### 3.8 Co zostaje bez zmian

- `_normalize()` transliteration — reused.
- `indexer.py` pipeline — wywołuje `upsert` / `delete` jak dotychczas.
- `search.py` prefilter — konsumuje `FtsIndex.search()` return, nie peek'uje w `match_type`.
- `llm_rank.py` — consumer, ignore unknown fields. W przyszłości może użyć `match_type` dla scoringu.
- `semantic.search` MCP tool — schema wyjściowa rośnie o jedno pole, backward compat.

---

## 4. Data flow

```
semantic.search(query, top_k, filter_folder)
  │
  ├─ _ensure_trigram_table_exists()  [1x lazy migration if fts_trigram missing]
  │
  ├─ _prefix_search(query, top_k, filter_folder) via fts.MATCH "{t}"* AND ...
  │     → rows z match_type="prefix"
  │
  ├─ if len(rows) < top_k:
  │     _trigram_search(query, top_k, filter_folder) via fts_trigram.MATCH "{t}" AND ...
  │     dedup po path vs seen, append z match_type="trigram"
  │
  └─ return rows (≤top_k, sorted: all prefix first, then trigram)
```

---

## 5. Format response MCP `semantic.search`

**Przed v0.2:**
```json
[
  {"path": "APP-Dev/cosmos.md", "title": "Cosmos", "folder": "APP-Dev",
   "tags": "...", "body": "...", "classification": {...}, "mtime": "..."}
]
```

**Po v0.2:**
```json
[
  {"path": "APP-Dev/cosmos.md", "title": "Cosmos", "folder": "APP-Dev",
   "tags": "...", "body": "...", "classification": {...}, "mtime": "...",
   "match_type": "prefix"},
  {"path": "Work/microcosmos.md", "title": "Microcosmos", "folder": "Work",
   "tags": "...", "body": "...", "classification": {...}, "mtime": "...",
   "match_type": "trigram"}
]
```

Backward compat: konsumenci (F6 workflow, `/gh-search` skill) ignorują nieznane pola — nic się nie psuje.

---

## 6. Error handling

| Scenariusz | Zachowanie |
|---|---|
| SQLite <3.34 (no trigram tokenizer) | `_ensure_trigram_table_exists` łapie `OperationalError: no such tokenizer: trigram`, loguje warning, `fts_trigram` nie powstaje. `search()` dalej działa tylko prefix — zero crash. |
| Query `<3` znaków | `_escape_trigram_query` zwraca `""` → skip trigram stage, return tylko prefix matches. |
| Concurrent upsert | Single transaction per `upsert()` — atomic both-tables. Failure jednego = rollback obu. |
| Migration partial (fts_trigram exists ale pusty) | `_ensure_trigram_table_exists` sprawdza `sqlite_master` (exists/not), nie count. Jeśli table empty ale istnieje — treat as complete. User może wywołać `semantic.reindex(full=True)` by populate. Unlikely edge case. |
| `full_rebuild` | DROP obu tables + CREATE → empty start, odbudowa przez pełny pipeline indexera. |
| `filter_folder` + trigram | Both indeksy mają `folder UNINDEXED`, filter działa identycznie. |

**Nie-silent-failure:** Migration + degradation zawsze loguje na stderr (Python logger, MCP już ma handler kierujący do stderr).

---

## 7. Testing

### 7.1 Nowe pliki

**`tests/test_fts_trigram.py`** (unit — trigram-specific):
- `test_trigram_table_created_on_schema_init`
- `test_trigram_insert_via_upsert_coexists_with_main_fts`
- `test_trigram_query_finds_substring_match` (`cosmos` → `microcosmos`)
- `test_trigram_query_too_short_returns_empty` (<3 chars)
- `test_trigram_query_respects_filter_folder`
- `test_trigram_delete_removes_from_both_tables`

**`tests/test_fts_search_fallback.py`** (integration):
- `test_prefix_match_returns_match_type_prefix`
- `test_fallback_fills_to_top_k_with_trigram_matches`
- `test_fallback_dedup_removes_path_already_in_prefix`
- `test_fallback_not_triggered_when_prefix_fills_top_k`
- `test_empty_query_returns_empty_list`
- `test_polish_diacritics_in_trigram` (`łódź` → `lodz` substring match)
- `test_filter_folder_applied_to_both_stages`

**`tests/test_fts_migration.py`** (lazy migration):
- `test_lazy_build_creates_trigram_from_existing_fts`
- `test_lazy_build_idempotent_second_call_noop`
- `test_full_reindex_drops_and_rebuilds_both_tables`
- `test_trigram_unavailable_graceful_degradation` (mock sqlite raising OperationalError)

### 7.2 Update istniejących

**`tests/test_fts_index.py`:**
- Schema assertion gdzieś explicit liczy tabele — update na 2.
- `search()` result shape assertions — dodać `match_type` field expectations.

**`tests/test_search.py`** (prefilter) i **`tests/test_semantic_e2e.py`** — consume `search()` jak czarny box. Spodziewam się pass bez modyfikacji. Weryfikuję.

### 7.3 Minimum bar

- ≥17 nowych testów (6 trigram + 7 fallback + 4 migration).
- Istniejące 127 testów must pass (z udate'owanymi assertions).
- Total target: **140+ passed, 0 failed**, 1 skipped (`test_e2e_mcp` environment-dependent jak dziś).

### 7.4 Benchmark

`tests/test_fts_bench.py` — marked `@pytest.mark.slow`, `@pytest.mark.skipif(not os.environ.get("RUN_BENCH"))`:
- Synthetic vault 1000 notek (random Polish-English prose).
- `search()` × 100 random queries.
- `assert p95 < 200ms`.

Nie wliczany do default `pytest` run; manual `RUN_BENCH=1 pytest tests/test_fts_bench.py`.

---

## 8. Granice i ryzyka

**Granice:**
- Migration one-time cost przy pierwszym `search()` po upgrade — proporcjonalny do liczby notek. Dla 10k notek ~kilka sekund. Akceptowalne.
- Indeks DB rośnie ~3-5× (trigram generuje więcej postingi). Dla 100k notek: ~250MB zamiast ~50MB. Akceptowalne.

**Ryzyka:**
- **SQLite trigram dostępność:** macOS ma bundled SQLite, ale Python `sqlite3` użyłby tego który jest zlinkowany. Python na macOS 13+ używa system SQLite (3.43+), trigram OK. Windows / Linux (userów MCP nie ma) też OK. Graceful degradation jeśli by było.
- **Performance degradation dla rzadkich tokenów:** Jeśli vault ma 100k notek i ktoś szuka `"aa"` jako substring, trigram może zwrócić tysiące kandydatów. Limit `top_k=50` (current) chroni. Mimo to — BM25 ranking trigramów może być wolniejsze niż prefix. Benchmark odkryje.
- **Dual-write atomicity:** Two inserts per upsert. Jeśli Python crash między nimi — stale data. SQLite transaction-scope rozwiązuje dopóki jesteśmy w `with` block. Weryfikujemy testem (`test_upsert_atomicity`).

---

## 9. Migration path dla users

**Dla usera updating v0.1 → v0.2:**

1. `cd ~/Desktop/gh-apple-notes-mcp && git pull`
2. `./setup.sh` (reuse venv, update deps — brak nowych deps, ale pip install -e .)
3. Restart Claude Code.
4. Pierwszy `semantic.search` call: auto-migration tworzy `fts_trigram` lazily. User zobaczy warning w log jeśli trigram unavailable.
5. (Opcjonalnie) `semantic.reindex(full=True)` by force clean rebuild.

Dokumentacja: update README v0.2 bullet "What's new: substring search fallback".

---

## 10. Sequence implementacji (high-level)

Szczegółowy plan powstanie w writing-plans. Szkic:

1. `fts_index.py` — dodać `fts_trigram` table do SCHEMA_SQL + rozszerz `upsert` / `delete` + unit tests.
2. `fts_index.py` — new `_escape_trigram_query`, `_trigram_search`, `_prefix_search` helpers (extract current logic) + unit tests.
3. `fts_index.py` — new public `search()` z fallback logic + integration tests.
4. `fts_index.py` — `_ensure_trigram_table_exists` migration logic + migration tests.
5. `indexer.py` — update `full_rebuild` drop both tables.
6. Existing tests — update assertions for `match_type` field + 2-table schema.
7. Benchmark (opt-in) + smoke test na live vault.
8. README v0.2 — note o substring fallback.
9. Version bump pyproject.toml → `0.2.0`, commit, tag, push.
