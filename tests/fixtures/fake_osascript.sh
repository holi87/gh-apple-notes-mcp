#!/bin/bash
# Fake osascript for E2E tests — responds to known scripts with mock data.
# Real osascript invocation: osascript -e SCRIPT
# Our MCP always passes script as args[2] (after "-e").

SCRIPT="${2:-}"

# Detect intent based on script content
if echo "$SCRIPT" | grep -q "return 1"; then
    # Preflight smoke test
    echo "1"
    exit 0
fi

if echo "$SCRIPT" | grep -q "every folder"; then
    # list_folders
    printf "Notes\x1f0\x1eclaude\x1f0\x1eWork\x1f0"
    exit 0
fi

if echo "$SCRIPT" | grep -q "make new note"; then
    # create
    echo "x-coredata://fake/ICNote/p12345"
    exit 0
fi

if echo "$SCRIPT" | grep -q "set body of"; then
    # update_body
    exit 0
fi

if echo "$SCRIPT" | grep -q "delete n"; then
    # delete
    exit 0
fi

if echo "$SCRIPT" | grep -q "first note whose id is"; then
    # get_note (also used by update_body / delete, but those are caught above)
    printf "uuid-001\x1fShopping\x1fclaude\x1f2026-04-17T09:00:00Z\x1f2026-04-17T09:05:00Z\x1fkup chleb #claude"
    exit 0
fi

if echo "$SCRIPT" | grep -q "repeat with n in"; then
    # list_notes batch
    printf "uuid-001\x1fShopping\x1fclaude\x1f2026-04-17T09:00:00Z\x1f2026-04-17T09:05:00Z\x1fkup chleb #claude\x1euuid-002\x1fBug\x1fclaude\x1f2026-04-17T10:00:00Z\x1f2026-04-17T10:30:00Z\x1fCosmicForge crash #claude #claude/synced"
    exit 0
fi

# Unknown script — emit empty
exit 0
