"""Google Calendar MCP Server.

Standard Model Context Protocol (MCP) server exposing Google Calendar
tools (read, write, update, delete, conflict detection) over stdio.
"""
from __future__ import annotations

import datetime
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

try:
    from mcp.server.mcpserver import MCPServer
    mcp = MCPServer("google-calendar")
except ImportError:
    from mcp.server.fastmcp import FastMCP
    mcp = FastMCP("google-calendar")

SCOPES = ["https://www.googleapis.com/auth/calendar.events"]

# Resolve token.json path relative to backend directory or environment
TOKEN_PATH = Path(os.environ.get("TOKEN_FILE", "token.json"))
if not TOKEN_PATH.is_absolute():
    TOKEN_PATH = Path(__file__).resolve().parent.parent.parent / TOKEN_PATH


def get_service():
    """Retrieve an authenticated Google Calendar service instance."""
    if not TOKEN_PATH.exists():
        raise RuntimeError(
            f"Google Calendar credentials not found at {TOKEN_PATH}. "
            "Please link your Google account via PepperDex Settings first."
        )

    creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
        with open(TOKEN_PATH, "w", encoding="utf-8") as f:
            f.write(creds.to_json())

    if not creds or not creds.valid:
        raise RuntimeError("Google Calendar credentials are invalid or expired.")

    return build("calendar", "v3", credentials=creds)


@mcp.tool()
def list_upcoming_events(max_results: int = 10) -> str:
    """List upcoming events from the user's Google Calendar.

    Args:
        max_results: Maximum number of upcoming events to return (default 10).
    """
    try:
        service = get_service()
        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
        res = (
            service.events()
            .list(
                calendarId="primary",
                timeMin=now_iso,
                maxResults=max_results,
                singleEvents=True,
                orderBy="startTime",
            )
            .execute()
        )
        items = res.get("items", [])
        if not items:
            return "No upcoming events found on Google Calendar."

        events_summary = []
        for it in items:
            summary = it.get("summary", "(No Title)")
            start = it.get("start", {}).get("dateTime") or it.get("start", {}).get("date")
            end = it.get("end", {}).get("dateTime") or it.get("end", {}).get("date")
            event_id = it.get("id")
            events_summary.append(f"• ID: {event_id} | {summary} | Start: {start} | End: {end}")

        return "\n".join(events_summary)
    except Exception as exc:
        return f"Error listing events from Google Calendar: {exc}"


@mcp.tool()
def check_availability(start_iso: str, end_iso: str) -> str:
    """Check if the farmer is available (has no conflicting events) during a time window.

    Args:
        start_iso: Window start in ISO format (e.g. '2026-09-25T08:00:00+08:00').
        end_iso: Window end in ISO format (e.g. '2026-09-25T10:00:00+08:00').
    """
    try:
        service = get_service()
        start_dt = datetime.datetime.fromisoformat(start_iso.replace("Z", "+00:00"))
        end_dt = datetime.datetime.fromisoformat(end_iso.replace("Z", "+00:00"))

        res = (
            service.events()
            .list(
                calendarId="primary",
                timeMin=start_dt.isoformat(),
                timeMax=end_dt.isoformat(),
                singleEvents=True,
            )
            .execute()
        )
        items = res.get("items", [])
        if not items:
            return f"FREE: No conflicting events between {start_iso} and {end_iso}."

        conflicts = [f"'{it.get('summary')}' ({it.get('start', {}).get('dateTime')})" for it in items]
        return f"BUSY: Found {len(items)} conflict(s): {', '.join(conflicts)}."
    except Exception as exc:
        return f"Error checking availability: {exc}"


@mcp.tool()
def create_calendar_event(
    title: str,
    start_iso: str,
    end_iso: str | None = None,
    description: str = "",
    location: str = "Ladang Lada (Pepper Block)",
) -> str:
    """Create a new treatment or farm schedule event in Google Calendar.

    Args:
        title: Title/summary of the farm activity (e.g., 'Semburan Kuprum Hidroksida - Blok A').
        start_iso: Event start datetime in ISO format.
        end_iso: Event end datetime in ISO format (defaults to 1 hour after start).
        description: Dosage, rainfast advice, or agronomical notes.
        location: Specific block or farm location.
    """
    try:
        service = get_service()
        start_dt = datetime.datetime.fromisoformat(start_iso.replace("Z", "+00:00"))
        if not end_iso:
            end_dt = start_dt + datetime.timedelta(hours=1)
        else:
            end_dt = datetime.datetime.fromisoformat(end_iso.replace("Z", "+00:00"))

        event_body = {
            "summary": title,
            "description": description,
            "location": location,
            "start": {"dateTime": start_dt.isoformat()},
            "end": {"dateTime": end_dt.isoformat()},
            "colorId": "2",  # Emerald green theme
            "reminders": {
                "useDefault": False,
                "overrides": [
                    {"method": "popup", "minutes": 60},
                    {"method": "popup", "minutes": 1440},
                ],
            },
        }

        created = service.events().insert(calendarId="primary", body=event_body).execute()
        event_id = created.get("id")
        html_link = created.get("htmlLink", "")
        return f"SUCCESS: Created event '{title}' (ID: {event_id}). Link: {html_link}"
    except Exception as exc:
        return f"Error creating event: {exc}"


@mcp.tool()
def update_calendar_event(
    event_id: str,
    new_title: str | None = None,
    new_start_iso: str | None = None,
    new_end_iso: str | None = None,
    new_description: str | None = None,
) -> str:
    """Update or reschedule an existing event in Google Calendar.

    Args:
        event_id: The ID of the event to update.
        new_title: Optional updated title.
        new_start_iso: Optional updated start datetime in ISO format.
        new_end_iso: Optional updated end datetime in ISO format.
        new_description: Optional updated notes or dosage details.
    """
    try:
        service = get_service()
        event = service.events().get(calendarId="primary", eventId=event_id).execute()

        if new_title:
            event["summary"] = new_title
        if new_description:
            event["description"] = new_description

        if new_start_iso:
            start_dt = datetime.datetime.fromisoformat(new_start_iso.replace("Z", "+00:00"))
            event["start"] = {"dateTime": start_dt.isoformat()}
            if new_end_iso:
                end_dt = datetime.datetime.fromisoformat(new_end_iso.replace("Z", "+00:00"))
                event["end"] = {"dateTime": end_dt.isoformat()}
            else:
                end_dt = start_dt + datetime.timedelta(hours=1)
                event["end"] = {"dateTime": end_dt.isoformat()}

        updated = service.events().update(calendarId="primary", eventId=event_id, body=event).execute()
        return f"SUCCESS: Updated event '{updated.get('summary')}' (ID: {event_id})."
    except Exception as exc:
        return f"Error updating event {event_id}: {exc}"


@mcp.tool()
def delete_calendar_event(event_id: str) -> str:
    """Cancel and delete an event from Google Calendar.

    Args:
        event_id: The ID of the event to remove.
    """
    try:
        service = get_service()
        service.events().delete(calendarId="primary", eventId=event_id).execute()
        return f"SUCCESS: Event '{event_id}' has been successfully deleted from Google Calendar."
    except Exception as exc:
        return f"Error deleting event {event_id}: {exc}"


if __name__ == "__main__":
    mcp.run()
