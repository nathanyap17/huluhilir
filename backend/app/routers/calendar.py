"""Calendar sync grants + on-demand draft generation. docs/PROJECT_SPEC.md
§9.15, §3 L4, pepperdex-rules skill §13.

The actual device calendar write is 100% client-side (expo-calendar) --
nothing here ever touches a calendar. This is only the consent record
(calendar_sync_grants) and the draft text (draft_calendar_sync).
"""
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent import mcp_calendar_client
from app.agent.llm_tools import draft_calendar_sync_flat
from app.db import get_session
from app.models.agent import CalendarEventProposal, Recommendation
from app.models.base import now_kuching
from app.models.core import Block, CalendarSyncGrant, Farm
from app.schemas.calendar import (
    ApproveProposalRequest,
    CalendarGrantRequest,
    CalendarGrantStatus,
    CalendarProposalOut,
    CalendarSyncGrantOut,
    CreateCalendarEventRequest,
    DraftCalendarSyncResult,
)
from app.tools import calendar_service


router = APIRouter(tags=["calendar"])


async def _is_demo_farm(session: AsyncSession, farm_id: str | None) -> bool:
    """The shared demo farm must never own the Google link: every device that
    picks "Try the demo farm" would then write into the team's calendar."""
    from app.routers.setup import DEMO_FARM_NAMES

    farm = await session.get(Farm, farm_id) if farm_id else None
    return farm is not None and farm.name in DEMO_FARM_NAMES


@router.get("/api/calendar/auth-url")
@router.get("/calendar/auth-url")
async def get_google_calendar_auth_url(
    farm_id: str | None = Query(default=None),
    redirect_uri: str | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
) -> dict[str, str]:
    """Generate the Google OAuth authorization URL for linking Google Calendar."""
    if await _is_demo_farm(session, farm_id) or not calendar_service.farm_may_link(farm_id):
        raise HTTPException(
            409,
            "Google Calendar is linked to the team's demo phone. On this device, approved "
            "schedules are kept in the app.",
        )
    res = calendar_service.get_authorization_url(redirect_uri=redirect_uri, state=farm_id)
    if not res:
        raise HTTPException(500, "Google Calendar OAuth client is not configured in .env")
    auth_url, _state = res
    return {"auth_url": auth_url}


@router.get("/api/calendar/login")
@router.get("/calendar/login")
async def google_calendar_login(
    farm_id: str | None = Query(default=None),
    redirect_uri: str | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
):
    """Direct browser shortcut: redirects directly to Google OAuth consent."""
    if await _is_demo_farm(session, farm_id) or not calendar_service.farm_may_link(farm_id):
        raise HTTPException(409, "Google Calendar is already linked to another farm.")
    res = calendar_service.get_authorization_url(redirect_uri=redirect_uri, state=farm_id)
    if not res:
        raise HTTPException(500, "Google Calendar OAuth client is not configured in .env")
    auth_url, _state = res
    return RedirectResponse(url=auth_url)


