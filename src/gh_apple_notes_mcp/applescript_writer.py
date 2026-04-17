"""AppleScript writer for Apple Notes (via osascript)."""
import re
import subprocess

from gh_apple_notes_mcp.config import APPLESCRIPT_TIMEOUT_SECONDS


class AppleScriptPermissionError(PermissionError):
    """macOS denied Apple Events access (error -1743)."""


class AppleScriptTimeoutError(TimeoutError):
    """osascript timed out."""


class AppleScriptError(RuntimeError):
    """Generic AppleScript failure."""


def escape_applescript_string(s: str) -> str:
    """Escape for AppleScript literal. Backslash FIRST."""
    s = s.replace("\\", "\\\\")
    s = s.replace('"', '\\"')
    s = s.replace("\n", "\\n")
    return s


def _run_osascript(script: str) -> subprocess.CompletedProcess:
    try:
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            text=True,
            timeout=APPLESCRIPT_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        raise AppleScriptTimeoutError(
            f"osascript timed out after {APPLESCRIPT_TIMEOUT_SECONDS}s"
        )
    if result.returncode != 0:
        if "-1743" in result.stderr or "Not authorized" in result.stderr:
            raise AppleScriptPermissionError(
                "Not authorized to access Apple Notes. "
                "System Settings → Privacy & Security → Automation → "
                "enable Notes access for your terminal."
            )
        raise AppleScriptError(f"osascript failed: {result.stderr.strip()}")
    return result


class AppleScriptWriter:
    def create(self, title: str, body: str, folder: str = "Notes") -> dict:
        t = escape_applescript_string(title)
        b = escape_applescript_string(body)
        f = escape_applescript_string(folder)
        script = f'''
tell application "Notes"
    set targetFolder to folder "{f}"
    set n to make new note at targetFolder with properties {{name:"{t}", body:"{b}"}}
    return id of n
end tell
'''.strip()
        result = _run_osascript(script)
        return {"id": result.stdout.strip()}

    def update_body(self, id: str, new_body: str) -> dict:
        i = escape_applescript_string(id)
        b = escape_applescript_string(new_body)
        script = f'''
tell application "Notes"
    set n to first note whose id is "{i}"
    set body of n to "{b}"
end tell
'''.strip()
        _run_osascript(script)
        return {"success": True}

    def append_tag(self, id: str, tag: str, existing_body: str) -> dict:
        """Idempotent tag append."""
        tag_pattern = re.compile(rf"(?<!\S)#{re.escape(tag)}(?!\w)")
        if tag_pattern.search(existing_body):
            return {
                "success": True,
                "already_present": True,
                "new_body": existing_body,
            }
        new_body = existing_body.rstrip() + f" #{tag}"
        self.update_body(id=id, new_body=new_body)
        return {
            "success": True,
            "already_present": False,
            "new_body": new_body,
        }

    def delete(self, id: str) -> dict:
        i = escape_applescript_string(id)
        script = f'''
tell application "Notes"
    set n to first note whose id is "{i}"
    delete n
end tell
'''.strip()
        _run_osascript(script)
        return {"success": True}
