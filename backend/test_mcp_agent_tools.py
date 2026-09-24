import asyncio
import os
import sys
from pathlib import Path

# Add backend directory to sys.path to allow imports
BACKEND_DIR = Path(__file__).resolve().parent
sys.path.append(str(BACKEND_DIR))

from app.agent.tools import (
    check_calendar_schedule,
    check_calendar_availability,
    schedule_treatment_event,
)

async def test_mcp_tools():
    print("--- Testing check_calendar_schedule ---")
    schedule_res = await check_calendar_schedule(max_results=3)
    print("Schedule Result:", schedule_res)
    print()

    print("--- Testing check_calendar_availability ---")
    avail_res = await check_calendar_availability(
        start_iso="2026-09-24T10:00:00+08:00",
        end_iso="2026-09-24T11:00:00+08:00"
    )
    print("Availability Result:", avail_res)
    print()

    print("--- Testing schedule_treatment_event ---")
    event_res = await schedule_treatment_event(
        title="Test Treatment from Tool",
        start_iso="2026-09-25T14:00:00+08:00",
        end_iso="2026-09-25T15:00:00+08:00",
        description="Testing MCP tool execution.",
        location="Farm Block A",
    )
    print("Schedule Event Result:", event_res)
    print()

if __name__ == "__main__":
    asyncio.run(test_mcp_tools())
