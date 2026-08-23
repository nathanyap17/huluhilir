from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.db import SessionLocal, init_db
from app.routers import agent, dashboard, diagnosis, health, media, setup, tools


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    # Idempotent -- each function checks for existing rows before inserting.
    # Runs on every startup because Cloud Run's filesystem is ephemeral: a
    # fresh instance boots with an empty DB, and "reseeded on redeploy" is
    # the documented cloud behaviour (docs/CLAUDE.md § Two deployment
    # targets), not something a separate init job handles. A no-op locally
    # once the dev DB is already seeded.
    from seed.seed import seed_demo_farm, seed_knowledge, seed_speech, seed_treatments

    async with SessionLocal() as session:
        await seed_treatments(session)
        await seed_knowledge(session)
        await seed_speech(session)
        await seed_demo_farm(session)
        await session.commit()
    yield


app = FastAPI(
    title="HuluHilir API",
    description="Terrain-aware agentic early warning for Phytophthora foot rot in Sarawak black pepper.",
    version="0.1.0",
    lifespan=lifespan,
)

# Phone reaches the API over the team's own hotspot (LOCAL) or a public HTTPS
# endpoint (CLOUD stretch) -- CORS wide open, there is no browser-based client.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(tools.router)
app.include_router(agent.router)
app.include_router(setup.router)
app.include_router(media.router)
app.include_router(diagnosis.router)
app.include_router(dashboard.router)
