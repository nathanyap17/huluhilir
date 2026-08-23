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
- `backend/app/config.py` gained `vertexai_project` / `vertexai_location` settings (env vars `VERTEXAI_PROJECT` / `VERTEXAI_LOCATION` — corrected from an initial `VERTEX_*` naming mistake, see Block C entry) for Block C's agent code to pass through to litellm's Vertex AI integration.

---

## [Block C] Agent layer — RootAgent, coordinators, Advisor, tools_called logging

**Commit:** `Block C: agent layer -- RootAgent, coordinators, Advisor, arbitration`

**Files added:**
- `backend/app/agent/` — `model.py`, `tools.py`, `llm_tools.py`, `error_boundary.py`, `logging_callbacks.py`, `setup_coordinator.py`, `diagnosis_coordinator.py`, `advisor_agent.py`, `root_agent.py`, `runner.py`
- `backend/app/tools/advisor.py` (deterministic `should_diagnose`), `backend/app/tools/knowledge.py` (RAG retrieval), `backend/app/tools/spread.py` gained `load_farm_graph`
- `backend/app/routers/agent.py` — `POST /agent/run`, `GET /farm/{farm_id}/advisor`
- `backend/seed/knowledge_docs.json` (+ `seed_knowledge()` in `seed.py`) — bootstrap 5-chunk advisory RAG corpus
- `backend/tests/test_agent_arbitration.py` — live test against real Ollama, the literal PLAN.md Block C exit criterion

**This block found more real bugs than any other so far — read this section fully before touching agent code.**

### Finding #1: the google-adk skill's own canonical example is wrong for the installed version

The huluhilir:google-adk skill (and general ADK documentation) shows `def compute_spread(req: SpreadRequest) -> SpreadResponse` as the recommended tool-authoring pattern — a single Pydantic model as the whole parameter. **This does not work in the installed `google-adk==2.7.1`.**

Root cause, confirmed by reading `google/adk/tools/function_tool.py` directly in the venv (not just the adk-python reference clone — both matched, so this isn't a version-skew artifact): the `JSON_SCHEMA_FOR_FUNC_DECL` experimental feature (on by default here) flattens a lone scalar-Pydantic-model parameter's fields into the top-level tool schema shown to the LLM. But `FunctionTool._prepare_invocation_args` filters incoming call args down to `{k: v for k, v in args_to_call.items() if k in valid_params}` — and `valid_params` for `def f(req: SomeModel)` is just `{"req"}`. Since the LLM calls with flattened top-level keys (e.g. `{"query": ..., "top_k": 5}`), none of them match `"req"`, the filtered dict is empty, and every call fails with `"mandatory input parameters are not present: req"`.

**`list[SomeModel]` parameters are NOT affected** — `_preprocess_args` has explicit reconstruction logic for that shape (`is_list_of_basemodel(...)` check), and it works correctly when the model calls with a top-level list-of-objects.

**Fix applied everywhere:** every ADK-facing tool function takes flattened scalar/list parameters, never a bare Pydantic model as the sole parameter. Internally, the flat args are reassembled into the existing `app/schemas/*` request models before calling into `app/tools/*`'s existing implementation (which is untouched — this only affects the ADK-facing wrapper layer in `app/agent/tools.py`, `app/agent/llm_tools.py`, `app/agent/advisor_agent.py`). This cost three separate debugging passes (`retrieve_knowledge`, `explain_why`/`draft_alert`, and the original `get_treatment`/`find_spray_window` closures in Block B's initial agent draft all hit it independently) before the pattern was generalized.

**If a future ADK upgrade changes this behavior, `app/agent/tools.py`'s module docstring has the full citation trail** — check whether `list[SomeModel]`-only reconstruction is still the case before reverting to single-model parameters.

### Finding #2: LoopAgent is deprecated in this ADK version, but is still the right tool here

`google/adk/agents/loop_agent.py` carries `@deprecated('LoopAgent is deprecated in favor of Workflow and will be removed in a future version. Workflow cannot yet be used as an LlmAgent sub-agent.')`. PLAN.md/PROJECT_SPEC.md explicitly specify `LoopAgent` with `max_iterations` for `SetupCoordinator`/`DiagnosisCoordinator` — a stated proposal commitment, not incidental code. Decision: **kept LoopAgent.** It still works (deprecated ≠ removed), and the suggested replacement (`Workflow`) explicitly cannot be used as an `LlmAgent` sub-agent yet, so there is no working alternative today. Re-evaluate only if a future `google-adk` release actually removes `LoopAgent`.

### Finding #3: AgentTool vs `sub_agents=[..., mode='single_turn']`

