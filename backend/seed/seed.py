"""Load seed data into the database. Run from backend/: `python -m seed.seed`.

Loads: rules.json -> treatment_options, templates.json -> speech_templates,
slot_vocabulary.json -> slot_vocabulary, demo_farm.json -> user/farm/blocks
+ derived flow_edges (k-NN, k=3, acyclic by elevation_rank per
docs/PROJECT_SPEC.md §5).
"""
import asyncio
import json
import math
from pathlib import Path

from sqlalchemy import select

from app.db import SessionLocal, init_db
from app.models.core import Block, Farm, FlowEdge, User
from app.models.knowledge import KnowledgeDoc, TreatmentOption
from app.models.speech import SlotVocabulary, SpeechTemplate

SEED_DIR = Path(__file__).parent


def load(name: str) -> dict:
    return json.loads((SEED_DIR / name).read_text(encoding="utf-8"))


def haversine_m(lat1, lon1, lat2, lon2) -> float:
    R = 6_371_000
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlambda / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


async def seed_treatments(session):
    data = load("rules.json")
    for t in data["treatments"]:
        exists = await session.get(TreatmentOption, t["treatment_id"])
        if exists:
            continue
        session.add(TreatmentOption(
            treatment_id=t["treatment_id"],
            name_ms=t["name_ms"],
            name_en=t["name_en"],
            type=t["type"],
            applies_to=t["applies_to"],
            rainfast_hours=t.get("rainfast_hours"),
            dose_text_ms=t.get("dose_text_ms"),
            application_method=t["application_method"],
            reentry_hours=t.get("reentry_hours"),
            source_ref=t["source_ref"],
            source_url=t.get("source_url"),
        ))
    print(f"  treatment_options: {len(data['treatments'])}")


async def seed_knowledge(session):
    data = load("knowledge_docs.json")
    
    # Lazy-load the embedding model so it doesn't slow down imports for non-seeding tasks
    from sentence_transformers import SentenceTransformer
    model = SentenceTransformer("all-MiniLM-L6-v2")
    
    for d in data["docs"]:
        exists = await session.get(KnowledgeDoc, d["doc_id"])
        if exists:
            continue
            
        text_to_embed = f"{d['title']}\n{d['content']}"
        embedding = model.encode(text_to_embed).tolist()
        
        session.add(KnowledgeDoc(
            doc_id=d["doc_id"],
            namespace=d["namespace"],
            title=d["title"],
            publisher=d.get("publisher"),
            chunk_index=d["chunk_index"],
            content=d["content"],
            embedding=embedding,
            citation=d["citation"],
        ))
    print(f"  knowledge_docs: {len(data['docs'])}")


async def seed_speech(session):
    templates = load("templates.json")
    for t in templates["templates"]:
        exists = await session.get(SpeechTemplate, t["template_id"])
        if exists:
            continue
        session.add(SpeechTemplate(
            template_id=t["template_id"],
            language=t["language"],
            category=t["category"],
            text_template=t["text_template"],
            slots=t["slots"],
            audio_clip_uri=t.get("audio_clip_uri"),
            translated_by=t.get("translated_by"),
            verified=t.get("verified", False),
        ))
    print(f"  speech_templates: {len(templates['templates'])}")

    vocab = load("slot_vocabulary.json")
    for s in vocab["slots"]:
        exists = await session.get(SlotVocabulary, s["slot_id"])
        if exists:
            continue
        session.add(SlotVocabulary(
            slot_id=s["slot_id"],
            slot_type=s["slot_type"],
            text_ms=s["text_ms"],
            text_iba=s.get("text_iba"),
            verified=s.get("verified", False),
        ))
    print(f"  slot_vocabulary: {len(vocab['slots'])}")