@router.get("/api/calendar/callback")
@router.get("/calendar/callback")
async def google_calendar_callback(
    code: str = Query(...),
    state: str | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
) -> HTMLResponse:
    """Handle OAuth redirect callback from Google, save token.json, and record grant."""
    try:
        if await _is_demo_farm(session, state) or not calendar_service.farm_may_link(state):
            raise RuntimeError("Google Calendar is already linked to another farm.")
        creds = calendar_service.exchange_code_and_save_token(code=code, state=state)
        if not creds:
            raise RuntimeError("Failed to exchange authorization code for tokens.")

        calendar_service.set_calendar_owner(state)
        # If a farm_id was passed in state, record the Google Calendar grant
        if state:
            farm = await session.get(Farm, state)
            if farm:
                grant = CalendarSyncGrant(farm_id=farm.farm_id, provider="google_calendar")
                session.add(grant)
                await session.commit()

        html_content = """<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>PepperDex - Google Calendar Connected</title>
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #F5F2ED; color: #2D2D2D; display: flex; align-items: center; justify-content: center; height: 100vh; margin: 0; }
        .card { background: white; padding: 32px 28px; border-radius: 16px; box-shadow: 0 4px 16px rgba(0,0,0,0.08); text-align: center; max-width: 380px; width: 90%; }
        .icon { width: 64px; height: 64px; background: #eaf5e9; border-radius: 50%; display: flex; align-items: center; justify-content: center; margin: 0 auto 16px; color: #2e7d32; font-size: 32px; font-weight: bold; }
        h1 { font-size: 20px; color: #1e3a1f; margin-bottom: 8px; }
        p { font-size: 14px; color: #5f6368; line-height: 1.5; margin-bottom: 24px; }
        .button { display: inline-block; background: #2e7d32; color: white; padding: 12px 24px; border-radius: 8px; text-decoration: none; font-weight: 600; font-size: 14px; }
    </style>
</head>
<body>
    <div class="card">
        <div class="icon">&#10003;</div>
        <h1>Google Calendar Disambungkan!</h1>
        <p>Google Calendar berjaya disambungkan ke PepperDex. Anda boleh kembali ke aplikasi sekarang.</p>
        <p style="font-size: 12px; color: #888;">(Google Calendar successfully connected. You may close this tab and return to the app.)</p>
    </div>
</body>
</html>"""
        return HTMLResponse(content=html_content, status_code=200)

    except Exception as exc:
        err_html = f"""<!DOCTYPE html>
<html>
<head><title>Authentication Error</title></head>
<body style="font-family: sans-serif; padding: 40px; text-align: center;">
    <h2 style="color: #c62828;">Sambungan Google Calendar Gagal</h2>
    <p>Ralat: {exc}</p>
    <p>Sila pastikan redirect URI sepadan dengan konfigurasi Google Cloud Console.</p>
</body>
</html>"""
        return HTMLResponse(content=err_html, status_code=400)


@router.delete("/api/calendar/google", status_code=204)
async def unlink_google_calendar(farm_id: str | None = Query(default=None)) -> None:
    """Owner-only: forget the Google token so another farm may link."""
    if calendar_service.get_calendar_owner() not in (None, farm_id):
        raise HTTPException(403, "Only the farm that linked Google Calendar can unlink it.")
    calendar_service.unlink_google()


