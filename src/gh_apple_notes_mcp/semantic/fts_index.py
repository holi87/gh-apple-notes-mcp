"""SQLite FTS5 wrapper for vault markdown indexing."""
import sqlite3
import unicodedata
from pathlib import Path
from typing import Optional


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
"""

# Characters that lack NFD decompositions but should still be folded to ASCII
# for cross-script matching (e.g. Polish ł → l, Scandinavian ø → o).
_TRANSLITERATION = str.maketrans({
    "ł": "l", "Ł": "L",
    "ø": "o", "Ø": "O",
    "đ": "d", "Đ": "D",
    "ð": "d", "Ð": "D",
    "þ": "th", "Þ": "Th",
    "æ": "ae", "Æ": "AE",
    "ß": "ss",
})


def _normalize(text: str) -> str:
    """Transliterate + NFD-fold diacritics; mirrors FTS5 unicode61 remove_diacritics 2."""
    text = text.translate(_TRANSLITERATION)
    return "".join(
        c for c in unicodedata.normalize("NFD", text)
        if unicodedata.category(c) != "Mn"
    )


def _escape_fts5_query(query: str) -> str:
    """Split query into tokens, wrap each as prefix-match phrase, AND them together.

    - Single word: 'konkurs' → '"konkurs"*'
    - Multi-word: 'konkurs ailab' → '"konkurs"* AND "ailab"*'
    - Special chars in tokens are escaped via FTS5 phrase quoting.
    """
    normalized = _normalize(query)
    tokens = normalized.split()
    if not tokens:
        return ""
    escaped_tokens = []
    for t in tokens:
        # FTS5: double quotes inside a phrase are escaped by doubling
        safe = t.replace('"', '""')
        escaped_tokens.append(f'"{safe}"*')
    return " AND ".join(escaped_tokens)


class FtsIndex:
    def __init__(self, db_path: Path):
        self.db_path = db_path

    def _connect(self) -> sqlite3.Connection:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def create_schema(self) -> None:
        with self._connect() as conn:
            conn.execute(SCHEMA_SQL)

    def upsert(self, record: dict) -> None:
        """Insert or replace a note record (searchable fields are normalized)."""
        with self._connect() as conn:
            conn.execute("DELETE FROM fts WHERE path = ?", (record["path"],))
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

    def delete(self, path: str) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM fts WHERE path = ?", (path,))

    def search(
        self,
        query: str,
        limit: int = 50,
        filter_folder: Optional[str] = None,
    ) -> list[dict]:
        """BM25-ranked full-text search with optional folder filter."""
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
