from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.db import init_db
from app.routers import agent, dashboard, diagnosis, health, media, setup, tools


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
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