`AgentTool`'s own docstring says direct usage is "discouraged," preferring `sub_agents=[...]` with `mode='single_turn'` set on the sub-agent. **This guidance doesn't apply to `SetupCoordinator`/`DiagnosisCoordinator`**: `mode` is a field on `LlmAgent` (`agents/llm_agent.py:365`), not on `BaseAgent` — a `LoopAgent` has no `mode` to set. `AgentTool` is the only mechanism that lets `RootAgent` call a bounded `LoopAgent` as a step and keep control afterward (call-and-return), which is exactly the "router + arbitrator" semantics PROJECT_SPEC.md §3 L4 describes — the alternative (`sub_agents` without `AgentTool`) is a *delegate-and-transfer-control* model, semantically wrong here. Kept `AgentTool` for all three (`SetupCoordinator`, `DiagnosisCoordinator`, `Advisor`) for consistency, even though `Advisor` technically *is* an `LlmAgent` and could have used `mode='single_turn'` instead — did not special-case it given the very small benefit.

### Finding #4: real LLM tool-calling failures under multi-step orchestration (qwen2.5:14b via Ollama)

Live-testing the RootAgent against the actual demo scenario (`docs/PROJECT_SPEC.md`'s "L1: treat now · L3: 24h rain-fast · Weather: 46mm tomorrow · L2: downslope risk in 4 days" arbitration moment) surfaced real reliability gaps EXP-5 didn't catch, because EXP-5 only tested "can it emit one valid tool call," not "can it correctly sequence and synthesize several dependent ones":

1. **Parallel-before-sequential tool calls with placeholder values.** Told to "check the weather, then compute spread," the model sometimes emits `get_weather` and `compute_spread` in the *same* turn, before it has seen `get_weather`'s result — filling the still-unknown `rainfall_7d_mm`/`forecast_7d_mm` with an obviously-fake sentinel (`-9999`, or the literal string `'__DYNAMIC__'`) rather than waiting. `'__DYNAMIC__'` also appeared as a placeholder for `treatment_id` and `rainfast_hours` in `find_spray_window` calls on different runs. This is a genuine model/framework limitation, not a one-off — it recurred across multiple independent live runs.
2. **An unhandled exception from one bad tool call killed the entire agent turn.** `-9999` passed pydantic's original (missing) bounds check on `SpreadResultItem.risk` and blew up downstream with a validation error that propagated all the way through `asyncio.gather` in ADK's `functions.py`, crashing the whole run — no chance for the model to see the error and retry.
3. **The model sometimes ignored a tool's own computed signal in its final synthesis.** One run: `find_spray_window` correctly computed `rain_free=False` for four upcoming days, yet the model's final JSON gave five identical "treat now" recommendations with `defer_cause: null` and a fabricated, contextually nonsensical date (`"2023-10-06T15:00:00Z"`) — it had the right tool result in context and didn't use it.

**Fixes applied (defense in depth, not a single patch):**
- `app/agent/error_boundary.py`: `tool_error_boundary` decorator wraps every ADK-facing tool function (sync and async) so any exception becomes a `{"error": "..."}` return instead of an unhandled exception — the model sees the error and can retry. Uses `functools.wraps` so `inspect.signature()` (which ADK's schema builder calls on `tool.func`) still resolves to the real signature/docstring.
- `app/schemas/spread.py`: added `ge=0` to `ComputeSpreadRequest.rainfall_7d_mm`/`forecast_7d_mm` (they had no bound before) — catches a `-9999`-style placeholder at the actual input boundary with a clear, retryable validation message, instead of letting it silently compute a misleading result further downstream.
- `app/tools/spread.py`'s `_rain_factor` also clamps to `max(0.0, ...)` as defense-in-depth — belt-and-suspenders in case a negative value ever reaches it through a path the schema doesn't guard.
- `ROOT_INSTRUCTION` (`app/agent/root_agent.py`) now explicitly says: never call a tool in the same turn as another tool it depends on; never use a placeholder like `-9999`/`__DYNAMIC__`; the farm_id comes from the user's message, never guess it or reuse a block_id as one. This measurably reduced (but did not eliminate) the parallel-call/placeholder behavior across repeated live runs.
- **`app/agent/runner.py`'s `_reconcile_spray_deferrals()` — a deterministic safety net over the LLM's own arbitration**, extending this project's existing "loop termination is deterministic Python, never LLM judgement" principle (google-adk skill §2) to the rainfast-defer decision specifically. After parsing the model's JSON, it finds the actual last `find_spray_window` tool call/result (kept via a `_raw_result` field on each logged call, stripped before `tools_called` is persisted so the DB shape stays exactly `{name, args, latency_ms, result_summary}` per `docs/DATA_MODEL.md` §15) and: overrides `defer_cause` on every rainfast-gated recommendation (`spray`/`drench` with a `treatment_id`) to match the tool's real computed value; overrides `recommended_at` to the tool's actual `recommended_window.window_start` whenever one exists (this is what fixed the fabricated-date failure); injects a `clear_drain` recommendation at `sequence=1` (bumping others) if a defer is needed and the model didn't already produce one. This is *reconciliation*, not replacement — the model still does the actual reasoning and produces the recommendation set; the safety net only corrects the two fields that were empirically shown to be unreliable.

**Residual known gap:** `find_spray_window_impl`'s own `defer_cause` only fires when *no* viable window exists anywhere in the given forecast (`viable == []`) — not for the more common "a window exists but only a few days out" case. In the passing test run, the model (correctly, on its own) chose `defer_cause: null` with a delayed `recommended_at` plus separate `clear_drain` recommendations for the alerted blocks — which is functionally right but doesn't literally set `defer_cause="rainfast"` per `docs/DATA_MODEL.md`'s stated intent that `deferred_from`+`defer_cause` are "the arbitration record." If a demo run needs `defer_cause` populated for a delayed-but-not-fully-blocked case specifically, `find_spray_window_impl` needs a second tier of "found a window, but not an immediate one" signal — not implemented; noted here rather than guessed at under time pressure.

### Other bugs fixed in this block

- **`app/tools/knowledge.py`**: same `use_enum_values=True` class of bug as three Block B fixes — `query.namespaces` items are already plain strings (not `KnowledgeNamespace` enum instances) because `ORMModel` sets `use_enum_values=True`; calling `.value` on them raised `AttributeError`. **This is now the fourth time this exact mistake has appeared independently across the codebase — grep for `.value` on any field coming from an `ORMModel`-based schema before assuming it's an enum instance.**
- **`VERTEXAI_PROJECT`/`VERTEXAI_LOCATION` naming**: the Cloud Gate entry above originally used `VERTEX_PROJECT`/`VERTEX_LOCATION`. Caught while writing `app/agent/model.py` and cross-referencing `LiteLlm`'s own docstring (`vertex_ai/claude-3-7-sonnet@20250219` example explicitly sets `os.environ["VERTEXAI_PROJECT"]`) — litellm reads these directly from the environment with the `VERTEXAI_*` spelling. Fixed in `config.py`, `deploy-cloud.sh`, `.env.example`. **This would have silently failed to authenticate on the actual Cloud Run deploy with zero error until that exact code path ran** — exactly the kind of naming mismatch worth double-checking against the library's own source/docstring rather than assuming a name pattern.

**Verified (how):**
- `pytest tests/` (16 tests, non-live) all pass with the agent module imported.
- Live smoke test of the `Advisor` sub-agent alone (RAG retrieval + grounded Bahasa Malaysia answer citing the seeded 24% drainage figure) — confirmed real retrieval + real synthesis, not just plumbing.
- Live smoke test of the full `RootAgent` trajectory against the actual demo scenario, run multiple times to observe variance — one run crashed (pre-error-boundary), one run "passed" with a wrong/fabricated arbitration (pre-reconciliation), one run passed on genuine merits post-fix (`tools_called` populated with all 4 non-LLM tools, treatment_id from the real rules table, `clear_drain` correctly sequenced ahead of the deferred `drench`).
- `tests/test_agent_arbitration.py` — the literal PLAN.md Block C exit criterion, live against real Ollama (qwen2.5:14b), passing as of this commit. **Deliberately not mocked**, and deliberately asserts structural guarantees (tools_called populated, no invented treatment_id, a defer/drainage response given imminent rain) rather than exact wording — an LLM-driven test asserting exact strings would be dishonest given the demonstrated variance above. Expect this specific test to occasionally need a re-run; that is a property of the model, not a flaky test in the usual sense — see Finding #4.

**Known gaps / placeholders:**
- `SetupCoordinator`/`DiagnosisCoordinator` are structurally correct and bounded (`max_iterations=25`/`30`) but have no live phone-side capture loop behind them yet (Block D) — they can only ever observe "already complete" or run to the iteration cap against whatever a test seeds. `demo_farm.json`'s seed now sets `farms.setup_completed_at` so the demo farm represents an already-onboarded farm and `SetupCoordinator` short-circuits immediately rather than looping, per PLAN.md Block F's "known-good state" intent.
- No `/observations` upload endpoint exists yet — `diagnose_leaf` still takes a local filesystem path; the real phone→storage→URI pipeline is Block D.
- `find_spray_window`'s `defer_cause` semantics gap (above) is unresolved.
- Cloud Run's Vertex AI IAM permission (Block C's `Cloud Gate` entry, item 2) is still unverified against a real `vertex_ai/gemini-2.0-flash` call — only tested against local Ollama so far.

---

## [Block D] Flutter app — setup flow, walk loop, dashboard, terrain canvas

**Commits:** `Block D prerequisite: the API surface the Flutter app actually consumes`, `Block D: Flutter app -- setup flow, walk loop, dashboard, terrain canvas`

### The plan gap this block exposed

PLAN.md Block D says *"Generate Dart models from `/openapi.json`"* and its exit is *"full setup → diagnosis → recommendation on a real phone"* — but **no block in PLAN.md ever allocated the CRUD/flow endpoints the app consumes.** Blocks A–C built the tools, the agent, and a health check; there was no way to create a user, capture a block, resolve elevation, upload a photo, or fetch a dashboard. Roughly 900 lines of backend had to land before a single screen could work. If re-planning a build like this, allocate the app-facing API surface explicitly — it is not implied by "FastAPI skeleton" in Block A.

**Files added (backend):** `routers/setup.py`, `routers/media.py`, `routers/diagnosis.py`, `routers/dashboard.py`, `tools/graph.py`, `tests/test_setup_flow.py`
**Files added (app):** `flutter_app/lib/{config,models,api_client,outbox,providers,terrain_canvas,main}.dart`, `lib/screens/{registration,walk,elevation,dashboard,diagnosis}_screen.dart`, `test/widget_test.dart`, `android/app/src/main/res/xml/network_security_config.xml`

### Key decisions

- **`tools/graph.py` lifted out of `seed.py`.** Elevation ranking and flow-edge derivation existed only inside the seed script; real farms need it at runtime. Ranking uses an ordering-score (count of "is above") rather than a topological sort, because a real farmer's pairwise answers may be **intransitive** (a>b, b>c, c>a is entirely possible) — a strict sort would raise on that, scoring degrades gracefully. Ties break by baro_rel then block_id so `elevation_rank` stays unique per farm and deterministic.
- **Dart models hand-written, not generated.** openapi-generator/build_runner setup costs more than it saves at this model count; `/openapi.json` remains the source of truth and the backend wins on any disagreement.
- **Terrain canvas lays out by `elevation_rank`, not geographic position.** It is a water-flow diagram, not a map. Rendering real coordinates would imply we hold land boundaries, which we explicitly never record (huluhilir-rules §4). Rank ordering is the only spatial claim the system actually makes.
- **`uses-feature barometer required="false"`** — marking it required would exclude exactly the low-cost phones this is built for, and MINIMAL tier loses no functionality per PROJECT_SPEC §4.

### Bugs found and fixed

1. **Session was in-memory only — closing the app lost the farm entirely.** Found by force-stopping the app during emulator testing. This also made PROJECT_SPEC §7's *"on app open mid-cycle, land on the dashboard with a resume prompt"* impossible to honour, since there was no session to resume into. Fixed with `shared_preferences` persisting **only the two IDs**, plus new `GET /users/{id}` and `GET /farms/{id}` endpoints so the farm is re-fetched from the server on launch — `setup_completed_at` is server truth, never a stale local copy. `SessionState.restoring` gates a splash so a returning farmer never sees the registration form flash first. Routing now also handles *registered-but-setup-incomplete* → resume the walk, rather than showing an empty dashboard.
2. **`permission_handler` broke the Android build** — its own `build.gradle.kts` uses `compilerOptions {}`, which needs a newer Kotlin Gradle plugin than this project has (`Unresolved reference: compilerOptions`). It turned out to be **completely unused**: geolocator, record, and image_picker each handle their own permissions. Removed rather than fighting the toolchain. If a future need for it arises, the Kotlin plugin must be upgraded first.
3. **Android blocks cleartext HTTP by default (API 28+)** — the LOCAL target is plain HTTP to a laptop, so without a `networkSecurityConfig` the app fails with a generic socket error. Caught before it could burn demo time on stage. **First attempt at the fix was wrong and worth recording:** I scoped it with `<domain>192.168.1.0</domain>`-style entries, but Android's `<domain>` matches *literal hostnames, not CIDR ranges* — that would only ever match the exact address `192.168.1.0`, never the laptop at `192.168.1.57`. Since the booth LAN IP isn't known ahead of time there's no way to enumerate it, so `base-config cleartextTrafficPermitted="true"` is used, with the reasoning documented in the file. Acceptable because the CLOUD build uses HTTPS regardless and the LOCAL build is booth-only.
4. **`walk_screen`'s `_walkSessionId` was assigned but never used** — flagged by `flutter analyze` as an unused field. It meant **walk samples were never actually being sent to the server**: the walk loop looked like it worked but persisted nothing. Fixed with a 10-second periodic flush plus a final flush on finish, a separate `_unflushed` buffer retaining the full trace (the rolling `_recent` window is only ±5 s for the centroid), and an offline indicator. Verified: 7 then 12 then 14 samples landing in `walk_samples`.

### Verified (how)

- **Gradle cache warmed** in a throwaway project per WORKSPACE_SETUP.md — 186.8 s first build, then **66.7 s** for subsequent builds. This was flagged as "the single biggest avoidable risk" (30–60 min); it is now retired. `flutter_app` builds in ~1 min.
- **Real end-to-end on the `Pixel_6_API_34` emulator**, not mocked: registration → farm creation → walk session → GPS sampling → flush → block capture sheet → session restore → dashboard.
- **Silent tier detection confirmed live**: emulator reports no barometer → farm created as `minimal` → UI honestly states *"Semua fungsi tetap berjalan"*.
- **Dashboard screenshot verified** showing rain pulse, Advisor verdict, and the terrain canvas with 4 ranked blocks and 6 downhill arrows — **with zero photographs ever taken**, which is huluhilir-rules §6 verified visually rather than only in a test.
- 22 backend tests + 5 Flutter tests passing. `flutter analyze`: 0 errors, 0 warnings.

### Known gaps — do NOT claim these work

- **No physical phone was ever connected.** Everything above is emulator-verified. Still blocked and untested on real hardware: EXP-3 (Ollama over hotspot), EXP-4 (barometer + drift → the entire OPTIMISED tier), EXP-6 (GPS under canopy), EXP-11 (scrcpy). **The OPTIMISED elevation tier has never run against a real barometer** — only the MINIMAL path is demonstrated.
- **Camera capture was not verified through the UI.** Driving the emulator's fake-camera app via blind `adb input tap` coordinates proved fragile and was abandoned as low-value; the capture sheet correctly gates SIMPAN BLOK on a photo existing, and the upload/classify path is verified server-side, but the ImagePicker→upload→observation round trip has not been exercised end-to-end from the UI.
- **`outbox.dart` is written but not wired in.** `queueObservation`/`queueWalkSample` are never called — the walk loop currently buffers in memory and drops samples if the app is killed mid-walk. The offline story is therefore weaker than PLAN.md's Block D "Outbox" row implies. Wiring it is a genuine remaining task, not a polish item.
- **"Tanya" (RAG chat) has a FAB entry that no-ops.** The Advisor agent exists and works server-side (Block C), but there is no chat screen.
- **No speech/audio playback.** Every user-facing string carries a `speech_template_id` and the dashboard has a speaker affordance, but it currently shows a snackbar — audio is Block E.
- **Block detail sheet is minimal** — photo, voice playback, timeline with rainfall overlay, diagnosis history, and treatment log (PROJECT_SPEC §7) are not built; the sheet shows label, state, rank, drainage only.
- **No signed release APK / keystore** (PLAN.md 0.15, Block F).

---

## [Block D+] Visual redesign — cream/olive/terracotta theme

**Commit:** `Redesign dashboard: cream/olive/terracotta theme, typography, terrain reskin`

User supplied a detailed design spec (colours, type pairing, card-by-card layout, FAB column) for the dashboard screen. Implemented faithfully with one deliberate, disclosed scope cut.

**Files added:** `lib/theme.dart` (colours, radii, `AppText.serif`/`AppText.sans`/`AppText.eyebrow`, `buildAppTheme()`, `softShadow()`)
**Files rewritten:** `lib/main.dart` (theme wiring), `lib/screens/dashboard_screen.dart` (all four cards + header + FAB column), `lib/terrain_canvas.dart` (recolour, legend overlay, tap-to-open profile card)

**Scope decision, stated up front rather than discovered late:** the spec calls for a literal 3D isometric terrain scene (terraced steps, low-poly trees on posts, blurred legend/profile overlays). Built everything **except** the literal 3D geometry — a 3D pipeline, asset modelling, and lighting is a materially larger, riskier build than the rest of this app, and the part that's actually load-bearing (the rank/flow diagram, which is what `compute_spread`'s output means) already existed and was correct. Instead: the existing 2D rank/flow diagram (from Block D) is re-skinned with a stylised terraced-gradient backdrop in the new palette, and the **legend overlay and tap-to-open profile overlay are both built exactly as specified** (blurred `BackdropFilter` box, state-coloured header card, close button) — those don't depend on 3D at all.

