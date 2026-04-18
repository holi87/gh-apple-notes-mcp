"""AppleScript reader for Apple Notes (via osascript)."""
import re
import subprocess
from typing import Optional

from gh_apple_notes_mcp.config import APPLESCRIPT_TIMEOUT_SECONDS, DEFAULT_LIST_LIMIT
from gh_apple_notes_mcp.sqlite_reader import fetch_native_tags, note_pk_from_id


RS = "\x1e"  # Record Separator (ASCII 30)
US = "\x1f"  # Unit Separator (ASCII 31)


class AppleScriptPermissionError(PermissionError):
    """macOS denied Apple Events access."""


class NoteNotFoundError(LookupError):
    """Requested note does not exist."""


class AppleScriptError(RuntimeError):
    """Generic osascript failure."""


def clean_plaintext_body(body: str, title: str) -> str:
    """Normalize AppleScript `plaintext` output for consumers.

    - Strip leading line when it duplicates the note title (Apple Notes renders
      the title as the first visible line of the note).
    - Remove U+FFFC object-replacement chars left behind by attachments.
    - Collapse runs of 3+ blank lines into a single blank line.
    - Strip trailing whitespace on each line; trim outer whitespace.
    """
    if not body:
        return body
    text = body.replace("\uFFFC", "")
    lines = text.split("\n")
    if lines and title and lines[0].strip() == title.strip():
        lines = lines[1:]
    lines = [ln.rstrip() for ln in lines]
    text = "\n".join(lines)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip("\n")


def extract_tags_from_body(body: str) -> list[str]:
    """Extract #tag tokens (lowercase, dedupe, preserve order)."""
    if not body:
        return []
    seen: list[str] = []
    for m in re.finditer(r"#([\w/-]+)", body):
        tag = m.group(1).lower()
        if tag not in seen:
            seen.append(tag)
    return seen


def _run_osascript(script: str) -> subprocess.CompletedProcess:
    try:
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            text=True,
            timeout=APPLESCRIPT_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        raise AppleScriptError(f"osascript timed out ({APPLESCRIPT_TIMEOUT_SECONDS}s)")
    if result.returncode != 0:
        if "-1743" in result.stderr or "Not authorized" in result.stderr:
            raise AppleScriptPermissionError(
                "Not authorized to access Apple Notes. "
                "System Settings → Privacy & Security → Automation → Notes."
            )
        raise AppleScriptError(f"osascript failed: {result.stderr.strip()}")
    return result


def _parse_note_record(record: str) -> Optional[dict]:
    """Parse one note record: id<US>title<US>folder<US>created<US>modified<US>body"""
    if not record:
        return None
    fields = record.split(US)
    if len(fields) < 6:
        return None
    return {
        "id": fields[0],
        "title": fields[1],
        "folder": fields[2],
        "created": fields[3],
        "modified": fields[4],
        # body may contain additional US chars — rejoin remainder
        "body": US.join(fields[5:]),
    }


