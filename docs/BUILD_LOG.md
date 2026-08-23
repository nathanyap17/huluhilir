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

## [Block B] Deterministic tools — compute_spread, get_weather, get_treatment, find_spray_window, diagnose_leaf

**Commit:** `Block B: five deterministic tools, unit tests, HTTP verification`

**Files added:**
- `backend/app/tools/{spread.py,weather.py,treatment.py,diagnose.py}`
- `backend/app/routers/tools.py` — wires all five tools to `POST /tools/<name>`, visible in `/docs`
- `backend/tests/{test_spread.py,test_treatment.py,test_diagnose.py,test_get_treatment.py}` (16 tests)
- `backend/pytest.ini` (`asyncio_mode = auto`)
- `backend/seed/weather_cache_kuching.json` (copied from `sandbox/`, see Block A entry)

**Schema changes on top of Block A** (contract wasn't quite right on the first pass — see bugs below):
- `FarmGraphEdge` gained `horizontal_dist_m` (path-finding needs real distance, not just weight) and `farmer_confirmed` (feeds confidence).
- `ComputeSpreadRequest` gained `elevation_tier` (confidence range selection).
- `FindSprayWindowRequest` gained `rainfast_hours` — it was missing entirely in the Block A draft; `find_spray_window` cannot look up the treatment table itself (it's a pure arithmetic tool per PLAN.md, no DB dependency), so the caller must resolve `rainfast_hours` from `get_treatment` first and pass it in.

**Key decisions:**
- `compute_spread`: Dijkstra over `horizontal_dist_m` restricted to already-downhill edges (`from.elevation_rank < to.elevation_rank`, re-checked defensively even though the graph is supposed to guarantee it) gives the shortest physical path; `cumulative_w` is the product of `flow_weight` along *that specific path*, not the max-weight path. `rain_factor = min(1, (rainfall_7d+forecast_7d)/100)` — a 100mm/week reference chosen as "a genuinely heavy Sarawak week," not derived from data (no calibration dataset exists — see `docs/PROJECT_SPEC.md` §3 L2 roadmap note). `eta_days = DAYS_PER_HOP(2) * hops / max(0.2, rain_factor)`, floors at 1 day, `None` below `RISK_FLOOR=0.05`. Confidence interpolates within the tier's documented range (`docs/PROJECT_SPEC.md` §4) by the fraction of farmer-confirmed edges on the path.
- `get_weather`: live call to `api.data.gov.my`, catches `httpx.HTTPError`/`ValueError`/`KeyError` and falls back to the cached asset. Qualitative forecast text ("Ribut petir di beberapa tempat", "Hujan lebat", ...) is mapped to an mm/probability estimate via ordered keyword matching — **this is a documented heuristic, not a measurement**; DID Sarawak's real rain-gauge API is still DNS-unreachable per EXP-9, so there is no live numeric rainfall source at all right now.
- `find_spray_window`: a window starting at forecast point *t* is `rain_free` if no point in `[t, t+rainfast_hours)` — **half-open interval** — has `rainfall_mm >= 5.0`. The 5mm threshold and half-open boundary are a judgment call (rain landing exactly at `t+rainfast_hours` means the product already had its full dry window, so it doesn't invalidate). `defer_cause="rainfast"` when zero windows are viable — this is the flag the root agent's arbitration reads.
- `diagnose_leaf`: loads the ONNX session, labels, and preprocess config with `@lru_cache(maxsize=1)` so the model loads once per process, not per request. Preprocessing follows `classifier/best-model/preprocess.json` exactly (224×224, ImageNet mean/std, CHW). `check_capture_mismatch()` is a standalone pure function (EXP-14) so it's testable without the model loaded.

**Bugs found and fixed during verification (this is why the log exists):**
1. **`find_spray_window` referenced `req.rainfast_hours` that didn't exist on the schema.** `FindSprayWindowRequest` only had `treatment_id` + `forecast` in the Block A draft. Caught immediately by `pytest` (`AttributeError`) — fixed by adding the field to the schema rather than fetching it from the DB inside a tool meant to stay pure-arithmetic.
2. **Router called `.value` on an already-plain-string enum field.** `ORMModel` sets `use_enum_values=True`, so `req.predicted_class` deserializes to a `str`, not an Enum member — `req.predicted_class.value` raised `AttributeError: 'str' object has no attribute 'value'`. Fixed in `app/routers/tools.py`; worth remembering for *every* future router touching an enum field on an `ORMModel` schema.
3. **`get_weather` fallback path itself crashed.** `CACHE_PATH.read_text(encoding="utf-8")` hit `JSONDecodeError: Unexpected UTF-8 BOM` because the asset was captured via PowerShell (which writes UTF-8 with BOM by default). Fixed with `encoding="utf-8-sig"`. Caught only because the live call was deliberately exercised first (a 301 redirect on the un-redirected `httpx.get` triggered the fallback path, which then failed for an unrelated reason) — **a lesson to always exercise the fallback path explicitly in future tools, not just trust the try/except.**
4. **Live `api.data.gov.my` returns a bare JSON list; the cached asset wraps it as `{"value": [...], "Count": N}`.** These are two different response shapes for what should be the same API — the cache was captured through a different code path (raw REST call vs. whatever produced the sandbox artifact). `_rows_from_data_gov_my_payload()` now accepts either. **If data.gov.my's API shape changes again, this is the first place to check.**
5. Also fixed: `httpx.get(...)` needs `follow_redirects=True` — `api.data.gov.my/weather/forecast` 301s to a trailing-slash URL by default.

**Verified (how):**
- `pytest tests/` — 14/14 pass, including a real ONNX forward pass on a synthetic image (not an accuracy test, just confirms the checkpoint loads and produces a valid 6-class softmax summing to 1.0).
- Live server (`uvicorn`) exercised over real HTTP for all five `/tools/*` endpoints against the seeded demo farm + a synthetic test image — see commit message for the exact request/response pairs used.
- `get_weather` verified in **both** modes: live (`is_cached_fallback: False`, real forecast returned for station `Tn187`) and forced-fallback (loaded `weather_cache_kuching.json` directly, `is_cached_fallback: True`).
- `compute_spread` verified acyclic-safe: an intentionally-added uphill edge (blk3→blk1) in a test fixture is excluded, not followed, and does not hang.

**Known gaps / placeholders:**
- `get_weather`'s farm→station resolution is hardcoded to `Tn187` regardless of `farm_id` — real per-farm station binding is a Block D/Flutter-setup-flow concern (`farms.weather_station_id`), not yet wired here.
- The qualitative-forecast-to-mm mapping in `weather.py` is a judgment call with no ground truth to validate against (DID Sarawak's real gauge API is still unreachable — EXP-9). State this as an estimate if a judge asks how rainfall_mm is derived.
- `diagnose_leaf` takes `image_uri` as a local filesystem path today; the real observation pipeline (phone upload → stored URI → this tool) doesn't exist until Flutter (Block D) and an upload endpoint (still needed — no `/observations` router yet).
- `pytest.ini` sets `asyncio_mode = auto` so async fixtures/tests (added for `get_treatment`, see `tests/test_get_treatment.py`) run without per-test decorators — keep this in mind if async tests are added to other files and don't seem to run.

---
