"""Hybrid search (knowledge_docs_fts + keyword overlap) and query_farm_history.
docs/PROJECT_SPEC.md §3 L3.
"""
import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db import init_db
from app.models.base import Base
from app.models.core import Block, Farm, User
from app.models.diagnosis import Diagnosis, Observation
from app.models.knowledge import KnowledgeDoc
from app.schemas.knowledge import RetrievalQuery
from app.tools.farm_history import query_farm_history
from app.tools.knowledge import retrieve_knowledge
from app.tools.knowledge_fts import rebuild_fts_index, search_fts


@pytest_asyncio.fixture
async def session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.execute(text(
            "CREATE VIRTUAL TABLE IF NOT EXISTS knowledge_docs_fts USING fts5(doc_id UNINDEXED, content)"
        ))
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as s:
        yield s
    await engine.dispose()


async def _seed_docs(session):
    from app.tools.knowledge import get_model
    model = get_model()
    session.add_all([
        KnowledgeDoc(doc_id="d1", namespace="advisory", title="Root rot drainage",
                     chunk_index=0, content="Improving drainage reduces foot rot losses significantly.",
                     citation="MPB 2024",
                     embedding=model.encode("Root rot drainage\nImproving drainage reduces foot rot losses significantly.").tolist()),
        KnowledgeDoc(doc_id="d2", namespace="advisory", title="Fungicide timing",
                     chunk_index=0, content="Contact fungicides wash off in heavy rain.",
                     citation="MPB 2024",
                     embedding=model.encode("Fungicide timing\nContact fungicides wash off in heavy rain.").tolist()),
        KnowledgeDoc(doc_id="d3", namespace="authoritative", title="Dose table",
                     chunk_index=0, content="Metalaxyl dose is 2g per litre of water.",
                     citation="DOA rules",
                     embedding=model.encode("Dose table\nMetalaxyl dose is 2g per litre of water.").tolist()),
    ])
    await session.commit()
    await rebuild_fts_index(session)
    await session.commit()


@pytest.mark.asyncio
async def test_fts_index_rebuild_and_search(session):
    await _seed_docs(session)
    hits = await search_fts(session, "drainage rot", top_k=5)
    assert "d1" in hits


@pytest.mark.asyncio
async def test_fts_search_degrades_to_empty_on_bad_query(session):
    await _seed_docs(session)
    # Punctuation-only query has no valid tokens -- must not raise.
    assert await search_fts(session, "???", top_k=5) == []


@pytest.mark.asyncio
async def test_retrieve_knowledge_never_returns_authoritative_by_default(session):
    await _seed_docs(session)
    hits = await retrieve_knowledge(session, RetrievalQuery(query="dose metalaxyl"))
    assert all(h.doc.namespace != "authoritative" for h in hits)


@pytest.mark.asyncio
async def test_retrieve_knowledge_boosts_docs_found_by_fts(session):
    await _seed_docs(session)
    # "drainage" is found by BOTH signals for d1 (vector cosine similarity + FTS5 hit)
    # -- score should include the 0.5 FTS boost on top of vector similarity (> 0.8).
    hits = await retrieve_knowledge(session, RetrievalQuery(query="drainage", namespaces=["advisory"]))
    assert hits, "expected at least one hit"
    assert hits[0].doc.doc_id == "d1"
    assert hits[0].score > 0.8, "score should include the FTS boost on top of vector similarity"


@pytest.mark.asyncio
async def test_query_farm_history_filters_by_block_and_since_days(session):
    user = User(display_name="Nathan", district="Julau")
    session.add(user)
    await session.flush()
    farm = Farm(user_id=user.user_id, name="Kebun Ujian", centroid_lat=1.5, centroid_lon=110.3)
    session.add(farm)
    await session.flush()
    block_a = Block(farm_id=farm.farm_id, label="A", photo_uri="x", centroid_lat=1.5, centroid_lon=110.3, elevation_rank=1)
    block_b = Block(farm_id=farm.farm_id, label="B", photo_uri="x", centroid_lat=1.5, centroid_lon=110.3, elevation_rank=2)
    session.add_all([block_a, block_b])
    await session.flush()

    from app.models.base import now_kuching
    obs_a = Observation(block_id=block_a.block_id, user_id=user.user_id, image_uri="x",
                         image_hash="h1", capture_target="collar", captured_at=now_kuching())
    obs_b = Observation(block_id=block_b.block_id, user_id=user.user_id, image_uri="x",
                         image_hash="h2", capture_target="collar", captured_at=now_kuching())
    session.add_all([obs_a, obs_b])
    await session.flush()
    session.add_all([
        Diagnosis(observation_id=obs_a.observation_id, predicted_class="collar_lesion",
                  confidence=0.9, all_scores={}, below_threshold=False, model_version="v1"),
        Diagnosis(observation_id=obs_b.observation_id, predicted_class="healthy_collar",
                  confidence=0.95, all_scores={}, below_threshold=False, model_version="v1"),
    ])
    await session.commit()

    result = await query_farm_history(session, farm.farm_id, block_id=block_a.block_id)
    assert len(result["diagnoses"]) == 1
    assert result["diagnoses"][0]["predicted_class"] == "collar_lesion"

    result_all = await query_farm_history(session, farm.farm_id)
    assert len(result_all["diagnoses"]) == 2

    # since_days excludes anything older than the cutoff -- prove it by
    # backdating one observation well outside a 1-day window.
    from datetime import timedelta
    obs_a.captured_at = now_kuching() - timedelta(days=10)
    await session.commit()

    result_recent = await query_farm_history(session, farm.farm_id, since_days=1)
    assert len(result_recent["diagnoses"]) == 1
    assert result_recent["diagnoses"][0]["block_id"] == block_b.block_id