**Typography:** `google_fonts` (Playfair Display serif for headers/numbers, Inter sans for labels/body) rather than bundling font files. This needs network on first font load, cached after — judged acceptable since the app already requires connectivity for the backend and agent, so it isn't introducing a new offline-breaking dependency.

**One real bug found and fixed during on-device verification:** the terrain canvas's chip-layout function fanned the highest-ranked (rank #1) block toward the top-**left**, which is exactly where the new legend overlay sits — the block's label was rendered underneath and partially obscured (`"lok Atas"` instead of `"Blok Atas"` in the first screenshot). This wasn't caught by `flutter analyze` or the widget tests (no test asserts screen-space non-overlap) — only caught by actually looking at a device screenshot. Fixed by pinning the topmost node to the right half of the canvas (`x = 0.68`) rather than the alternating-fan formula used for interior ranks; the legend always occupies the top-left corner regardless of block count, so this is a structural fix, not a one-off coordinate tweak.

**Verified (how):** rebuilt and reinstalled on the `Pixel_6_API_34` emulator (build time now 17–22 s thanks to the warmed Gradle cache from Block D), relaunched against the existing session (proving session-restore still works post-redesign), screenshotted the full dashboard scroll, confirmed the legend/chip overlap bug via screenshot, fixed it, rebuilt, and reconfirmed via a second screenshot that all four block labels are now fully legible. Tap-to-open profile overlay verified live (correct state-colour gradient header, close button dismisses). `flutter analyze`: 0 new errors (5 pre-existing `info`-level items, unchanged). 5 Flutter tests + 22 backend tests still passing.

