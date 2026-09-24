"""Google Calendar service layer using official google-api-python-client.

Handles OAuth 2.0 credentials, token refresh, and Calendar API operations
(event creation, listing, conflict detection) for both the AI Advisor Agent
and the mobile app.
"""
from __future__ import annotations

import datetime
import json
import logging
import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build

load_dotenv()
logger = logging.getLogger(__name__)

SCOPES = [
    "https://www.googleapis.com/auth/calendar.events",
]

# Path to local token file relative to backend root
# Where the one Google token lives. Locally: backend/token.json. On Cloud Run
# the container disk is wiped per revision and refreshed tokens are written
# back, so TOKEN_FILE points at a writable /tmp path and the token itself is
# seeded from Secret Manager (GOOGLE_TOKEN_JSON) at startup. The MCP server
# subprocess reads the same TOKEN_FILE (app/mcp/google_calendar_server.py).
TOKEN_FILE = Path(os.environ.get("TOKEN_FILE", "token.json"))
if not TOKEN_FILE.is_absolute():
    TOKEN_FILE = Path(__file__).resolve().parent.parent.parent / TOKEN_FILE
if os.environ.get("GOOGLE_TOKEN_JSON") and not TOKEN_FILE.exists():
    TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
    TOKEN_FILE.write_text(os.environ["GOOGLE_TOKEN_JSON"], encoding="utf-8")

# There is ONE Google token per backend, so exactly one farm may use it.
# Without this, any phone that installed the APK could link its own Google
# account (replacing the team's token) or read/write the team's calendar.
# Owner = the farm that completed the OAuth link (written at callback), or
# CALENDAR_OWNER_FARM_ID in .env to pin it. Every other farm still gets
# proposals and can approve them -- the approval is kept in the app only.
OWNER_FILE = TOKEN_FILE.with_name("calendar_owner.json")


def get_calendar_owner() -> str | None:
    pinned = os.environ.get("CALENDAR_OWNER_FARM_ID", "").strip()
    if pinned:
        return pinned
    try:
        return json.loads(OWNER_FILE.read_text(encoding="utf-8")).get("farm_id") or None
    except (OSError, ValueError):
        return None


def set_calendar_owner(farm_id: str) -> None:
    OWNER_FILE.write_text(json.dumps({"farm_id": farm_id}), encoding="utf-8")


def unlink_google() -> None:
    for f in (TOKEN_FILE, OWNER_FILE):
        try:
            f.unlink()
        except FileNotFoundError:
            pass


def farm_may_link(farm_id: str | None) -> bool:
    """A farm may start the Google link if nobody owns it yet, or it is the owner."""
    owner = get_calendar_owner()
    return bool(farm_id) and (owner is None or owner == farm_id)


def farm_may_write(farm_id: str | None) -> bool:
    """Writes/reads of the real calendar: only the owning farm, only when linked."""
    owner = get_calendar_owner()
    return bool(farm_id) and owner == farm_id and is_calendar_connected()


def get_client_config() -> dict[str, Any] | None:
    client_id = os.environ.get("GOOGLE_CLIENT_ID")
    client_secret = os.environ.get("GOOGLE_CLIENT_SECRET")
    redirect_uri = os.environ.get("GOOGLE_REDIRECT_URI", "http://localhost:8000/api/calendar/callback")

    if not client_id or not client_secret:
        logger.warning("GOOGLE_CLIENT_ID or GOOGLE_CLIENT_SECRET not configured in .env")
        return None

    return {
        "web": {
            "client_id": client_id,
            "client_secret": client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": [redirect_uri],
        }
    }


# In-memory PKCE fallback store keyed by OAuth state
_PKCE_STORE: dict[str, str] = {}


def create_oauth_flow(redirect_uri: str | None = None) -> Flow | None:
    """Create a Google OAuth Flow using client credentials from .env."""
    config = get_client_config()
    if not config:
        return None

    effective_redirect_uri = redirect_uri or os.environ.get(
        "GOOGLE_REDIRECT_URI", "http://localhost:8000/api/calendar/callback"
    )

    flow = Flow.from_client_config(
        config,
        scopes=SCOPES,
        redirect_uri=effective_redirect_uri,
    )
    # Confidential Web clients authenticate via client_secret. Disable autogenerating
    # PKCE code_verifier so that stateless callbacks across different requests do not
    # trigger "(invalid_grant) Missing code verifier".
    flow.autogenerate_code_verifier = False
    return flow


