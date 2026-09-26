"""Next best check (2026-09-27): after each diagnosis the Advisor says WHEN
the next check is most useful -- a few days after the next heavy rain
(kb_051), after an approved treatment has had time to work, or on the
routine interval -- and never sooner than the incubation floor."""
from datetime import timedelta

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models.agent import AgentRun, CalendarEventProposal, Recommendation
from app.models.base import Base, now_kuching
from app.models.core import Block, Farm, User
from app.schemas.advisor import AdvisorVerdictOut
from app.tools.advisor import next_best_check
from seed.seed import seed_treatments


@pytest_asyncio.fixture
async def session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with async_sessionmaker(engine, expire_on_commit=False)() as s:
        await seed_treatments(s)
        user = User(display_name="N", district="Sibu")
        s.add(user)
        await s.flush()
        farm = Farm(user_id=user.user_id, name="Kebun", centroid_lat=2.3, centroid_lon=111.8)
        s.add(farm)
        await s.flush()
        block = Block(farm_id=farm.farm_id, label="Blok 1", photo_uri="x", centroid_lat=2.3,
                      centroid_lon=111.8, elevation_rank=1)
        s.add(block)
        await s.commit()
        yield s, farm.farm_id, block.block_id
    await engine.dispose()


def verdict(farm_id, *, urgency="none", reason="no_action_needed", last_days_ago=None, protected=True):
    now = now_kuching()
    return AdvisorVerdictOut(
        farm_id=farm_id, urgency=urgency, reason_code=reason, reason_ms="x",
        last_cycle_at=None if last_days_ago is None else now - timedelta(days=last_days_ago),
        days_since_last_cycle=21 if last_days_ago is None else last_days_ago,
        rain_since_last_cycle_mm=0.0, blocks_all_protected=protected, computed_at=now,
    )


def day(n):
    return (now_kuching() + timedelta(days=n)).date()


@pytest.mark.asyncio
async def test_heavy_rain_ahead_sets_the_check_a_few_days_after_it(session):
    s, farm_id, _ = session
    v = await next_best_check(s, farm_id, verdict(farm_id, last_days_ago=4),
                              [(day(1), 8.0), (day(3), 40.0), (day(4), 25.0)])
    assert v.suggested_date == day(5) and v.days_until_recommended == 5
    assert v.next_check_basis == "rain_pulse"
    assert "Heavy rain" in v.next_check_en and "Hujan lebat" in v.next_check_ms


@pytest.mark.asyncio
async def test_an_approved_drench_brings_the_check_forward_to_its_follow_up(session):
    s, farm_id, block_id = session
    run = AgentRun(farm_id=farm_id, trigger="manual", llm_model="t")
    s.add(run)
    await s.flush()
    rec = Recommendation(run_id=run.run_id, block_id=block_id, sequence=1, action_type="drench",
                         treatment_id="metalaxyl_drench", recommended_at=now_kuching(), reason_ms="r")
    s.add(rec)
    await s.flush()
    start = now_kuching() + timedelta(days=1)
    s.add(CalendarEventProposal(farm_id=farm_id, run_id=run.run_id, recommendation_id=rec.recommendation_id,
                                title="Drench", start_time=start, end_time=start + timedelta(hours=1),
                                description="d", status="approved", approved_by_farmer=True))
    await s.commit()
    # Rain-fast 24 h (rulebook) + 3 days after a treatment on day 1 -> day 5;
    # the heavy rain on day 6 would give day 8, so the follow-up wins.
    v = await next_best_check(s, farm_id, verdict(farm_id, last_days_ago=4), [(day(6), 40.0)])
    assert v.suggested_date == day(5)
    assert v.next_check_basis == "treatment_follow_up"


@pytest.mark.asyncio
async def test_a_healthy_dry_farm_waits_for_the_routine_interval(session):
    s, farm_id, _ = session
    v = await next_best_check(s, farm_id, verdict(farm_id, reason="protected_stable", last_days_ago=2),
                              [(day(1), 8.0), (day(2), 0.0)])
    assert v.suggested_date == day(12)  # 14 days after the last check, no heavy rain ahead
    assert v.next_check_basis == "routine"


@pytest.mark.asyncio
async def test_never_sooner_than_the_incubation_floor_after_the_last_check(session):
    s, farm_id, _ = session
    # Checked yesterday; heavy rain today would suggest day 2, and the floor
    # (3 days after the last check) is also day 2 -- never earlier.
    v = await next_best_check(s, farm_id, verdict(farm_id, last_days_ago=1), [(day(0), 40.0)])
    assert v.suggested_date == day(2)
    # Checked today with heavy rain today: the floor pushes it to day 3.
    v = await next_best_check(s, farm_id, verdict(farm_id, last_days_ago=0), [(day(0), 40.0)])
    assert v.suggested_date == day(3)


@pytest.mark.asyncio
async def test_a_check_due_now_says_today_and_a_new_farm_can_start_any_time(session):
    s, farm_id, _ = session
    v = await next_best_check(s, farm_id, verdict(farm_id, urgency="high", reason="heavy_rain_recent",
                                                   last_days_ago=5), [])
    assert v.suggested_date == day(0) and v.next_check_en.startswith("Next check: today")
    v = await next_best_check(s, farm_id, verdict(farm_id), [])
    assert v.suggested_date == day(0) and v.next_check_basis == "first_check"