**Known gaps:**
- Only the dashboard screen received the full redesign. Registration/walk/elevation/diagnosis screens inherit the new global `ThemeData` (buttons, inputs, app bars all follow the new palette automatically) but were not individually re-laid-out to the same card-by-card detail.
- The "Tanya" chat FAB is still a no-op snackbar, unchanged from Block D.
- Reset was moved from "long-press the chat FAB" (my first instinct) to "long-press the header's settings icon" — overloading the chat button's long-press with an unrelated destructive action would have been confusing UX; not explicitly covered by the design spec's 2-FAB layout, so this is a judgment call worth revisiting if the design is reviewed further.

---

## [Block D+] 3D terrain viability spike — WebView + Three.js, verified on-device

User supplied a detailed React Three Fiber spec for the terrain visual (procedural IDW terrain, terracing, flat-shaded low-poly vine clusters, dashed downhill flow lines, OrbitControls, click-to-select) and asked directly whether it's achievable in Flutter, specifically on-device rather than in theory. Flutter has no built-in 3D engine, so this was a genuine three-way architecture fork, not a "just build it": (A) embed real Three.js in a WebView, (B) fake it with 2D `CustomPainter` isometric projection, (C) an experimental/unmaintained Dart-native 3D engine (`three_dart`, `flutter_scene`). Presented the tradeoffs and the user picked (A), then asked "will this work on phone?" — answered empirically rather than by assertion, since this codebase's whole culture is "verified how," not "should work."

