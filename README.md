# gh-apple-notes-mcp

Custom MCP server for Apple Notes. Lets Claude Code (and any MCP-compatible client) list, read, create, tag, update, and delete notes — plus semantic search over a companion Obsidian vault.

## What's new in v0.2

**FTS5 substring-fallback search.** `semantic.search` now dorzuca wyniki substring-match (trigram tokenizer) gdy prefix search zwrócił mniej niż `top_k` trafień. Każdy wynik oznaczony `match_type: "prefix" | "trigram"` — Claude-side rerank może wziąć to pod uwagę.

**Auto-migration.** Bazy v0.1 automatycznie dostają nowy `fts_trigram` indeks przy pierwszym `semantic.search` po update. Zero manual steps — po `git pull && ./setup.sh` wszystko działa.

**Brak breaking changes.** Istniejące konsumenty (Claude Code skille) ignorują nowe pole — safe upgrade.

**Architecture:** AppleScript (via `osascript`) for CRUD + read-only SQLite for native hashtag tags (which AppleScript exposes as `\ufffc` placeholders). macOS-only.

## Requirements

- macOS 13+, Notes.app 16+
- Python 3.10+
- **Automation permission** for your terminal → Notes.app (prompted on first write)
- **Full Disk Access** for your terminal (needed for SQLite read of `NoteStore.sqlite`)

## Install

```bash
git clone https://github.com/holi87/gh-apple-notes-mcp.git
cd gh-apple-notes-mcp
./setup.sh
```

`setup.sh` creates a venv, installs deps, runs tests, and prints the `~/.claude.json` snippet to add.

Add the printed block to `~/.claude.json` under `mcpServers`:

```json
"gh-apple-notes": {
  "type": "stdio",
  "command": "/absolute/path/to/gh-apple-notes-mcp/.venv/bin/python",
  "args": ["-m", "gh_apple_notes_mcp"],
  "env": {
    "PYTHONPATH": "/absolute/path/to/gh-apple-notes-mcp/src"
  }
}
```

Restart Claude Code. Verify with any `notes.list` call.

## Tools

| Tool | Description |
|------|-------------|
| `notes.list(folder?, since?, limit?, include_trashed?)` | List notes with metadata + native hashtag tags |
| `notes.get(id, include_html?)` | Get full note by UUID |
| `notes.get_by_title(title, folder?)` | Find note by title (migration helper) |
| `notes.create(title, body, folder?)` | Create new note |
| `notes.append_tag(id, tag)` | Idempotent tag append (pass tag without `#`) |
| `notes.update_body(id, new_body)` | Replace full body |
| `notes.delete(id, confirm: true)` | Delete note (requires `confirm=true`) |
| `notes.list_folders()` | List folders with note counts |
| `semantic.search(query, top_k?, mode?, filter_folder?)` | BM25 search over Obsidian vault (requires indexer run) |
| `semantic.reindex(full?)` | Rebuild FTS5 index of vault notes |

## Semantic search (optional)

`semantic.*` tools index a companion Obsidian vault (default: `~/Documents/Obsidian/SecondBrain/SecondBrain/`). Override via env var `VAULT_PATH`. The FTS5 index uses Polish-diacritic normalization + prefix matching. `mode="candidates"` returns raw BM25 top-N for Claude-side rerank; `mode="auto"` does server-side LLM rerank (requires `ANTHROPIC_API_KEY`).

If you don't use Obsidian, ignore these tools — they fail gracefully without a vault.

## Debug

```bash
source .venv/bin/activate
python -m gh_apple_notes_mcp 2> /tmp/mcp.log   # stderr logs
pytest -v                                       # run test suite
```

## Troubleshooting

- **`osascript` error -1743 "Not authorized"** → System Settings → Privacy & Security → Automation → enable your terminal for Notes.
- **SQLite `unable to open database file`** → grant Full Disk Access to your terminal.
- **MCP not responding in Claude Code** → verify `~/.claude.json` paths, then restart Claude Code (MCPs don't auto-respawn).
- **Tests fail after setup.sh** → confirm Python 3.10+ (`python3 --version`) and that `pip install -e ".[dev]"` completed.

## Limitations

- **Attachments** not supported (Apple proprietary binary format).
- **Smart Folders** — `list_folders` returns them with `is_smart_folder=False` (AppleScript doesn't easily expose the flag).
- **Locked notes** — inaccessible via AppleScript until user unlocks in Notes.app.
- **Performance:** `notes.list` batch-fetches all notes in a folder in a single `osascript` call (~500ms–2s depending on folder size). Acceptable for manual workflows; not optimized for hot paths.
- **macOS only** — Apple Notes doesn't exist on other platforms.

## License

MIT — see [LICENSE](LICENSE).
