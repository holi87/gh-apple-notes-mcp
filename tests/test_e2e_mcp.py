"""E2E: spawn server subprocess with fake osascript, send JSON-RPC."""
import asyncio
import json
import os
import shutil
import stat
import sys
import tempfile
from pathlib import Path

import pytest


FAKE_OSASCRIPT = Path(__file__).parent / "fixtures" / "fake_osascript.sh"
# src/ directory for editable install — subprocess needs it on PYTHONPATH
SRC_DIR = str(Path(__file__).parent.parent / "src")


@pytest.fixture
def fake_path():
    """Create temp dir with fake osascript shimmed as 'osascript'."""
    d = tempfile.mkdtemp(prefix="gh-mcp-e2e-")
    fake = Path(d) / "osascript"
    shutil.copy(FAKE_OSASCRIPT, fake)
    fake.chmod(fake.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    yield d
    shutil.rmtree(d, ignore_errors=True)


@pytest.mark.asyncio
async def test_e2e_initialize_list_tools_and_call(fake_path):
    env = os.environ.copy()
    # Prepend fake osascript dir to PATH
    env["PATH"] = f"{fake_path}:{env.get('PATH', '')}"
    # Ensure the subprocess can find the package (editable .pth not always processed)
    existing_pythonpath = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = f"{SRC_DIR}:{existing_pythonpath}" if existing_pythonpath else SRC_DIR

    proc = await asyncio.create_subprocess_exec(
        sys.executable, "-m", "gh_apple_notes_mcp",
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=env,
    )

    try:
        # 1. Initialize
        init_req = {
            "jsonrpc": "2.0", "id": 1, "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "test", "version": "0.0.1"},
            },
        }
        proc.stdin.write((json.dumps(init_req) + "\n").encode())
        await proc.stdin.drain()
        line = await asyncio.wait_for(proc.stdout.readline(), timeout=10)
        response = json.loads(line)
        assert response["jsonrpc"] == "2.0"
        assert response["id"] == 1
        assert "result" in response

        # 2. notifications/initialized
        proc.stdin.write((json.dumps({
            "jsonrpc": "2.0", "method": "notifications/initialized"
        }) + "\n").encode())
        await proc.stdin.drain()

        # 3. tools/list
        proc.stdin.write((json.dumps({
            "jsonrpc": "2.0", "id": 2, "method": "tools/list"
        }) + "\n").encode())
        await proc.stdin.drain()
        line = await asyncio.wait_for(proc.stdout.readline(), timeout=5)
        response = json.loads(line)
        assert response["id"] == 2
        tools = response["result"]["tools"]
        names = [t["name"] for t in tools]
        assert "notes.list" in names
        assert "notes.get" in names
        assert "notes.append_tag" in names
        assert len(tools) == 10

        # 4. tools/call notes.list
        proc.stdin.write((json.dumps({
            "jsonrpc": "2.0", "id": 3, "method": "tools/call",
            "params": {"name": "notes.list", "arguments": {"folder": "claude"}},
        }) + "\n").encode())
        await proc.stdin.drain()
        line = await asyncio.wait_for(proc.stdout.readline(), timeout=5)
        response = json.loads(line)
        assert response["id"] == 3
        content = response["result"]["content"]
        notes = json.loads(content[0]["text"])
        assert len(notes) == 2
        assert all("id" in n for n in notes)
        assert notes[0]["id"] == "uuid-001"

        # 5. tools/call notes.list_folders
        proc.stdin.write((json.dumps({
            "jsonrpc": "2.0", "id": 4, "method": "tools/call",
            "params": {"name": "notes.list_folders", "arguments": {}},
        }) + "\n").encode())
        await proc.stdin.drain()
        line = await asyncio.wait_for(proc.stdout.readline(), timeout=5)
        response = json.loads(line)
        folders = json.loads(response["result"]["content"][0]["text"])
        folder_names = [f["name"] for f in folders]
        assert "claude" in folder_names
        assert "Notes" in folder_names

    finally:
        proc.stdin.close()
        try:
            await asyncio.wait_for(proc.wait(), timeout=3)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