class AppleScriptReader:
    def _build_list_script(
        self,
        folder: Optional[str] = None,
        include_trashed: bool = False,
    ) -> str:
        """Build AppleScript to list all notes.

        Always fetches ALL notes (no AppleScript-side folder filter) to support
        Smart Folders. Folder filtering is done post-hoc in Python (list_notes).

        Bug fixes:
        - Uses index-based iteration (repeat with i from 1 to count) instead of
          repeat-with-ref to avoid -1700 coercion error on container access.
        - Uses container property via item-indexed reference, which works reliably.
        """
        script = '''
set RS to (ASCII character 30)
set US to (ASCII character 31)
set output to ""
tell application "Notes"
    set theNotes to every note
    set noteCount to count of theNotes
    repeat with i from 1 to noteCount
        set n to item i of theNotes
        set noteId to id of n as string
        set noteTitle to name of n as string
        try
            set noteContainer to container of n
            set noteFolder to name of noteContainer as string
        on error
            set noteFolder to ""
        end try
        set createdDate to creation date of n
        set modifiedDate to modification date of n
        try
            set noteBody to plaintext of n as string
        on error
            set noteBody to body of n as string
        end try
        set createdStr to my isoDate(createdDate)
        set modifiedStr to my isoDate(modifiedDate)
        set noteRecord to noteId & US & noteTitle & US & noteFolder & US & createdStr & US & modifiedStr & US & noteBody
        if output is "" then
            set output to noteRecord
        else
            set output to output & RS & noteRecord
        end if
    end repeat
end tell
return output

on isoDate(d)
    if d is missing value then return ""
    set y to year of d as integer
    set m to (month of d as integer)
    set dd to day of d as integer
    set hh to hours of d as integer
    set mm to minutes of d as integer
    set ss to seconds of d as integer
    return (y as string) & "-" & text -2 thru -1 of ("0" & m) & "-" & text -2 thru -1 of ("0" & dd) & "T" & text -2 thru -1 of ("0" & hh) & ":" & text -2 thru -1 of ("0" & mm) & ":" & text -2 thru -1 of ("0" & ss) & "Z"
end isoDate
'''
        return script

    def _build_get_note_script(self, note_id: str) -> str:
        """Build AppleScript to get a single note by ID."""
        safe_id = note_id.replace('"', '\\"')
        script = f'''
set US to (ASCII character 31)
tell application "Notes"
    try
        set n to first note whose id is "{safe_id}"
    on error
        return ""
    end try
    set noteId to id of n as string
    set noteTitle to name of n as string
    try
        set noteContainer to container of n
        set noteFolder to name of noteContainer as string
    on error
        set noteFolder to ""
    end try
    set createdDate to creation date of n
    set modifiedDate to modification date of n
    try
        set noteBody to plaintext of n as string
    on error
        set noteBody to body of n as string
    end try
    set createdStr to my isoDate(createdDate)
    set modifiedStr to my isoDate(modifiedDate)
    return noteId & US & noteTitle & US & noteFolder & US & createdStr & US & modifiedStr & US & noteBody
end tell

on isoDate(d)
    if d is missing value then return ""
    set y to year of d as integer
    set m to (month of d as integer)
    set dd to day of d as integer
    set hh to hours of d as integer
    set mm to minutes of d as integer
    set ss to seconds of d as integer
    return (y as string) & "-" & text -2 thru -1 of ("0" & m) & "-" & text -2 thru -1 of ("0" & dd) & "T" & text -2 thru -1 of ("0" & hh) & ":" & text -2 thru -1 of ("0" & mm) & ":" & text -2 thru -1 of ("0" & ss) & "Z"
end isoDate
'''
        return script

    def _build_get_html_script(self, note_id: str) -> str:
        """Build AppleScript returning the raw HTML body of a note."""
        safe_id = note_id.replace('"', '\\"')
        return f'''
tell application "Notes"
    try
        set n to first note whose id is "{safe_id}"
    on error
        return ""
    end try
    return body of n as string
end tell
'''

    def _build_list_folders_script(self) -> str:
        """Build AppleScript to list all folders."""
        return '''
set RS to (ASCII character 30)
set US to (ASCII character 31)
set output to ""
tell application "Notes"
    set theFolders to every folder
    repeat with f in theFolders
        set folderName to name of f as string
        set folderType to "0"
        set folderRecord to folderName & US & folderType
        if output is "" then
            set output to folderRecord
        else
            set output to output & RS & folderRecord
        end if
    end repeat
end tell
return output
'''

    def list_notes(
        self,
        folder: Optional[str] = None,
        since: Optional[str] = None,
        limit: int = DEFAULT_LIST_LIMIT,
        include_trashed: bool = False,
    ) -> list[dict]:
        """Batch-fetch note metadata + body via single osascript call.

        When *folder* is given, post-hoc filtering keeps notes where:
          - note's physical folder name matches (regular folder), OR
          - folder name appears in the note's #tags (Smart Folder convention).
        This handles Apple Notes Smart Folders which are saved queries and do not
        appear as physical containers on their notes.

        By default (include_trashed=False), notes in "Recently Deleted" folder
        are excluded.
        """
        script = self._build_list_script(include_trashed=include_trashed)
        result = _run_osascript(script)
        output = result.stdout.rstrip("\n")
        if not output:
            return []
        records = output.split(RS)
        seen_ids: set[str] = set()
        notes: list[dict] = []
        folder_lower = folder.lower() if folder else None
        native_tags_by_pk = fetch_native_tags()
        for r in records:
            parsed = _parse_note_record(r)
            if parsed is None:
                continue
            # De-duplicate: every note may appear multiple times when the user
            # has multiple accounts (iCloud + Google etc.)
            note_id = parsed["id"]
            if note_id in seen_ids:
                continue
            seen_ids.add(note_id)
            body = clean_plaintext_body(parsed["body"], parsed["title"])
            tags = extract_tags_from_body(body)
            pk = note_pk_from_id(note_id)
            if pk is not None:
                for t in native_tags_by_pk.get(pk, []):
                    if t not in tags:
                        tags.append(t)
            note_folder = parsed["folder"]
            # Filter out trashed notes (Recently Deleted folder) by default
            if not include_trashed and note_folder == "Recently Deleted":
                continue
            note = {
                "id": note_id,
                "title": parsed["title"],
                "folder": note_folder,
                "created": parsed["created"],
                "modified": parsed["modified"],
                "tags": tags,
                "snippet": body[:100],
            }
            if since and note["modified"] <= since:
                continue
            # Post-hoc folder filter: physical folder OR smart-folder tag match
            if folder_lower is not None:
                physical_match = note_folder.lower() == folder_lower
                tag_match = folder_lower in [t.lower() for t in tags]
                if not physical_match and not tag_match:
                    continue
            notes.append(note)
            if len(notes) >= limit:
                break
        return notes

    def get_note(self, id: str) -> dict:
        """Fetch a single note by UUID, returning full body."""
        script = self._build_get_note_script(id)
        result = _run_osascript(script)
        output = result.stdout.strip()
        if not output:
            raise NoteNotFoundError(f"Note not found: {id}")
        parsed = _parse_note_record(output)
        if parsed is None:
            raise NoteNotFoundError(f"Failed to parse note: {id}")
        body = clean_plaintext_body(parsed["body"], parsed["title"])
        tags = extract_tags_from_body(body)
        pk = note_pk_from_id(parsed["id"])
        if pk is not None:
            for t in fetch_native_tags().get(pk, []):
                if t not in tags:
                    tags.append(t)
        return {
            "id": parsed["id"],
            "title": parsed["title"],
            "body": body,
            "folder": parsed["folder"],
            "created": parsed["created"],
            "modified": parsed["modified"],
            "tags": tags,
            "has_attachments": False,
        }

    def get_note_html(self, id: str) -> str:
        """Fetch a note's raw HTML body (preserves rich formatting).

        Used by writer operations that must round-trip the body through
        Apple Notes without flattening to plaintext.
        """
        script = self._build_get_html_script(id)
        result = _run_osascript(script)
        output = result.stdout
        if not output.strip():
            raise NoteNotFoundError(f"Note not found: {id}")
        return output.rstrip("\n")

    def get_note_by_title(self, title: str, folder: Optional[str] = None) -> Optional[dict]:
        """Migration helper: find note by exact title match."""
        notes = self.list_notes(folder=folder, limit=10000)
        for n in notes:
            if n["title"] == title:
                return self.get_note(n["id"])
        return None

    def list_folders(self) -> list[dict]:
        """List all Apple Notes folders."""
        script = self._build_list_folders_script()
        result = _run_osascript(script)
        output = result.stdout.rstrip("\n")
        if not output:
            return []
        records = output.split(RS)
        folders: list[dict] = []
        for r in records:
            if not r:
                continue
            fields = r.split(US)
            if len(fields) < 2:
                continue
            folders.append({
                "name": fields[0],
                "note_count": 0,  # AppleScript doesn't easily expose per-folder count
                "is_smart_folder": False,  # Would require additional detection logic
            })
        return folders
