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

## [Cloud Gate] Cloud account setup — project, billing, APIs, Firebase, Vertex AI decision

**Not a code commit** — this entry covers GCP/Firebase account configuration done ahead of the 17:00 gate (`WORKSPACE_SETUP.md` explicitly treats this as "configuration, not code," permitted regardless of build-window timing). Recorded here in detail because it took three project attempts and two distinct 403 errors to get working — if cloud deploy breaks later, read this before re-diagnosing from scratch.

**End state:**
- GCP project: **`sfws-aicc-workspace-1`**, owned by `a personal Google account`
- Region: `asia-southeast1`
- Billing: active (confirmed by successfully enabling `aiplatform.googleapis.com`, which requires it)
- APIs enabled: `run`, `artifactregistry`, `aiplatform` (Vertex AI), `sqladmin`, `cloudbuild`, `firebase`
- Firebase: attached to the project, default Hosting site auto-provisioned (`hostingSite: sfws-aicc-workspace-1`)
- LLM auth decision: **Vertex AI via the Cloud Run service's own service account** (`LITELLM_MODEL=vertex_ai/gemini-2.0-flash`), not a raw `GEMINI_API_KEY` — no key to manage, no key to leak, auth is automatic via Application Default Credentials on Cloud Run's metadata server.

**Three projects were tried before this one worked — in order:**

1. **`model-block-503304-g2`** (account `a second personal account`) — pre-existing from earlier prep, never actually used; superseded once the team decided on a dedicated project name.
2. **`aicc-workspace-sfws-1`** (account `a university student account`, a UNIMAS student email) — **abandoned.** This account had `roles/owner` on the project (confirmed via `gcloud projects get-iam-policy`), yet `gcloud billing accounts list` / enabling `cloudbilling.googleapis.com` failed with `PERMISSION_DENIED`. Root cause: `gcloud projects describe --format="yaml(parent)"` showed `parent: {type: organization, id: '<org-id redacted>'}` — the project sits inside a UNIMAS-managed Google Cloud Organization, which enforces an org policy blocking billing/service enablement regardless of project-level IAM role. **This cannot be fixed by the project owner** — it needs a UNIMAS Workspace/Cloud org admin to lift, which is out of reach on a competition timeline. **Lesson: if a `gcloud services enable` or billing command 403s despite the caller being Owner, check `gcloud projects describe --format="yaml(parent)"` first — an organization parent is the tell.**
3. **`sfws-aicc-workspace-1`** (account `a personal Google account`) — **this is the one that worked.** `gcloud projects describe` on this one shows no `parent:` field at all (a bare personal-account project), so no org policy applies. `a personal Google account` has `roles/owner`.

**Bugs hit and fixed on the working project:**

1. **Stale ADC quota project caused `billing`-family commands to reference the wrong (blocked) project number even after `gcloud config set project` was updated correctly.** `gcloud config list` showed the right project, but `gcloud billing accounts list` kept failing against project number `681255809395` (the *old*, org-blocked `aicc-workspace-sfws-1`'s number) instead of the new project. `gcloud auth application-default set-quota-project <new-project>` itself failed too (`the account in ADC does not have serviceusage.services.use on this project` — the cached ADC credential belonged to yet another identity). **Workaround that actually mattered: plain `gcloud services enable <api> --project=<id>` and direct REST calls with an explicit `-H "x-goog-user-project: <project-id>"` header both bypass this — only the `gcloud billing` CLI subcommand group and bare `gcloud auth print-access-token` REST calls are affected.** If a `gcloud billing ...` command misbehaves like this again, don't chase ADC — use `services enable`/REST-with-header instead, or just verify billing indirectly by enabling a billing-gated API (as done here with `aiplatform.googleapis.com`).
2. **`firebase projects:addfirebase sfws-aicc-workspace-1` (note: typo-prone — this is the *other*, abandoned project's name; the actual command target was always `sfws-aicc-workspace-1`) failed with a generic `403 PERMISSION_DENIED`, "The caller does not have permission,"** even with Owner IAM and reproduced identically from both a local terminal and Google Cloud Shell (ruling out any local-environment cause). Two layered causes, fixed in order:
   - `firebase.googleapis.com` (Firebase Management API) was not enabled on the project at all — `gcloud services list --enabled --filter="name:firebase.googleapis.com"` returned 0 items. Fixed with `gcloud services enable firebase.googleapis.com --project=sfws-aicc-workspace-1`.
   - Even after that, `addFirebase` still 403'd. Root cause: **the Google account had never used the Firebase console before**, and Firebase gates first-time `addFirebase` calls behind having visited console.firebase.google.com and passed its onboarding at least once — the API alone can't complete this, no matter how the CLI is invoked (local or Cloud Shell, same result). Fixed by the user manually visiting `console.firebase.google.com` signed in as `a personal Google account` and adding the project there. **Lesson: a `403 PERMISSION_DENIED` on `addFirebase` with an Owner-role account and the API enabled is very likely this specific first-time-use gate — send the human to the console UI rather than continuing to retry the CLI.**
   - Verified the fix by querying `GET https://firebase.googleapis.com/v1beta1/projects/sfws-aicc-workspace-1` directly with `curl` (with the `x-goog-user-project` header per bug #1 above) rather than via the `firebase-tools` CLI — `npx firebase-tools` invocations are blocked by this environment's permission classifier (flagged as executing a downloaded package), so any future verification of Firebase/npm-CLI-only state needs this direct-REST-call approach instead.

**Environment constraints worth remembering:**
- This session's `Bash` tool cannot complete interactive OAuth (`gcloud auth login`, `firebase login`, `gcloud auth application-default login`) — those must be run by the user directly (terminal, IDE, or Cloud Shell). Read-only checks (`gcloud auth list`, `gcloud config list`, `gcloud projects describe`) and non-interactive mutations (`gcloud services enable`, `gcloud projects create`) work fine once the user has authenticated.
- `gcloud projects add-iam-policy-binding` (granting another account access to the project) was blocked by the permission classifier here — account-permission changes need the user's explicit go-ahead each time, not just a general "proceed with cloud setup."
- `npx firebase-tools <anything>` is blocked by the permission classifier (package execution) — Firebase CLI actions must be run by the user; read-only Firebase state can be checked via direct REST calls instead (see bug #2 above).

**What's NOT done yet:**
- No actual `gcloud run deploy` has been run — there is no app to deploy until Block C (agent layer) exists. `deploy-cloud.sh` (repo root) is written and ready.
- The Cloud Run runtime service account (`the Cloud Run runtime service account`, `roles/editor`) has not been explicitly granted `roles/aiplatform.user` — Editor should already cover Vertex AI calls, but this is unverified until Block C makes a real `litellm.completion(model="vertex_ai/...")` call. If that call fails with a permissions error, check this first.
- Cloud Run's filesystem is ephemeral outside `/tmp`; `deploy-cloud.sh` points `DATABASE_URL` at `/tmp/huluhilir.db`, which means **the seeded demo data does not exist on a fresh Cloud Run instance** — nothing currently runs `seed.py` on cloud startup. This needs an entrypoint change before the cloud path is actually demoable, not just deployable.
- `backend/app/config.py` gained `vertex_project` / `vertex_location` settings (env vars `VERTEX_PROJECT` / `VERTEX_LOCATION`) — Block C's agent code must actually pass these to `litellm.completion()` when the model string starts with `vertex_ai/`; nothing consumes them yet.

---
