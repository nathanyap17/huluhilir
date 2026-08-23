"""get_treatment against a real (in-memory) DB session -- the one tool with a
DB dependency that Block B's initial HTTP smoke test covered manually only.
"""
import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models.base import Base
from app.models.knowledge import TreatmentOption
from app.tools.treatment import get_treatment


@pytest.fixture
async def session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as s:
        s.add(TreatmentOption(
            treatment_id="metalaxyl_drench", name_ms="x", name_en="y", type="systemic",
            applies_to=["collar_lesion", "defoliation_wilt"], rainfast_hours=24,
            application_method="drench", source_ref="test",
        ))
        s.add(TreatmentOption(
            treatment_id="trichoderma_biocontrol", name_ms="x", name_en="y", type="biological",
            applies_to=["healthy_collar"], rainfast_hours=None,
            application_method="drench", source_ref="test",
        ))
        await s.commit()
        yield s
    await engine.dispose()


@pytest.mark.asyncio
async def test_returns_only_matching_treatments(session):
    result = await get_treatment(session, "collar_lesion")
    ids = {o.treatment_id for o in result.options}
    assert ids == {"metalaxyl_drench"}


@pytest.mark.asyncio
async def test_hard_rule_never_invents_a_treatment_outside_the_table(session):
    """huluhilir-rules skill §1: the agent may only output a treatment that
    exists in treatment_options. Verifies get_treatment returns [] rather
    than fabricating anything for a class no seeded row covers."""
    result = await get_treatment(session, "unrelated")
    assert result.options == []