**Result: yes, confirmed working, with two real bugs found and fixed along the way that would otherwise have surfaced as an inexplicable blank screen at demo time.**

**Files added:** `flutter_app/assets/terrain/smoke_test.html`, `flutter_app/assets/terrain/vendor/{three.min.js,OrbitControls.js}` (Three.js r128, vendored locally — not fetched from a CDN at runtime, so this works fully offline once installed), `flutter_app/lib/terrain_3d_smoke_test.dart` (kept as reference scaffold for the real implementation; not routed from `main.dart`)

### Bug 1: ES modules cannot load over `file://` — a Chromium restriction, not a WebView quirk

First attempt used `three.module.js` (the current recommended Three.js distribution -- the classic global-script UMD build is deprecated as of r150+) loaded via `<script type="module">` with an import map. This produced, on-device: `Access to script at 'file:///android_asset/.../three.module.js' from origin 'null' has been blocked by CORS policy`. `webview_flutter`'s `loadFlutterAsset()` serves bundled assets at `file:///android_asset/flutter_assets/...`, and Chromium's ES module loader treats `file://` as an opaque/null origin, which fails the same-origin check module imports require -- regardless of the fact that the importing page and the imported script are in the exact same local directory. This is standard Chromium behaviour (reproducible in desktop Chrome too, not something specific to Android WebView).

