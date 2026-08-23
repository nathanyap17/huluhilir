# BUILD_LOG.md — Implementation & Debugging Trail

> Append-only. One entry per block/session of work. Purpose: when something
> breaks at hour 20, this file tells you *what exists, why it was built that
> way, what was verified, and what is still a placeholder* — without having
> to re-read every diff. `git log` has the "what changed"; this has the
> "why" and "what's still fake."
>
> Conventions: newest entry at the bottom. Each entry lists commit(s), files
> touched, key design decisions, what was verified and how, and known gaps
> / TODOs / placeholder data still in the tree.

---

## [Block A] Foundation — repo, schemas, models, FastAPI skeleton, seed data

**Commits:**
- `Initial commit: prep-window assets and project docs` — prep assets only, no app code
- `Block A: foundation — schemas, models, FastAPI skeleton, seed data`

**Files added:**
- `backend/app/schemas/` — `enums.py`, `common.py`, `farm.py`, `diagnosis.py`, `spread.py`, `treatment.py`, `knowledge.py`, `weather.py`, `speech.py`, `agent.py`, `advisor.py`, `dashboard.py`
- `backend/app/models/` — `base.py`, `core.py`, `diagnosis.py`, `knowledge.py`, `agent.py`, `speech.py`, `weather.py`
- `backend/app/{main.py,db.py,config.py,ids.py}`
- `backend/app/routers/health.py`
- `backend/Dockerfile`, `backend/requirements.txt`, `backend/.env.example`
- `tts/main.py`, `tts/Dockerfile`, `tts/requirements.txt`
- `docker-compose.yml`, `.gitignore`
- `backend/seed/{rules.json,templates.json,slot_vocabulary.json,demo_farm.json,seed.py}`

**Key decisions:**
- Pydantic schemas written before SQLAlchemy models — the contract everything else depends on (PLAN.md Block A). `ORMModel` base class (`from_attributes=True`) so DB rows convert to API responses without a manual mapping layer.
- ULIDs generated client-side (`app/ids.py`, Crockford base32, timestamp+random) — offline capture must not depend on DB autoincrement.
- SQLAlchemy 2.0 `Mapped[]`/`mapped_column()` style, async engine (`aiosqlite`). `create_all()` on FastAPI `lifespan` startup — Alembic explicitly skipped per PLAN.md.
- CORS wide open (`allow_origins=["*"]`) — there is no browser client, only the Flutter app; not a real attack surface for this deployment shape.
- Two Docker services: `api` (8000) and `tts` (8001), both bound to `0.0.0.0` so the phone can reach them over the team hotspot. `api` reaches host-native Ollama via `host.docker.internal` (`extra_hosts: host-gateway`).
- `tts/main.py` is a working MMS-TTS synthesis endpoint (VITS via `transformers`, seeded per EXP-2 finding that VITS is stochastic) — this is the OPTIMISED tier; MVP speech is pre-recorded clips played from the Flutter app directly, not through this service.

**Verified (how):**
- `from app.main import app; from app.models import Base` imports clean, `Base.metadata.tables` shows all 23 tables from `docs/DATA_MODEL.md`.
- `python -m seed.seed` against a fresh sqlite file populates 6 treatments, 25 speech templates, 25 slot-vocab entries, 1 demo farm with 6 blocks and k-NN-derived flow edges — no errors.
- `uvicorn app.main:app` boots; `curl /health` → `{"ok":true,"service":"huluhilir-api"}`; `/openapi.json` serves and lists `/health`.
- Did **not** verify: Docker Compose build (not run this session — no Docker invoked), TTS container (transformers/torch not installed in the smoke-test venv), phone-over-hotspot reachability (no phone connected — EXP-3 still blocked per VALIDATION_CHECKLIST.md).

**Known gaps / placeholders (do not treat as real on demo day):**
- `backend/seed/rules.json` — dose/timing text is agronomically plausible but `source_ref` citations are **unverified placeholders** (`_verified_pending: true` on 5 of 6 entries). Abraham must confirm against actual MPB/DOA documents before the pitch (WORKSPACE_SETUP.md item 0.9). The `clear_drainage` entry is backed by the cited PROJECT_SPEC.md field study and is *not* pending.
- `backend/seed/templates.json` / `slot_vocabulary.json` — all `text_iba` fields are `null`, `verified: false`. BM text is prep-drafted, not native-checked either. EXP-12 is still blocked (needs an Iban speaker).
- `backend/seed/demo_farm.json` — synthetic placeholder farm near the EXP-10 SRTM test point (1.5533, 110.3592), **not** a real walk. Must be replaced with Nathan's actual recorded walk (PLAN.md task 0.14) before the pitch — VALIDATION_CHECKLIST.md decision #2 explicitly wants the real walk "to prove the loop."
- No routers/endpoints exist yet beyond `/health` — Block B adds the five deterministic tools.
- `google-adk` is in `requirements.txt` but nothing imports it yet (Block C).

---
