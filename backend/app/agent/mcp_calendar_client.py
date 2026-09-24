"""MCP Client Bridge for Google Calendar.

Connects to the configured Google Calendar MCP server over stdio,
discovers its tools, and invokes them on behalf of the AI agents.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

logger = logging.getLogger(__name__)

BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
CONFIG_PATH = BACKEND_DIR / "mcp_config.json"


def load_mcp_config() -> dict[str, Any]:
    """Load MCP server parameters from mcp_config.json."""
    if not CONFIG_PATH.exists():
        logger.warning("mcp_config.json not found at %s, using defaults", CONFIG_PATH)
        return {
            "command": sys.executable,
            "args": ["-m", "app.mcp.google_calendar_server"],
            "env": os.environ.copy(),
        }

    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)

    cal_cfg = data.get("mcpServers", {}).get("google_calendar", {})
    cmd = cal_cfg.get("command", sys.executable)
    if cmd == "python":
        cmd = sys.executable

    args = cal_cfg.get("args", ["-m", "app.mcp.google_calendar_server"])
    # mcp_config.json supplies DEFAULTS only; the real environment wins, so a
    # deployment's TOKEN_FILE (Cloud Run: /tmp/...) reaches the MCP server.
    merged_env = {**cal_cfg.get("env", {}), **os.environ}

    return {
        "command": cmd,
        "args": args,
        "env": merged_env,
    }


async def call_calendar_mcp_tool(tool_name: str, arguments: dict[str, Any]) -> str:
    """Execute a tool on the Google Calendar MCP server via stdio transport."""
    cfg = load_mcp_config()
    server_params = StdioServerParameters(
        command=cfg["command"],
        args=cfg["args"],
        env=cfg["env"],
        cwd=str(BACKEND_DIR),
    )

    try:
        async with stdio_client(server_params) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                result = await session.call_tool(tool_name, arguments=arguments)

                # Extract textual content from tool result
                output_parts = []
                for content in result.content:
                    if hasattr(content, "text"):
                        output_parts.append(content.text)
                    else:
                        output_parts.append(str(content))

                return "\n".join(output_parts)
    except Exception as exc:
        logger.error("MCP tool call '%s' failed: %s", tool_name, exc)
        return f"MCP Error executing '{tool_name}': {exc}"


async def get_mcp_calendar_status() -> dict[str, Any]:
    """Check connectivity and list registered tools from Google Calendar MCP server."""
    cfg = load_mcp_config()
    server_params = StdioServerParameters(
        command=cfg["command"],
        args=cfg["args"],
        env=cfg["env"],
        cwd=str(BACKEND_DIR),
    )

    # Same path the calendar service reads/writes (TOKEN_FILE env on Cloud Run).
    from app.tools.calendar_service import TOKEN_FILE as token_file
    has_token = token_file.exists()

    try:
        async with stdio_client(server_params) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                tools_result = await session.list_tools()
                tool_names = [t.name for t in tools_result.tools]

                return {
                    "mcp_connected": True,
                    "server_name": "google-calendar",
                    "tools": tool_names,
                    "has_token": has_token,
                    "token_file": str(token_file.name),
                }
    except Exception as exc:
        return {
            "mcp_connected": False,
            "error": str(exc),
            "tools": [],
            "has_token": has_token,
        }


# High-level tool wrappers for agent integration
async def mcp_list_upcoming_events(max_results: int = 10) -> str:
    return await call_calendar_mcp_tool("list_upcoming_events", {"max_results": max_results})


async def mcp_check_availability(start_iso: str, end_iso: str) -> str:
    return await call_calendar_mcp_tool("check_availability", {"start_iso": start_iso, "end_iso": end_iso})


async def mcp_create_calendar_event(
    title: str,
    start_iso: str,
    end_iso: str | None = None,
    description: str = "",
    location: str = "Ladang Lada (Pepper Block)",
) -> str:
    args = {
        "title": title,
        "start_iso": start_iso,
        "description": description,
        "location": location,
    }
    if end_iso:
        args["end_iso"] = end_iso
    return await call_calendar_mcp_tool("create_calendar_event", args)


async def mcp_update_calendar_event(
    event_id: str,
    new_title: str | None = None,
    new_start_iso: str | None = None,
    new_end_iso: str | None = None,
    new_description: str | None = None,
) -> str:
    args: dict[str, Any] = {"event_id": event_id}
    if new_title:
        args["new_title"] = new_title
    if new_start_iso:
        args["new_start_iso"] = new_start_iso
    if new_end_iso:
        args["new_end_iso"] = new_end_iso
    if new_description:
        args["new_description"] = new_description
    return await call_calendar_mcp_tool("update_calendar_event", args)


async def mcp_delete_calendar_event(event_id: str) -> str:
    return await call_calendar_mcp_tool("delete_calendar_event", {"event_id": event_id})
