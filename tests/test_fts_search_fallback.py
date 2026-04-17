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
    assert "Ideas/a.md" in paths  # prefix match (lodz is prefix after normalize)
    # Both should be findable via normalization + fallback