Plain `<script>` tags (no `type="module"`) have never had this restriction -- only the ES module loader path triggers the CORS check. **Fix:** dropped ES modules; pinned to Three.js r128, the last release with a full classic UMD build (`build/three.min.js`, attaches `window.THREE`) and a matching non-module `OrbitControls.js` (`examples/js/controls/OrbitControls.js`, attaches `THREE.OrbitControls`). This is a real constraint on the eventual full implementation too: **any Three.js addon used (Line2/LineDashedMaterial for the flow vectors, Text geometry for labels, etc.) must be sourced from the classic `examples/js/` tree of a pre-r150 release, not the modern `examples/jsm/` ES-module tree** -- mixing module and non-module Three.js code will not work here.

### Bug 2: Flutter directory asset declarations are not recursive

After fixing bug 1, the page still failed with `THREE is not defined` and logcat showed `AndroidProtocolHandler: Unable to open asset URL: .../vendor/three.min.js`. `pubspec.yaml` declared `assets/terrain/` as a directory asset, which Flutter's asset bundler includes shallowly -- files directly inside `assets/terrain/` (i.e. `smoke_test.html`) were bundled, but the nested `vendor/` subfolder's contents were silently dropped. Confirmed by inspecting the built APK directly (`unzip -l ... | grep terrain`) before and after the fix -- the APK genuinely didn't contain the vendor files, this wasn't a caching artifact. **Fix:** added `assets/terrain/vendor/` as its own explicit line in `pubspec.yaml`. **Any future nested asset folder needs the same treatment -- this will bite again silently if forgotten.**

### Verified (how)