async def seed_demo_farm(session):
    data = load("demo_farm.json")

    existing_farm = (await session.execute(
        select(Farm).where(Farm.name.in_([data["farm"]["name"], "Kebun Demo HuluHilir", "Kebun Demo PepperDex"]))
    )).scalar_one_or_none()
    
    from app.models.agent import AgentRun, Recommendation
    from app.models.diagnosis import RiskAssessment
    from app.ids import new_ulid
    from app.models.base import now_kuching

    if existing_farm:
        # v2 rename: a DB seeded under the old brand shows "Kebun Demo
        # HuluHilir" to everyone who taps "Try the demo farm". Rename the row
        # in place (same farm_id, same data) -- local and Cloud SQL alike, on
        # their next startup; no connection settings change.
        if existing_farm.name != data["farm"]["name"]:
            print(f"  demo farm: renamed '{existing_farm.name}' -> '{data['farm']['name']}'")
            existing_farm.name = data["farm"]["name"]
        # Check if recommendations and risk_assessments exist for this farm's blocks
        existing_risk = (await session.execute(
            select(RiskAssessment).join(Block, RiskAssessment.block_id == Block.block_id)
            .where(Block.farm_id == existing_farm.farm_id)
        )).scalars().first()

        if not existing_risk:
            blocks = (await session.execute(
                select(Block).where(Block.farm_id == existing_farm.farm_id).order_by(Block.elevation_rank)
            )).scalars().all()
            if blocks:
                run_id = new_ulid()
                session.add(AgentRun(
                    run_id=run_id,
                    farm_id=existing_farm.farm_id,
                    trigger="manual",
                    llm_model="seed",
                    completed_at=now_kuching(),
                    status="ok",
                ))
                session.add(Recommendation(
                    run_id=run_id,
                    block_id=blocks[0].block_id,
                    action_type="spray",
                    recommended_at=now_kuching(),
                    reason_ms="Semburan racun kulat diperlukan untuk mencegah penyebaran Penyakit Reput Akar.",
                    speech_template_id="_adhoc",
                    sequence=0,
                ))
                session.add(RiskAssessment(
                    run_id=run_id,
                    block_id=blocks[0].block_id,
                    source_block_id=blocks[0].block_id,
                    risk_score=0.85,
                    risk_band="high",
                    confidence=0.92,
                    eta_days=3,
                    rainfall_7d_mm=45.2,
                    forecast_7d_mm=22.0,
                    elevation_tier_used="minimal",
                    model_version="l2_deterministic_v1",
                    computed_at=now_kuching(),
                    is_estimate=True,
                ))
                print("  demo farm: backfilled missing mock Recommendation and RiskAssessment")
        else:
            print("  demo farm already seeded, skipping")

        # (Removed 2026-09-23) A backfill used to run here on EVERY startup that
        # gave any recommendation on ANY farm -- real farmers' included -- a
        # constant risk row (0.85 / 0.92 / 3 days / 45.2 mm). That is why the
        # Home bento tiles never changed between diagnoses, and it presented
        # invented numbers as spread-model output (rule 8). Real rows now come
        # only from compute_spread (app/agent/runner.py _deterministic_spread).
        return

    user = User(**data["user"])
    session.add(user)
    await session.flush()

    # Demo farm represents an already-onboarded farm ready for diagnosis
    # (PLAN.md Block F "seed demo farm, known-good state") -- setup_completed_at
    # set so SetupCoordinator short-circuits immediately rather than looping.
    farm = Farm(user_id=user.user_id, setup_completed_at=now_kuching(), **data["farm"])
    session.add(farm)
    await session.flush()

    blocks = []
    for b in data["blocks"]:
        block = Block(
            farm_id=farm.farm_id,
            label=b["label"],
            photo_uri="seed/placeholder.jpg",
            centroid_lat=b["centroid_lat"],
            centroid_lon=b["centroid_lon"],
            elevation_rank=b["elevation_rank"],
            drainage=b["drainage"],
            vine_count=b.get("vine_count"),
            current_state=b.get("current_state", "protected"),
        )
        session.add(block)
        blocks.append(block)
    await session.flush()

    # k-NN (k=3) candidates, keep only upslope -> downslope (acyclic by construction)
    K = 3
    for i, from_block in enumerate(blocks):
        dists = sorted(
            ((haversine_m(from_block.centroid_lat, from_block.centroid_lon,
                          to.centroid_lat, to.centroid_lon), to)
             for j, to in enumerate(blocks) if j != i),
            key=lambda pair: pair[0],
        )[:K]
        for dist_m, to_block in dists:
            if from_block.elevation_rank >= to_block.elevation_rank:
                continue  # only from.rank < to.rank -- upslope to downslope
            flow_weight = round(1.0 / (1.0 + dist_m / 50.0), 3)  # closer -> higher weight, no slope data yet
            session.add(FlowEdge(
                farm_id=farm.farm_id,
                from_block_id=from_block.block_id,
                to_block_id=to_block.block_id,
                horizontal_dist_m=round(dist_m, 1),
                flow_weight=flow_weight,
                source="farmer",
                farmer_confirmed=True,
            ))

    # Add a mock Recommendation and RiskAssessment to populate the Priority Action Card bento tiles
    run_id = new_ulid()
    session.add(AgentRun(
        run_id=run_id,
        farm_id=farm.farm_id,
        trigger="manual",
        llm_model="seed",
        completed_at=now_kuching(),
        status="ok",
    ))
    session.add(Recommendation(
        run_id=run_id,
        block_id=blocks[0].block_id,
        action_type="spray",
        recommended_at=now_kuching(),
        reason_ms="Semburan racun kulat diperlukan untuk mencegah penyebaran Penyakit Reput Akar.",
        speech_template_id="_adhoc",
        sequence=0,
    ))
    session.add(RiskAssessment(
        run_id=run_id,
        block_id=blocks[0].block_id,
        source_block_id=blocks[0].block_id,
        risk_score=0.85,
        risk_band="high",
        confidence=0.92,
        eta_days=3,
        rainfall_7d_mm=45.2,
        forecast_7d_mm=22.0,
        elevation_tier_used="minimal",
        model_version="l2_deterministic_v1",
        computed_at=now_kuching(),
        is_estimate=True,
    ))

    print(f"  demo farm: 1 user, 1 farm, {len(blocks)} blocks, flow edges derived (k-NN k={K})")



async def main():
    await init_db()
    async with SessionLocal() as session:
        print("Seeding treatment_options ...")
        await seed_treatments(session)
        print("Seeding knowledge_docs ...")
        await seed_knowledge(session)
        print("Seeding speech_templates + slot_vocabulary ...")
        await seed_speech(session)
        print("Seeding demo farm ...")
        await seed_demo_farm(session)
        await session.commit()
    print("Done.")


if __name__ == "__main__":
    asyncio.run(main())