@router.get("/api/calendar/status")
@router.get("/calendar/status")
async def get_google_calendar_status(
    farm_id: str | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Google link status as seen by THIS farm: `connected` only when this
    farm owns the link; `linked_elsewhere` when another farm (the team's demo
    phone) does, so the app can explain why it can't link."""
    token_ok = calendar_service.is_calendar_connected()
    owner = calendar_service.get_calendar_owner()
    connected = token_ok and farm_id is not None and owner == farm_id
    return {
        "connected": connected,
        "linked_elsewhere": token_ok and owner is not None and owner != farm_id,
        "provider": "google_calendar" if connected else None,
        "token_file": str(calendar_service.TOKEN_FILE.name),
    }


@router.get("/api/calendar/events")
@router.get("/calendar/events")
async def list_google_calendar_events(
    farm_id: str | None = Query(default=None),
    max_results: int = Query(default=10, ge=1, le=50),
) -> dict[str, Any]:
    """List upcoming Google Calendar events (owning farm only -- this is a
    real person's calendar)."""
    if not calendar_service.farm_may_write(farm_id):
        raise HTTPException(403, "Only the farm that linked Google Calendar can read it.")
    if not calendar_service.is_calendar_connected():
        raise HTTPException(400, "Google Calendar is not connected. Authenticate via /api/calendar/login first.")
    try:
        events = calendar_service.list_upcoming_events(max_results=max_results)
        return {"events": events, "count": len(events)}
    except Exception as exc:
        raise HTTPException(500, f"Failed to list events: {exc}")


@router.post("/api/calendar/events", status_code=201)
@router.post("/calendar/events", status_code=201)
async def create_google_calendar_event(
    req: CreateCalendarEventRequest,
    farm_id: str | None = Query(default=None),
) -> dict[str, Any]:
    """Create an event on Google Calendar directly (owning farm only)."""
    if not calendar_service.farm_may_write(farm_id):
        raise HTTPException(403, "Only the farm that linked Google Calendar can write to it.")
    if not calendar_service.is_calendar_connected():
        raise HTTPException(400, "Google Calendar is not connected. Authenticate via /api/calendar/login first.")
    try:
        res = calendar_service.create_calendar_event(
            title=req.title,
            start_iso=req.start_iso,
            end_iso=req.end_iso,
            description=req.description,
            location=req.location,
        )
        return res
    except Exception as exc:
        raise HTTPException(500, f"Failed to create event: {exc}")


@router.get("/api/calendar/mcp/status")
async def get_google_calendar_mcp_status() -> dict[str, Any]:
    """Check connectivity and list tools registered on the Google Calendar MCP server."""
    status = await mcp_calendar_client.get_mcp_calendar_status()
    return status


@router.get("/api/calendar/mcp/events")
async def list_events_via_mcp(
    max_results: int = Query(default=10, ge=1, le=50),
    farm_id: str | None = Query(default=None),
) -> dict[str, Any]:
    if not calendar_service.farm_may_write(farm_id):
        raise HTTPException(403, "Only the farm that linked Google Calendar can read it.")
    """List events via the Google Calendar MCP server."""
    res = await mcp_calendar_client.mcp_list_upcoming_events(max_results=max_results)
    return {"result": res}


@router.post("/api/calendar/mcp/events", status_code=201)
async def create_event_via_mcp(
    req: CreateCalendarEventRequest, farm_id: str | None = Query(default=None)
) -> dict[str, Any]:
    if not calendar_service.farm_may_write(farm_id):
        raise HTTPException(403, "Only the farm that linked Google Calendar can write to it.")
    """Create an event using the Google Calendar MCP server."""
    res = await mcp_calendar_client.mcp_create_calendar_event(
        title=req.title,
        start_iso=req.start_iso,
        end_iso=req.end_iso,
        description=req.description,
        location=req.location,
    )
    return {"result": res}


# ---------------------------------------------------------------------------
# Rule 13 Human-in-the-Loop Guardrail: Calendar Proposals & Approval
# ---------------------------------------------------------------------------


@router.get("/farms/{farm_id}/calendar-proposals", response_model=list[CalendarProposalOut])
async def list_calendar_proposals(
    farm_id: str, session: AsyncSession = Depends(get_session)
) -> list[CalendarProposalOut]:
    """Treatment schedule proposals for a farm: pending and decided ones.
    Proposals a newer diagnosis replaced before anyone acted ("superseded")
    are left out."""
    proposals = (
        await session.execute(
            select(CalendarEventProposal)
            .where(CalendarEventProposal.farm_id == farm_id, CalendarEventProposal.status != "superseded")
            .order_by(CalendarEventProposal.created_at.desc())
        )
    ).scalars().all()
    return [CalendarProposalOut.model_validate(p) for p in proposals]


@router.post("/farms/{farm_id}/calendar-proposals", response_model=CalendarProposalOut, status_code=201)
async def create_calendar_proposal(
    farm_id: str,
    req: CreateCalendarEventRequest,
    recommendation_id: str | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
) -> CalendarProposalOut:
    """Create a draft calendar proposal requiring farmer confirmation (Rule 13).
    Does NOT write to Google Calendar until explicitly approved."""
    import datetime

    start_dt = datetime.datetime.fromisoformat(req.start_iso.replace("Z", "+00:00"))
    if req.end_iso:
        end_dt = datetime.datetime.fromisoformat(req.end_iso.replace("Z", "+00:00"))
    else:
        end_dt = start_dt + datetime.timedelta(hours=1)

    proposal = CalendarEventProposal(
        farm_id=farm_id,
        recommendation_id=recommendation_id,
        title=req.title,
        start_time=start_dt,
        end_time=end_dt,
        description=req.description,
        location=req.location,
        status="pending_approval",
        approved_by_farmer=False,
    )
    session.add(proposal)
    await session.commit()
    return CalendarProposalOut.model_validate(proposal)


@router.post("/recommendations/{recommendation_id}/calendar-proposal", response_model=CalendarProposalOut)
async def proposal_for_recommendation(
    recommendation_id: str, session: AsyncSession = Depends(get_session)
) -> CalendarProposalOut:
    """Priority card -> "Add to calendar": the proposal card for THIS
    recommendation, shown in the Advisor for Approve/Reject. Returns the
    existing pending (or already approved) proposal; otherwise drafts a new
    one with the same slot rule the agent run uses. Never writes to a
    calendar -- approval still happens on the card (rule 13)."""
    from app.tools.scheduling import SCHEDULABLE, proposal_for, workable_slot

    rec = await session.get(Recommendation, recommendation_id)
    if rec is None:
        raise HTTPException(404, "recommendation not found")
    if rec.action_type not in SCHEDULABLE:
        raise HTTPException(400, f"'{rec.action_type}' is not something to schedule")
    if rec.defer_cause:
        raise HTTPException(400, "deferred: no rain-free window yet, so there is no slot to propose")

    existing = (
        await session.execute(
            select(CalendarEventProposal)
            .where(
                CalendarEventProposal.recommendation_id == recommendation_id,
                CalendarEventProposal.status.in_(("pending_approval", "approved", "deployed")),
            )
            .order_by(CalendarEventProposal.created_at.desc())
        )
    ).scalars().first()
    if existing is not None:
        return CalendarProposalOut.model_validate(existing)

    block = await session.get(Block, rec.block_id)
    if block is None:
        raise HTTPException(404, "block not found")
    proposal = proposal_for(
        farm_id=block.farm_id,
        run_id=rec.run_id,
        recommendation_id=rec.recommendation_id,
        block=block,
        action_type=rec.action_type,
        start=workable_slot(rec.recommended_at),
        reason_ms=rec.reason_ms or "",
    )
    session.add(proposal)
    await session.commit()
    return CalendarProposalOut.model_validate(proposal)


@router.post("/api/calendar/proposals/{proposal_id}/approve", response_model=CalendarProposalOut)
async def approve_calendar_proposal(
    proposal_id: str,
    req: ApproveProposalRequest,
    session: AsyncSession = Depends(get_session),
) -> CalendarProposalOut:
    """Farmer approves the proposed treatment schedule (Rule 13 Gate).
    Triggers the Google Calendar MCP server to deploy the event live."""
    proposal = await session.get(CalendarEventProposal, proposal_id)
    if not proposal:
        raise HTTPException(404, "Calendar proposal not found")

    if not req.farmer_confirmed:
        raise HTTPException(400, "Farmer confirmation is required to deploy to Google Calendar")

    if not calendar_service.farm_may_write(proposal.farm_id):
        # Not the farm that owns the Google link (e.g. a judge's phone), or no
        # link at all: the farmer's approval is still recorded -- rule 13's
        # gate is the approval itself -- but nothing is written to anyone's
        # Google Calendar. `html_link` stays null, which the card shows.
        proposal.approved_by_farmer = True
        proposal.approved_at = now_kuching()
        proposal.status = "approved"
        await session.commit()
        return CalendarProposalOut.model_validate(proposal)

    import datetime
    
    start_time = proposal.start_time
    if start_time.tzinfo is None:
        start_time = start_time.replace(tzinfo=datetime.timezone(datetime.timedelta(hours=8)))
        
    end_time = proposal.end_time
    if end_time.tzinfo is None:
        end_time = end_time.replace(tzinfo=datetime.timezone(datetime.timedelta(hours=8)))

    # Deploy event live via MCP tool
    mcp_res = await mcp_calendar_client.mcp_create_calendar_event(
        title=proposal.title,
        start_iso=start_time.isoformat(),
        end_iso=end_time.isoformat(),
        description=proposal.description,
        location=proposal.location,
    )

    # MCP is the only write path. There used to be a silent fallback to a
    # direct Google Calendar API call here, which is why an approved event
    # could land in the calendar without MCP ever being used (2026-09-23).
    # If the MCP server fails the farmer sees the error and can retry.
    if not mcp_res.startswith("SUCCESS"):
        raise HTTPException(502, f"Google Calendar MCP server could not create the event: {mcp_res}")
    if "ID: " in mcp_res:
        proposal.google_event_id = mcp_res.split("ID: ", 1)[1].split(")")[0].strip()
    if "Link: " in mcp_res:
        proposal.html_link = mcp_res.split("Link: ", 1)[1].strip()

    proposal.approved_by_farmer = True
    proposal.approved_at = now_kuching()
    proposal.status = "deployed"

    await session.commit()
    return CalendarProposalOut.model_validate(proposal)


@router.post("/api/calendar/proposals/{proposal_id}/reject", response_model=CalendarProposalOut)
async def reject_calendar_proposal(
    proposal_id: str,
    session: AsyncSession = Depends(get_session),
) -> CalendarProposalOut:
    """Farmer rejects the proposed treatment schedule."""
    proposal = await session.get(CalendarEventProposal, proposal_id)
    if not proposal:
        raise HTTPException(404, "Calendar proposal not found")

    proposal.status = "rejected"
    await session.commit()
    return CalendarProposalOut.model_validate(proposal)




@router.post("/farms/{farm_id}/calendar-grants", response_model=CalendarSyncGrantOut, status_code=201)
async def create_calendar_grant(
    farm_id: str, req: CalendarGrantRequest, session: AsyncSession = Depends(get_session)
) -> CalendarSyncGrantOut:
    """The farmer just approved the consent modal (§9.15) -- record it. The
    actual expo-calendar write happens on the client immediately after this
    call succeeds; this endpoint only ever records consent, never performs
    a write itself."""
    farm = await session.get(Farm, farm_id)
    if farm is None:
        raise HTTPException(404, "farm not found")

    grant = CalendarSyncGrant(farm_id=farm_id, provider=str(getattr(req.provider, "value", req.provider)))
    session.add(grant)
    await session.commit()
    return CalendarSyncGrantOut.model_validate(grant)


@router.delete("/farms/{farm_id}/calendar-grants", status_code=204)
async def revoke_calendar_grant(farm_id: str, session: AsyncSession = Depends(get_session)) -> None:
    """Revokes every currently-live grant for this farm. Idempotent -- a
    farm with no live grant returns 204 either way, since the end state
    (no live grant) is what the caller actually wants."""
    grants = (
        await session.execute(
            select(CalendarSyncGrant).where(
                CalendarSyncGrant.farm_id == farm_id, CalendarSyncGrant.revoked_at.is_(None)
            )
        )
    ).scalars().all()
    for grant in grants:
        grant.revoked_at = now_kuching()
    await session.commit()


@router.get("/farms/{farm_id}/calendar-grants/status", response_model=CalendarGrantStatus)
async def calendar_grant_status(farm_id: str, session: AsyncSession = Depends(get_session)) -> CalendarGrantStatus:
    """Checked before every future write (pepperdex-rules skill §13) -- the
    app must call this (or otherwise know the answer) before assuming a
    prior approval still holds, since a grant can be revoked at any time."""
    grant = (
        await session.execute(
            select(CalendarSyncGrant)
            .where(CalendarSyncGrant.farm_id == farm_id, CalendarSyncGrant.revoked_at.is_(None))
            .order_by(CalendarSyncGrant.granted_at.desc())
        )
    ).scalars().first()
    return CalendarGrantStatus(
        granted=grant is not None,
        grant=CalendarSyncGrantOut.model_validate(grant) if grant else None,
    )


@router.post("/recommendations/{recommendation_id}/draft-calendar", response_model=DraftCalendarSyncResult)
async def draft_calendar_for_recommendation(
    recommendation_id: str, session: AsyncSession = Depends(get_session)
) -> DraftCalendarSyncResult:
    """On-demand draft generation, independent of whether the arbitration
    turn that produced this recommendation also called draft_calendar_sync
    itself. This is the reliable path: it does not depend on a local
    model's arbitration JSON reliably including a calendar draft (the same
    reliability gap already documented for defer_cause in
    app/agent/runner.py's _reconcile_spray_deferrals)."""
    rec = await session.get(Recommendation, recommendation_id)
    if rec is None:
        raise HTTPException(404, "recommendation not found")
    block = await session.get(Block, rec.block_id)
    if block is None:
        raise HTTPException(404, "block not found")

    return await draft_calendar_sync_flat(
        block_label=block.label,
        action_type=rec.action_type,
        recommended_at=rec.recommended_at.isoformat(),
        reason_ms=rec.reason_ms,
    )