def get_authorization_url(redirect_uri: str | None = None, state: str | None = None) -> tuple[str, str] | None:
    """Generate Google authorization URL and state token."""
    flow = create_oauth_flow(redirect_uri=redirect_uri)
    if not flow:
        return None

    auth_url, state_out = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",
        state=state,
    )
    if flow.code_verifier and state_out:
        _PKCE_STORE[state_out] = flow.code_verifier
    return auth_url, state_out


def exchange_code_and_save_token(
    code: str,
    state: str | None = None,
    redirect_uri: str | None = None,
) -> Credentials | None:
    """Exchange OAuth authorization code for credentials and save to token.json."""
    flow = create_oauth_flow(redirect_uri=redirect_uri)
    if not flow:
        return None

    # If a code verifier was saved for this state, restore it
    if state and state in _PKCE_STORE:
        flow.code_verifier = _PKCE_STORE.pop(state)

    flow.fetch_token(code=code)
    creds = flow.credentials

    # Save to disk
    with open(TOKEN_FILE, "w", encoding="utf-8") as f:
        f.write(creds.to_json())

    logger.info("Successfully saved Google Calendar credentials to %s", TOKEN_FILE)
    return creds


def get_credentials() -> Credentials | None:
    """Load credentials from token.json and auto-refresh if expired."""
    if not TOKEN_FILE.exists():
        return None

    try:
        creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)
        if creds and creds.expired and creds.refresh_token:
            logger.info("Refreshing expired Google Calendar access token...")
            creds.refresh(Request())
            with open(TOKEN_FILE, "w", encoding="utf-8") as f:
                f.write(creds.to_json())
        return creds if creds and creds.valid else None
    except Exception as exc:
        logger.warning("Failed loading or refreshing credentials: %s", exc)
        return None


def is_calendar_connected() -> bool:
    """Check if valid Google Calendar credentials currently exist."""
    creds = get_credentials()
    return creds is not None and creds.valid


def get_calendar_service():
    """Build and return an authorized Google Calendar v3 service object."""
    creds = get_credentials()
    if not creds:
        raise RuntimeError("Google Calendar is not connected. Please authenticate first.")
    return build("calendar", "v3", credentials=creds)


def create_calendar_event(
    title: str,
    start_iso: str,
    end_iso: str | None = None,
    description: str = "",
    location: str = "Ladang Lada (Pepper Block)",
) -> dict[str, Any]:
    """Create an event on the user's primary Google Calendar."""
    service = get_calendar_service()

    start_dt = datetime.datetime.fromisoformat(start_iso.replace("Z", "+00:00"))
    if not end_iso:
        end_dt = start_dt + datetime.timedelta(hours=1)
    else:
        end_dt = datetime.datetime.fromisoformat(end_iso.replace("Z", "+00:00"))

    event_body = {
        "summary": title,
        "description": description,
        "location": location,
        "start": {
            "dateTime": start_dt.isoformat(),
        },
        "end": {
            "dateTime": end_dt.isoformat(),
        },
        # Emerald green for agricultural treatment / PepperDex theme
        "colorId": "2",
        "reminders": {
            "useDefault": False,
            "overrides": [
                {"method": "popup", "minutes": 60},
                {"method": "popup", "minutes": 1440},  # 1 day before
            ],
        },
    }

    created = service.events().insert(calendarId="primary", body=event_body).execute()
    logger.info("Created calendar event '%s' (ID: %s)", title, created.get("id"))
    return {
        "event_id": created.get("id"),
        "html_link": created.get("htmlLink"),
        "summary": created.get("summary"),
        "start": created.get("start", {}).get("dateTime"),
        "end": created.get("end", {}).get("dateTime"),
    }


def list_upcoming_events(max_results: int = 10) -> list[dict[str, Any]]:
    """Retrieve upcoming events starting from now."""
    service = get_calendar_service()
    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()

    events_result = (
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

    items = events_result.get("items", [])
    return [
        {
            "id": it.get("id"),
            "summary": it.get("summary"),
            "start": it.get("start", {}).get("dateTime") or it.get("start", {}).get("date"),
            "end": it.get("end", {}).get("dateTime") or it.get("end", {}).get("date"),
        }
        for it in items
    ]


def has_conflict(start_iso: str, end_iso: str) -> bool:
    """Check if any event overlaps with the given start/end window."""
    service = get_calendar_service()
    start_dt = datetime.datetime.fromisoformat(start_iso.replace("Z", "+00:00"))
    end_dt = datetime.datetime.fromisoformat(end_iso.replace("Z", "+00:00"))

    events_result = (
        service.events()
        .list(
            calendarId="primary",
            timeMin=start_dt.isoformat(),
            timeMax=end_dt.isoformat(),
            singleEvents=True,
        )
        .execute()
    )

    items = events_result.get("items", [])
    return len(items) > 0