- Both bugs were diagnosed via `adb logcat` reading actual Chromium console/protocol-handler output, not guessed at -- `chromium: [INFO:CONSOLE(0)]` lines carry the browser's own JS console messages (including `console.log` calls added for debugging), and `AndroidProtocolHandler` lines show asset-resolution failures directly.
- Final on-device confirmation: screenshotted the app twice, 3 seconds apart, on the `Pixel_6_API_34` emulator. The camera angle visibly changed between the two screenshots with no user input, confirming `OrbitControls.autoRotate` is genuinely animating a live WebGL scene (not a static frame or a hung page). Flat shading is visible (distinct per-face brightness on both the cube and the dodecahedron under the directional light). The JS-to-Flutter `JavaScriptChannel` bridge round-trip was also confirmed -- the Flutter app's own title bar updated to reflect the message posted from inside the WebView's JS context.
- `flutter analyze`: 0 new issues. 5 Flutter tests still passing (this spike didn't touch the dashboard/terrain-2D code paths).

### What this does NOT prove yet -- the real terrain implementation is still unbuilt

This spike proves the *pipeline* works: bundled classic-script Three.js renders real WebGL with lighting and animates via OrbitControls inside `webview_flutter`, and JS can talk back to Flutter. It does **not** yet implement any of the spec's actual content:
- IDW height interpolation over farm block positions, island tapering, height quantization/terracing
- Vertex/face colouring by elevation tier
- Per-block vine-cluster geometry (cylinder posts + overlapping dodecahedron foliage) driven by real `BlockModel` state
- Dashed downhill flow lines driven by real `FlowEdgeModel` data (needs `LineDashedMaterial` from the classic, non-module Three.js examples tree per Bug 1's constraint)
- Click-to-select raycasting against the vine clusters, wired back to the existing Flutter `_BlockProfile` overlay via the JS bridge
- Camera polar-angle/zoom clamping

Each of those is a real, separate piece of engineering, not a natural extension of the spike -- estimate this as the largest single remaining task in the app if pursued.

---

## [Block D+] Full 3D terrain implementation — real IDW terrain, real data, click-to-select

Following the viability spike above, built the actual terrain the spec describes and wired it into the dashboard, replacing `TerrainCanvas` (the 2D flow diagram) as the primary view. **All four sections of the spec are implemented and verified working on-device against the real "Kebun Saya" farm's data** (4 blocks, 6 flow edges from the real backend, not synthetic test data) -- this is not a mockup.

**Files added/changed:** `flutter_app/assets/terrain/terrain.html` (the real scene, ~400 lines), `flutter_app/lib/terrain_3d_view.dart` (the Flutter↔WebView bridge), `flutter_app/lib/providers.dart` (`terrainInteractingProvider`), `flutter_app/lib/screens/dashboard_screen.dart` (swapped `TerrainCanvas` → `Terrain3DView`, wired `ListView.physics`)

### What's implemented

- **IDW terrain generation**: a 100×100-segment plane (150 in the original spec; reduced for mobile GPUs, visually indistinguishable), height at every vertex computed by inverse-distance weighting from each block's height sample, island-tapered to zero past a radius so it reads as a contained landform, and quantized into discrete terraces (`Math.floor(h/STEP)*STEP`) for the topographic-model look. Flat shading via `toNonIndexed()` + `computeVertexNormals()`, vertex-coloured by a 7-stop elevation ramp (base/water → mid earth/sand → high vegetation), matching the spec's palette.
- **Vine pillars**: cylinder post + 3 overlapping low-poly dodecahedrons per block, coloured by the block's REAL `current_state` (protected/alerted/harmed/overrun → olive/yellow/terracotta/dark-red, the same mapping `TerrainCanvas` already used), a semi-transparent base decal, and a canvas-texture sprite label (`"{label} · #{rank}"`) that always faces the camera.
- **Downhill flow lines**: dashed `THREE.Line` (`LineDashedMaterial`, core Three.js, no addon needed) between each pair of blocks with a real `flow_edge` from the backend -- **not re-derived client-side** by a simplified "nearest lower node" heuristic like the original spec suggested. This was a deliberate deviation: the backend's `flow_weight`/`barrier` already encode the actual computed downhill relationship (`app/tools/graph.py`), and re-deriving a second, simpler version in JS would create two sources of truth that could disagree.
- **Camera**: `OrbitControls` with `autoRotate` (0.5 speed), damping, `maxPolarAngle`/`minPolarAngle` clamps (can't go under the terrain or fully overhead), and distance clamps, per spec §6.
- **Click-to-select**: raycasting against each pillar's foliage (plus an invisible larger hit-sphere added after on-device testing showed the visible geometry alone was too small a target for a real fingertip), which stops `autoRotate`, draws a dark selection ring at the block's base, and posts the `block_id` back to Flutter via `JavaScriptChannel`. Flutter renders the **existing native `_BlockProfile` widget** (built in the earlier dashboard redesign) as an overlay -- deliberately not a second HTML/CSS profile UI inside the WebView, so there's one implementation of that card, in the app's actual theme/fonts, not two.

### Real bugs found and fixed via on-device testing (four more, on top of the viability spike's two)

**Bug 3 — non-monotonic node layout produced a spurious second low patch inside the high terrain ring.** First layout fanned nodes across a ~100° arc at growing radius (an attempt at organic scatter). This meant the geometric origin wasn't reliably closest to the highest-ranked node -- IDW blending from an angularly-closer-but-lower-ranked node could out-weigh the intended peak, producing a pale dip where a green peak was expected. Screenshotted and diagnosed by testing with known synthetic data (4 nodes, exact ranks) via the local-HTTP-server + browser-preview loop (fast iteration, no APK rebuild needed for this part) before ever touching the emulator. **Fixed** by placing nodes along a single line radiating from centre (small constant-magnitude lateral jitter only for visual separation between pillars, not radius-scaled) so radius is strictly monotonic in `elevation_rank` and the height field can't develop a spurious interior dip.

**Bug 4 — the dashboard's `ListView` stole every touch from the embedded WebView; taps scrolled the page instead of reaching Three.js.** First fix attempt: `WebViewWidget(gestureRecognizers: {Factory(() => EagerGestureRecognizer())})`, the textbook Flutter answer for "let this platform view win the gesture arena against an ancestor Scrollable." **This did not work reliably** -- confirmed by instrumenting the WebView's own `pointerdown`/`pointerup` handlers to print coordinates on-screen: a stationary tap produced `UP` coordinates ~267px away from the matching `DOWN`, which is not real finger movement -- it's the WebView's own on-screen position shifting mid-touch because the ListView was still scrolling underneath it, which Chromium then reports as a huge *relative* pointer displacement. **Real fix**: bypassed the native gesture-arena/PlatformView ambiguity entirely. Added `terrainInteractingProvider` (a Riverpod `StateProvider<bool>`), toggled by a plain Flutter `Listener` wrapping the `WebViewWidget` (`onPointerDown` → true, `onPointerUp`/`onPointerCancel` → false), and the dashboard's `ListView.physics` directly reads it (`NeverScrollableScrollPhysics` while true). This is deterministic Flutter-side state, not a hope that the native touch dispatch resolves the way a given webview_flutter/Android WebView version combination happens to resolve it. **If any other embedded interactive widget is ever added inside a scrollable in this app, this is the pattern to reach for, not `gestureRecognizers` alone.**

**Bug 5 — visible pillar geometry was too small a raycast target for a real fingertip.** Not caught until manually tapping the emulator screen (as opposed to earlier tests that called `window.renderTerrain` and inspected state via console/status text without simulating a real touch). A tap that visually looked "on" the tree model reported `raycast hits=0`. **Fixed** with an invisible, larger `SphereGeometry` hit target added to each pillar group (rendered with `MeshBasicMaterial({visible: false})`, which Three.js's raycaster still intersects -- only `Object3D.visible` on the mesh itself, not material visibility, is checked by the raycaster).

**Bug 6 (minor, cosmetic, not fixed)**: the terrain's true colour peak (deep green, `t=1.0`) is real and does get computed correctly very close to the highest-ranked node, but is naturally hidden directly underneath that node's own pillar/decal geometry from every camera angle, since the peak-coloured area is small and the pillar sits exactly on top of it. Tried increasing `IDW_POWER` from 2 to 3 (sharper per-node falloff) which improved overall colour separation between rings but didn't surface the hidden peak patch, since the geometry occlusion is the actual cause, not the colour math. Not worth chasing further: the vine pillar's own state colour (the diagnostically important signal) is unaffected and renders correctly; the terrain colour ramp is atmospheric.

### Verified (how)

- Fast iteration loop for terrain-generation logic (Bug 3, camera framing, IDW tuning): a local Python `http.server` serving `assets/terrain/` directly, driven via the Claude Browser preview tooling with `window.renderTerrain(...)` called with synthetic JSON matching the real payload shape. This caught and let me fix Bug 3 in a few seconds per iteration, instead of a ~20-30s full APK rebuild+install+launch cycle -- **use this loop for any future terrain.html changes that don't depend on the actual WebView/Flutter bridge.**
- Full on-device verification on `Pixel_6_API_34` against the real "Kebun Saya" farm (not synthetic data): confirmed the terrain renders with the actual 4 blocks and 6 backend-computed flow edges (`rendered 4 blocks, 6 edges` in the on-screen status), confirmed `OrbitControls.autoRotate` genuinely animates (camera angle changed across screenshots with zero input), confirmed click-to-select opens the real native `_BlockProfile` overlay with correct state colour and real block data (drainage, vine count), confirmed the overlay's close button and that scrolling resumes correctly afterward, and confirmed the whole regression (auto-rotate → tap → select → still no scroll-hijack) holds after all fixes were applied together, not just individually.
- `flutter analyze`: 0 new issues (same 5 pre-existing `info`-level items). 5 Flutter tests + 22 backend tests still passing -- this work didn't touch either test suite's subject matter, and both were re-run to confirm no regression.

### Known gaps

- `TerrainCanvas` (the 2D flow diagram) is kept in the codebase, unused by the dashboard now, as an explicit fallback -- per PLAN.md's own philosophy of not deleting a working safety net. If the 3D view has any issue on a real (non-emulator) phone on demo day, swapping `Terrain3DView` back to `TerrainCanvas` in `dashboard_screen.dart`'s `_TerrainCard` is a one-line change.
- `_ProfileCard` in `terrain_3d_view.dart` duplicates `terrain_canvas.dart`'s `_ProfileOverlay` (same Positioned/shadow/close-button presentation). Accepted minor duplication under time pressure rather than risk a refactor of working code; a shared widget would be a clean follow-up if time allows.
- Never tested on a real physical phone -- only the `Pixel_6_API_34` emulator. WebGL/Chromium behavior on real device GPUs and real WebView versions (which vary far more across actual Android phones than across emulator images) is unverified. Given how much on-device-only debugging this feature already needed (none of bugs 3-6 were visible from code review or `flutter analyze` alone), **budget real testing time for this specific feature on a physical phone before demo day, not just a final smoke check.**
- Selection/hit-testing was only verified with 4 blocks at a fairly loose spread; a farm with many more, more tightly-packed blocks has not been tested and could stress both the IDW layout's jitter-based separation and raycast hit-target overlap.

---
