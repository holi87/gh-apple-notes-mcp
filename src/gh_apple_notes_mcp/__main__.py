"""Entry point for MCP server: python -m gh_apple_notes_mcp"""
import asyncio
import json
import logging
import shutil
import subprocess
import sys

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

from gh_apple_notes_mcp.applescript_reader import AppleScriptReader
from gh_apple_notes_mcp.applescript_writer import AppleScriptWriter
from gh_apple_notes_mcp.config import SERVER_NAME, SERVER_VERSION
from gh_apple_notes_mcp.server import build_server_handlers


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger(SERVER_NAME)


TOOL_DEFINITIONS = [
    Tool(
        name="notes.list",
        description="List Apple Notes with optional folder/since filters.",
        inputSchema={
            "type": "object",
            "properties": {
                "folder": {"type": "string"},
                "since": {"type": "string", "description": "ISO datetime, filter modified > since"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 1000, "default": 50},
                "include_trashed": {"type": "boolean", "default": False},
            },
        },
    ),
    Tool(
        name="notes.get",
        description="Get full note by UUID.",
        inputSchema={
            "type": "object",
            "properties": {
                "id": {"type": "string"},
                "include_html": {"type": "boolean", "default": False},
            },
            "required": ["id"],
        },
    ),
    Tool(
        name="notes.get_by_title",
        description="Get note by title (migration helper).",
        inputSchema={
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "folder": {"type": "string"},
            },
            "required": ["title"],
        },
    ),
    Tool(
        name="notes.create",
        description="Create new note.",
        inputSchema={
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "body": {"type": "string"},
                "folder": {"type": "string", "default": "Notes"},
            },
            "required": ["title", "body"],
        },
    ),
    Tool(
        name="notes.append_tag",
        description="Idempotently append #tag to note body.",
        inputSchema={
            "type": "object",
            "properties": {
                "id": {"type": "string"},
                "tag": {"type": "string", "description": "WITHOUT leading #"},
            },
            "required": ["id", "tag"],
        },
    ),
    Tool(
        name="notes.update_body",
        description="Replace entire note body.",
        inputSchema={
            "type": "object",
            "properties": {
                "id": {"type": "string"},
                "new_body": {"type": "string"},
            },
            "required": ["id", "new_body"],
        },
    ),
    Tool(
        name="notes.delete",
        description="Delete note (requires confirm=true).",
        inputSchema={
            "type": "object",
            "properties": {
                "id": {"type": "string"},
                "confirm": {"type": "boolean"},
            },
            "required": ["id", "confirm"],
        },
    ),
    Tool(
        name="notes.list_folders",
        description="List folders with note counts and smart-folder flags.",
        inputSchema={"type": "object", "properties": {}},
    ),
    Tool(
        name="semantic.search",
        description="Semantic search over Obsidian vault markdown. BM25 prefilter + LLM rerank.",
        inputSchema={
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "top_k": {"type": "integer", "default": 5},
                "filter_folder": {"type": "string"},
                "mode": {
                    "type": "string",
                    "enum": ["candidates", "auto"],
                    "default": "candidates",
                    "description": "candidates=return for in-session LLM rank; auto=headless claude --print rerank"
                },
            },
            "required": ["query"],
        },
    ),
    Tool(
        name="semantic.reindex",
        description="Rebuild FTS5 index. full=True drops and recreates; false=incremental.",
        inputSchema={
            "type": "object",
            "properties": {
                "full": {"type": "boolean", "default": False},
            },
        },
    ),
]


def _preflight_checks() -> None:
    """Verify osascript is available."""
    if shutil.which("osascript") is None:
        logger.error("osascript not found in PATH — are you on macOS?")
        sys.exit(1)
    # Basic smoke: can we call osascript?
    try:
        result = subprocess.run(
            ["osascript", "-e", "return 1"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode != 0:
            logger.warning(f"osascript smoke test failed: {result.stderr}")
    except subprocess.TimeoutExpired:
        logger.warning("osascript smoke test timed out")
    except Exception as e:
        logger.warning(f"osascript smoke test error: {e}")


async def _serve() -> None:
    _preflight_checks()
    logger.info(f"{SERVER_NAME} v{SERVER_VERSION} starting")

    reader = AppleScriptReader()
    writer = AppleScriptWriter()
    handlers = build_server_handlers(reader=reader, writer=writer)

    server = Server(SERVER_NAME)

    @server.list_tools()
    async def list_tools() -> list[Tool]:
        return TOOL_DEFINITIONS

    @server.call_tool()
    async def call_tool(name: str, arguments: dict) -> list[TextContent]:
        handler = handlers.get(name)
        if handler is None:
            raise ValueError(f"Unknown tool: {name}")
        result = await handler(arguments)
        return [TextContent(type="text", text=json.dumps(result, default=str))]

    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream, write_stream, server.create_initialization_options()
        )


def main() -> None:
    try:
        asyncio.run(_serve())
    except KeyboardInterrupt:
        logger.info("Shutting down")


if __name__ == "__main__":
    main()
