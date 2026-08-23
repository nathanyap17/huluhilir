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

## [Cloud Deploy] Cloud Run + Vertex AI — classifier bundling, auto-seed, wrong model name

Followed the explicit sequencing from earlier in the day (Block D → local test → cloud gate) and the account a personal Google account / project `sfws-aicc-workspace-1` established after the original UNIMAS-org-policy and Firebase-403 blockers (see earlier entries). User preferred Vertex AI over the Gemini API directly, since Cloud Run's own service account can authenticate to Vertex with no API key to manage. Before running `deploy-cloud.sh` as it existed, re-derived it against PLAN.md/CLAUDE.md and found three gaps that would have made the deploy silently broken or incomplete.

### Gap 1 — the deployed image would not contain the CNN model

`backend/Dockerfile` (used by `docker-compose.yml` for LOCAL) works because `docker-compose.yml` bind-mounts `./classifier:/classifier:ro` at *run* time — the image itself never contains the model. `deploy-cloud.sh` ran `gcloud run deploy --source ./backend`, i.e. a build context scoped to `backend/`, which cannot see the sibling `classifier/` directory at all. Deployed as-is, every diagnosis call would have failed at runtime with a missing-file error, not caught by anything short of actually invoking `/diagnosis` against the live service.

**Fix:** added a new repo-root `Dockerfile` (kept separate from `backend/Dockerfile` rather than merged, since the two have genuinely different build contexts and only Cloud Run needs the model baked in) that `COPY`s both `backend/` and `classifier/best-model/`, and points `CNN_MODEL_PATH`/`CNN_LABELS_PATH`/`CNN_PREPROCESS_PATH` at the new in-image location (`config.py`'s defaults assume `cwd=backend/` with `classifier/` as a sibling, which is only true locally). Added `.dockerignore` at the repo root scoped to this new Dockerfile's context, excluding `.git/`, `flutter_app/`, `docs/`, `sandbox/`, local venvs/caches, and the non-`best-model` classifier artifacts — without it, `--source .` uploads the entire repo (including git history and the Flutter tree) on every deploy. Updated `deploy-cloud.sh` to `--source .` (repo root) and added `--memory 1Gi` (CNN inference plus ADK/litellm needs more than Cloud Run's 512Mi default).

### Gap 2 — cloud DB starts empty on every fresh instance, with no seed step

Cloud Run's filesystem is ephemeral per instance; `DATABASE_URL=sqlite+aiosqlite:////tmp/huluhilir.db` starts empty every cold start. Nothing in the existing app called the seed functions except a manual local script.

**Fix:** `backend/app/main.py`'s `lifespan` now calls `seed_treatments`/`seed_knowledge`/`seed_speech`/`seed_demo_farm` on every startup, after `init_db()`. Confirmed idempotent (each seed function already checked for existing rows before inserting — this was true before this change, just never invoked automatically). This makes CLOUD's behaviour "reseeded on every redeploy," which is acceptable and documented in `CLAUDE.md`'s two-deployment-targets table; it is a no-op LOCAL since the dev DB is already seeded there.

### Gap 3 — wrong Vertex AI model name, diagnosed via real logs and a direct API probe (not assumed)

First deploy (with gaps 1-2 already fixed) came up healthy, served `/health` and the full `setup → dashboard` flow correctly, but `/agent/run` failed. This was **not** an IAM/auth problem — worth stating explicitly since that was the a priori suspicion going in (new service account, new API to call) and it would have been easy to spend the remaining time on IAM bindings that were never actually broken. Confirmed by reading the actual failure, not guessing:

```bash
gcloud run services logs read huluhilir-api --project sfws-aicc-workspace-1 --region asia-southeast1 --limit 100
```

showed a full `litellm`/ADK stack trace ending in `litellm.exceptions.NotFoundError` with the message `Publisher model projects/sfws-aicc-workspace-1/locations/asia-southeast1/publishers/google/models/gemini-2.0-flash was not found`. A 404 from Vertex's own publisher-model endpoint, after auth succeeded and the request reached Google, is model-availability, not permissions. Confirmed which model names actually resolve for this project/region by probing Vertex's REST API directly rather than trying names one at a time against the full app stack:

```bash
TOKEN=$(gcloud auth print-access-token --account=a personal Google account)
for MODEL in "gemini-2.0-flash-001" "gemini-2.0-flash" "gemini-2.5-flash" "gemini-1.5-flash-002" "gemini-1.5-flash"; do
  curl -s -o /dev/null -w "%{http_code} $MODEL\n" -H "Authorization: Bearer $TOKEN" -H "x-goog-user-project: sfws-aicc-workspace-1" \
    "https://us-central1-aiplatform.googleapis.com/v1/publishers/google/models/$MODEL"
done
```

Only `gemini-2.5-flash` returned `200`; every 2.0 and 1.5 variant tried (including the "-001"/"-002" pinned releases) returned `404` for this project, in both `asia-southeast1` and `us-central1`. (User independently suggested trying `gemini-2.5-flash` mid-diagnosis, which matched what this probe had just found.)

**Fix:** `gcloud run services update` with `LITELLM_MODEL=vertex_ai/gemini-2.5-flash` and `VERTEXAI_LOCATION=us-central1` (env-var-only update, no rebuild) confirmed working, then made permanent in `deploy-cloud.sh` via `VERTEX_LOCATION`/`GEMINI_MODEL` variables (defaults `us-central1`/`gemini-2.5-flash`), with a comment pointing back to this log entry so a future "let's just use gemini-2.0-flash, it's newer-numbered" doesn't silently reintroduce the 404. Vertex AI's model location (`us-central1`) is deliberately decoupled from Cloud Run's own region (`asia-southeast1`, kept for Sarawak latency) — they don't need to match, and forcing them to match is not what fixed this.

### Verified (how)

- `GET /health` on the live URL after each deploy.
- Full `POST /setup` → `GET /farm/{id}/dashboard` round trip against the live service, confirming auto-seed produced usable treatment/knowledge/speech rows and the zero-photo-dashboard rule still holds with no diagnosis cycle run.
- `POST /agent/run` with a trivial no-tool-call prompt — succeeded end-to-end (`status: "ok"`, `llm_model: "vertex_ai/gemini-2.5-flash"`, ~10s), confirming the full Vertex AI auth + model-resolution path.
- `POST /agent/run` with a prompt requiring a real tool call (`get_weather`) — succeeded with `tools_called` correctly populated (real station data, `latency_ms: 193`), confirming Gemini 2.5 Flash's function-calling behaviour works through this ADK/LiteLLM path, not just plain text completion. This was checked separately from the trivial call because tool-calling reliability is a different capability than chat completion, and the only prior tool-calling confidence in this project (`test_agent_arbitration.py`) was against local Ollama/qwen2.5:14b — a different model with potentially different tool-calling characteristics.

### Known gaps

- Only single-tool-call arbitration has been verified against Vertex/gemini-2.5-flash so far — the full multi-tool arbitration sequence (diagnosis + weather + spread + treatment converging on one recommendation, the actual demo-critical path) has only been proven against local Ollama in `test_agent_arbitration.py`. If time allows, run that same test's scenario against the cloud URL before relying on it for a live demo.
- Two Cloud Run URLs were returned across different commands (the deploy command's own stdout vs. a later `gcloud run services describe` call) — both route to the same service (Cloud Run's default domain plus its stable alias), but only one should be used consistently in the cloud-target APK build and shared with the team.

---

## [Cloud Deploy 2] Ephemeral DB → Cloud SQL, root 404, and farm discoverability

Three problems surfaced when the deployed service was actually opened in a browser and poked at, rather than only curl'd at the routes known to exist.

### `GET /` returned `{"detail":"Not Found"}`

Correct FastAPI behaviour (no `/` route was declared), but the Cloud Run URL is a link people *open* — teammates, judges — and a 404 at the root reads as a broken deployment even when every real route is healthy. Added a root route that self-describes and points at `/docs`, plus `GET /health/ready`, which counts seeded rows: plain liveness cannot distinguish a healthy instance from one whose seed silently failed, which is a live risk on an ephemeral filesystem.

### The database was genuinely not durable — confirmed, not theorised

The farm created during the previous session's cloud test was **gone**. Root cause was not idle recycling: `gcloud run revisions list` showed revision `00003` was created at 08:42:52Z by the earlier `services update` (the Vertex AI model fix), a few minutes *after* the farm was created — and a new revision means a new container with a fresh, empty `/tmp`. So the real behaviour was: data survives within a revision, and is destroyed by every redeploy or env-var change. For a link meant to stay up across the competition that is not acceptable, and it also meant the seeded demo farm drew a **new ULID on every revision**, so nothing could reference it stably.

**Fix:** migrated CLOUD to Cloud SQL Postgres 15 (`huluhilir-db`, db-f1-micro, asia-southeast1). This cost almost nothing in code because `app/db.py` was already fully `DATABASE_URL`-driven and a grep confirmed zero SQLite-specific SQL anywhere in `app/` — the only code change was adding `asyncpg` to requirements. The connection string contains the DB password, so it lives in Secret Manager (`huluhilir-db-url`) and is injected via `--set-secrets DATABASE_URL=...`, never as a plaintext env var; Cloud Run reaches the instance over its Unix socket via `--add-cloudsql-instances`. The compute service account was granted `secretmanager.secretAccessor` and `cloudsql.client`.

**Verified by reproducing the original failure:** created a farm through the live API, then deliberately forced a new revision with a throwaway env-var update — the exact operation that destroyed the data last time. The farm survived (`/farms` returned both it and the demo farm), `/health/ready` reported `postgresql+asyncpg`, and the demo farm was **not** duplicated, confirming the idempotent seed guards work on Postgres and not just SQLite. A leftover `Durability Probe Farm` row is still visible on `/farms` from this test; harmless, but delete it before the pitch.

### `GET /farms` added

With farm IDs assigned at insert time, there was no way for a client — or a judge with a browser — to discover the current demo farm. This lists them. It exposes no ownership or boundary data (huluhilir-rules §4); a farm row is a name and a centroid point.

---

## [Block E] Speech — Cloud TTS over agent output, not pre-recorded clips

**Deliberate deviation from PLAN.md.** The original Block E bundled pre-recorded `.wav` clips per speech template, with synthesis as an "optimised tier" reach goal, and a `tts/` MMS-VITS service existed as a stub (never wired into the backend). That design inverts once the *agent* is the thing talking: a recommendation's `reason_ms` is composed at runtime from live weather and real block state, so there is no finite set of sentences to pre-record. Synthesising agent output directly is the only thing that actually covers the demo path.

**Rule #7 is not weakened by this.** Templates remain the canonical source of phrasing and `POST /speech/render` is the path that uses them (including `slot_vocabulary` lookup, so the spoken noun is the native-speaker-verified term rather than whatever the LLM wrote). `POST /speech/say` exists only for genuinely runtime-composed strings that no template can cover, and still records a `template_id` where one applies.

**Implementation:** `app/speech/synth.py` (Google Cloud TTS, ADC auth via the Cloud Run service account — no API key, same story as Vertex AI) and `app/routers/speech.py`. Audio is cached on `sha256(text + language + voice)` rather than on `(template_id, slots)`, because agent-composed strings have no template and two templates rendering identical text should not pay for synthesis twice. The synchronous Cloud TTS client is run via `asyncio.to_thread` so slow synthesis cannot block the rest of the API.

**Never on the critical path.** Every failure path returns `audio_uri: null` plus a `degraded_reason` instead of raising — a farmer who cannot hear the advice must still be able to read it. The route cannot 500 on a synthesis failure.

### Verified (how)

- Locally against **real** Cloud TTS (not a mock): `/speech/say` returned a genuine 36,480-byte MP3 in `ms-MY-Standard-A`, `/speech/audio/{key}` served it back with `content-type: audio/mpeg`, and an immediate repeat returned `cache_hit: true`.
- Against the deployed service after the Cloud SQL migration: same call succeeded on Cloud Run, confirming the service account's ADC reaches Cloud TTS with no key configured.

### Known gaps

- **No Iban voice exists.** Cloud TTS ships `ms-MY` but has no `iba` voice, and no major commercial TTS does. Iban currently falls back to the Malay voice reading Iban text — intelligible (shared phonology, Latin script) but not correct. The response reports which voice actually spoke, so this is visible rather than silently pretended-away. The `tts/` MMS-VITS stub (`facebook/mms-tts-iba`) remains in the repo precisely because it is the only route to a real Iban voice; it is unwired and untested.
- `duration_ms` is **estimated** from character count (~14 chars/sec at `speaking_rate` 0.92), not measured — decoding MP3 to measure it would need another dependency. Fine for sizing a progress bar, wrong for anything that needs real timing.
- **The Flutter app does not call these endpoints yet.** The backend speech layer is complete and verified; wiring playback into the dashboard is outstanding.
- Audio cache files are written under `MEDIA_ROOT` (`/tmp/media` on Cloud Run), so cached audio — unlike the database — is still lost on a new revision. Harmless: the `audio_cache` row and the file are re-created on the next request. Worth moving to Firebase Storage only if synthesis cost becomes a concern.

### Local test suite state

`tests/test_agent_arbitration.py` currently **fails locally** with `litellm.Timeout: Connection timed out. Timeout passed=600.0` against Ollama. This is an environment problem, not a regression: Ollama's HTTP endpoint answers (`/api/tags` → 200) but `qwen2.5:14b` generation exceeded ten minutes while the machine was simultaneously running Docker builds, Cloud Run deploys and a Flutter release build. A later re-run made the cause explicit — `Ollama_chatException - {"error":"an error was encountered while running the model: CUDA error: out of memory"}`. The GPU was exhausted by concurrent builds. The other 22 backend tests pass. Re-run this test on an otherwise-idle machine before trusting it either way — do not read the current failure as the agent being broken, and do not assume it passes without re-running it.

---

## [Web] Flutter web on Firebase Hosting — the UI, reachable without an APK

The Cloud Run URL is the **backend**. Opening it in a browser shows a JSON service descriptor, which is correct but useless as a demonstration — the product is the Flutter UI. The APK covers phones, but nothing let a judge (or a teammate without an Android device) *see* the app. Added a Flutter web target deployed to Firebase Hosting: **https://sfws-aicc-workspace-1.web.app**

This is the split `CLAUDE.md` already specified — Cloud Run for the backend (it needs a container, Vertex AI, Cloud SQL, none of which Firebase Hosting can run) and Firebase Hosting for the static frontend.

### Three real incompatibilities, each fixed without touching the Android path

Every fix below is guarded by `kIsWeb`, which is a **compile-time constant** on Android — the APK is byte-for-byte unaffected and the web branches are tree-shaken out. The committed mobile baseline was never put at risk.

**1 — `webview_flutter` has no web implementation**, so the 3D terrain cannot run in a browser. Rather than write a second 3D implementation, the dashboard falls back to `TerrainCanvas`, the 2D flow diagram that was deliberately kept when the 3D view replaced it. It takes an *identical* argument list, so this is a straight swap, not a parallel implementation to maintain. **This is exactly the scenario that fallback was retained for.**

**2 — `sqflite` has no web implementation**, and the dashboard calls `outbox.cacheFarmState()` on every load. Guarded inside `Outbox` itself (`static const _unavailable = kIsWeb`) so every method degrades to a no-op or empty result and no call site needs to learn about platforms. Losing the offline queue is acceptable on web in a way it never would be on a phone: the browser build exists so the dashboard can be *viewed*, and nobody walks a hillside with a laptop.

**3 — geolocation is unavailable or refused**, which hard-blocked registration with *"Akses lokasi diperlukan"*. This was a genuine product bug, not merely a web one: **a farmer who tapped "deny" once was permanently locked out of setup.** Location here only selects a weather station — farm structure comes from the walk and from the farmer's own elevation answers, which override sensors anyway (huluhilir-rules §3). Now falls back to a district centroid table with a non-blocking notice that the station is estimated. `_locate()` also catches outright (previously uncaught) exceptions, covering emulators with no location set and devices with location services off.

### `Lihat ladang demo` — the dashboard was otherwise unreachable

Even with registration fixed, completing setup requires *walking the farm with a GPS fix*. Nobody evaluating the app from a desk can do that, which left the entire dashboard — rain pulse, advisor, arbitration result, terrain model — unreachable to anyone not standing in a pepper garden. Added an entry point that loads the seeded demo farm read-only. It finds the farm **by name, not by a hardcoded ID**, because IDs are ULIDs assigned at insert time and the cloud DB reseeds on every new revision — any baked-in constant would go stale within a deploy. `listFarms()` returns raw maps rather than `FarmModel` because the caller needs `user_id`, which `FarmModel` deliberately does not carry: the app has no reason to know who owns a farm, and adding the field to serve one screen would spread ownership data everywhere a farm goes.

### Verified (how)

Driven end-to-end in a real browser against the live Cloud Run backend, not asserted from a successful build:
- Registration submitted with geolocation **blocked** — succeeded via the Kuching centroid fallback, and the farm was confirmed present in Cloud SQL by querying `/farms` afterwards (`Kebun Saya | lat 1.5533 lon 110.3592`).
- `Lihat ladang demo` → the full dashboard rendered: real rain pulse (**20 mm, Isnin, 1 hari lagi** — live weather, not seed data), the advisor card, and the terrain model showing all 6 blocks correctly ranked #1→#6 hulu-to-hilir with downhill flow arrows.
- CORS preflight from the hosting origin to Cloud Run returned 200, and the deployed bundle was confirmed to contain the current build by grepping `main.dart.js` over the network.
- `flutter analyze`: 0 new issues across all changes (same 5 pre-existing `info` items).

### Known gaps

- **The walk/capture flow still cannot complete in a browser** without granted geolocation — `TANDA BLOK` needs a real fix. Registration degrades; block capture cannot, since a block's position is its actual data. Web is therefore a *viewing* surface for the dashboard, not a substitute for the APK. The demo entry point exists precisely because of this.
- Browser HTTP caching served a stale `main.dart.js` for several minutes after a deploy, which briefly looked like a failed deployment during testing. `firebase.json` sets `max-age=3600` on JS. **Hard-reload after deploying, and do not trust a screenshot taken immediately after** — verify with a `cache: 'reload'` fetch instead.
- The 3D terrain remains Android-only. If a browser-based 3D view is ever wanted, `terrain.html` is already a standalone page and could be embedded via `HtmlElementView` + an iframe rather than by porting the scene.

---

## [Fix pass] Six reported defects — logo, landing page, terrain, upload, RAG, TTS

Reported after using the deployed build. Three of these were **placeholders that had never been implemented**, not regressions; saying so plainly matters more than the fix, because the affordances existed in the UI and therefore read as working features.

### 1 · Logo in every header

`docs/brand/logo.png` copied to `flutter_app/assets/brand/` and exposed as `BrandLogo` / `BrandLogoAction` (`lib/brand.dart`) rather than placed per-screen, so six headers cannot drift apart. It sits to the **right** of the wordmark, matching the landing page. `assets/brand/` needed its own `pubspec.yaml` line — directory assets bundle non-recursively, the same trap that silently dropped `terrain/vendor/` earlier. The banner goes in `README.md`, not the app.

`BrandLogo` falls back to an empty box rather than Flutter's broken-image glyph: a header briefly missing its logo is cosmetic, a red error box in the middle of a farmer's dashboard is not.

### 2 · Landing page (React + TypeScript + anime.js)

New `landing/` (Vite). Content condensed from `LANDING_PAGE.md`; palette and type mirror `lib/theme.dart` so the page and the product do not look like two products. anime.js v4 (`animate`/`stagger`/`createScope` — **not** the v3 default-export API; `@types/animejs` is v3-only and was removed since v4 ships its own types).

Hosting now serves the landing page at `/` and the Flutter app at `/app`, staged by `build-site.sh` into `public_site/`.

**Two real traps, both worth remembering:**

- **Motion must not gate content.** The first version put `opacity: 0` in CSS and animated it up. In a background tab — where `requestAnimationFrame` is throttled hard — the fade never finished and the page stayed *blank*. Now content is visible by default, JS adds `.motion-ready` immediately before animating, and a 4s failsafe force-reveals everything regardless. A page whose script never runs simply shows its content.
- **`--base-href /app/` cannot be passed from Git Bash on Windows.** MSYS rewrites anything path-shaped, so Flutter received `"C:/Program Files/Git/app/"` and failed citing a value nobody typed. `MSYS_NO_PATHCONV=1` did not help. The build now patches `<base href>` into the built `index.html` afterwards, which is immune and platform-independent.

### 3 · Terrain — green ground, real zoom, legend, cross-sections, and 3D on web

- **The 3D scene now runs in the browser.** Previously web fell back to the 2D diagram because `webview_flutter` has no web implementation. But `terrain.html` is already standalone, so on web it is embedded as an `<iframe>` (`lib/terrain_embed_web.dart`, selected by conditional import on `dart.library.js_interop`) driven by `postMessage` — the web counterpart of the Android `JavaScriptChannel`. **One scene file, one payload shape, two transports.** Selection opens the same native profile overlay on both.
- **Green, natural ground.** The old white → cyan → orange → green ramp read as desert terracing, and worse, implied that ground colour encoded risk. It is now green throughout, lightening with height the way a real hillside does. Risk is carried by the pillars and cross-sections, never by the ground. Ambient/sun were also lowered — they had been tuned against the pale ramp and blew out mid-greens — and `STEP_HEIGHT` dropped 0.5 → 0.28 so terracing reads as bench terraces rather than a ziggurat.
- **Zoom actually moves now.** `minDistance`/`maxDistance` were 8–26, tight enough that pinching felt inert. Now 3.5–60.
- **Legend moved into the scene**, so it travels with the terrain on every platform instead of only existing on the 2D fallback. Colours are taken from `STATE_COLOUR` directly rather than eyeballed.
- **Cross-sections.** A semi-transparent column tinted by the block's condition, cut down through the terrain — the soil-core metaphor is the correct one, since foot rot is a *soil-borne* disease and a block's condition is a property of the ground under it, not the canopy above. Depth is fixed, not scaled by risk: it is a section, not a bar chart, and varying its length would imply a magnitude the model does not claim. It had to span *above* the surface too — a column entirely underground was fully occluded by the opaque terrain, leaving only its cap disc visible.

### 4 · `Unsupported operation: _Namespace` on photo submit

`dart:io`'s `File` does not exist on web; constructing one throws exactly that. `uploadMedia` now takes `Uint8List` and callers use `XFile.readAsBytes()`, which works on both platforms — and the bytes were needed for the content hash anyway. `walk_screen`'s voice label followed: `AudioRecorder.stop()` returns a path on Android and a blob URL on web, so both are read back over HTTP rather than through the filesystem (`lib/recording_io.dart`). A lost voice label never blocks capturing the block — it is an optional audio sticker, not required data.

**The ONNX model was never the problem** and is confirmed working on Cloud Run: a real upload through `/media` → `/observations` returned `defoliation_wilt 0.6296` with all six class scores and `inference_ms: 6`.

### 5 · Tanya (RAG) was a placeholder

The FAB showed *"Tanya (RAG) — datang tidak lama lagi"*. The **Advisor agent already existed** (`app/agent/advisor_agent.py`) with retrieval wired; it simply had no HTTP route and no UI. Added `POST /advisor/ask` and `TanyaSheet`.

Deliberately **not** persisted as an `agent_run`: those record decisions that produced recommendations, and a farmer asking "what causes foot rot" produced none — mixing them would corrupt the arbitration audit trail `tools_called` exists to evidence. The rule-2 guarantee here is structural, not prompt-based: the agent's only tool is scoped away from the authoritative namespace, so it *cannot* reach a dose, product, or timing.

Verified live: *"Apa punca penyakit busuk pangkal?"* returned a correct Malay answer citing `kb_001` via a real `retrieve_knowledge` call.

### 6 · TTS was a placeholder

The speaker button showed `Suara: rain_pulse_forecast (Block E)` — a snackbar naming the template id, never wired to the Block E speech endpoints. Now calls `/speech/say` and plays the result (`lib/speech.dart`). The spoken line is composed from the same live values the card displays, so audio cannot drift from the text beside it. Verified from the deployed origin: a real 33,216-byte `audio/mpeg` in `ms-MY-Standard-A`.

### Verified (how)

Driven in a real browser against the live stack, not inferred from builds: 3D terrain rendering with all 6 real blocks, zoom, click-to-select opening the native profile card, cross-sections visible; landing page rendering and scroll-revealing; `/` serving the landing page and `/app/` serving the Flutter app with the correct `<base href>`; ONNX inference and TTS confirmed by direct API calls. `flutter analyze`: 0 new issues. `tsc -b` clean.

### Known gaps

- The **cross-section depth carries no data** — it is uniform. If block-level severity should be legible at a glance, that is a deliberate next decision, not an oversight.
- `REPO_URL` in `landing/src/content.ts` is a **placeholder**; the repo is not published yet. It must be corrected before the landing page is shared, or the two most prominent buttons 404.
- Firebase Hosting caching bit twice during testing, serving a stale bundle long enough to look like a failed deploy. `no-cache` is now set on both `index.html` files, but **hard-reload after deploying** rather than trusting a screenshot.
- Web still cannot complete the walk (block capture needs a real GPS fix), and the browser blocks geolocation by default — registration degrades to a district centroid, capture cannot.

---

## [Polish pass] Barometer tier, walk map, settings, block history — and an L1 model finding

### 1 · Barometer: detection was right, the arithmetic was not

Detection and altitude tracking already worked — baseline pressure captured before walking, continuous listening, `baro_rel_m` computed per block. What was missing was that **nothing ever told the farmer which path they were on**, so two very different setup experiences looked like one flow behaving inconsistently. `TierBanner` now states it plainly (`Barometer dikesan` / `Tiada barometer`, OPTIMISED / MINIMAL) on both registration and the walk screen, and `AltitudeReadout` shows live relative altitude while walking so the sensor is visibly tracking rather than merely claimed to be.

**The real defect was in `pairs_needing_farmer_input()`.** Without a barometer it asked only the **n−1 adjacent pairs**. That is only sufficient if the blocks already arrive in a trustworthy order — and without an altitude sensor they do not: capture order is just the order the farmer happened to walk in, so comparing neighbours in that arbitrary sequence establishes nothing. It now asks **every distinct pair, C(n, 2)**, which is the honest cost of having no sensor and additionally makes contradictions (a > b, b > c, c > a) detectable, which a chain of n−1 answers cannot surface at all.

This is quadratic and the banner says so before the walk rather than after: 6 blocks = 15 questions, 10 blocks = 45. That burden **is** the argument for the barometer path.

`test_minimal_tier_asks_all_adjacent_pairs` encoded the old behaviour and failed — correctly. Rewritten as `test_minimal_tier_asks_every_distinct_pair`, now also asserting the pairs are distinct and no block is compared with itself.

### 2 · Map during the walk

`WalkMap` (flutter_map + OpenStreetMap tiles): the GPS track so far, a numbered pin per captured block, and a live position marker. Auto-follows, and any manual pan releases the follow with a recentre button — yanking the camera back on every GPS tick makes a map unusable.

It draws the walked path and marked points **only**. No boundary is drawn, inferred, or stored, because a polygon around someone's plot is precisely what huluhilir-rules §4 forbids on NCR land. Tiles are the one network-dependent part of the walk, so it is deliberately additive: the track and markers still render over an empty background and **nothing about capturing a block depends on a tile arriving**. OSM attribution is required by licence and is not decoration.

### 3 · Settings

The gear previously showed a snackbar telling the farmer to long-press it — a hint about a hidden gesture, not a setting. `SettingsSheet` now offers Tanya, a rain-alert toggle, log out, and reset. Reset keeps its confirmation *and* its long-press shortcut, because wiping a farm means re-walking the whole garden.

`signOut()` and `reset()` are separate methods with identical mechanics today, deliberately: they are different promises ("your farm is still there" vs "start over"), and if server-side deletion ever exists only `reset()` should call it. The rain-alert toggle is a local display preference — it does not subscribe to push, and it never touches neighbour alerts, which stay drafted and farmer-approved regardless (§5).

### 4 · Block profile: photo, history, voice label

The old card rendered only fields already in the dashboard payload, so the photo, voice label and history had **nowhere to come from**. Added `GET /blocks/{id}/detail` and `BlockProfileCard`, which fetches on tap. Kept out of the dashboard payload on purpose: it is only wanted when a farmer actually taps a block, and folding it in would make every dashboard load heavier on a slow connection.

The block's own photo is the card header — that is what makes a block recognisable to the person who marked it — behind a scrim so type stays readable, falling back to the state colour rather than a broken-image glyph. History rows show the class, date, confidence, and **an explicit "keyakinan rendah — periksa sendiri" when the call was uncertain**, which matters more than usual given the model finding below.

The voice label is **played, never transcribed**. There is no ASR anywhere in this codebase, and that is exactly why an Iban label works here at all (§1). The old dead `_BlockProfile` was deleted rather than left beside the new one — two implementations of one card is how they drift.

### 5 · L1 false positives — investigated properly; the wiring is fine, the model is not

Reported: green healthy leaves classified as yellowed/wilted. **Everything I could check about incorporation is correct**, and I checked rather than assumed:

- `best-model/huluhilir_l1.onnx` is distinct from `huluhilir_l1_baseline.onnx` (different SHA-256) — the best model *is* the one deployed.
- ONNX IO is `[batch, 3, 224, 224] → [batch, 6]`, matching the pipeline.
- Output is **raw logits** (sums to 0.14, has negatives), so applying softmax once is correct.
- `labels.txt` order matches the documented class-index table in `L1_IMPLEMENTATION_LOG.md` exactly (`healthy_leaf` = 0 … `unrelated` = 5). An alphabetical-vs-declared mismatch would have shifted every prediction and was the first thing suspected; it is not present.
- Preprocessing (224×224, ImageNet mean/std, RGB) matches `L1_MODEL_ROADMAP.md`.

**Then I probed the model directly with flat colour fields, and the results are damning:**

| input | prediction |
|---|---|
| solid black | `healthy_leaf` **0.78** |
| solid brown | `healthy_leaf` **0.91** |
| solid white | `foliar_yellowing` **0.73** |
| solid green | `defoliation_wilt` **0.64** |
| random noise | `unrelated` 0.31 |

A sound model puts every one of those in `unrelated` with high confidence. Being *confidently* wrong on degenerate inputs is the signature of a model that never learned robust features.

I then re-ran all five plausible preprocessing variants (RGB/BGR, ImageNet-normalised, 0–1, raw 0–255, [-1,1]). **Every variant still calls solid black `healthy_leaf`.** That excludes a preprocessing mismatch and locates the problem in the weights themselves — consistent with training on ~530 originals, largely AI-generated prompt batches, augmented 7×. Logit magnitudes are also small (max ≈ 2.2), i.e. a weakly-confident model throughout.

**No code change fixes this.** What was added is a mitigation and is labelled as one: a **top-2 margin gate** (`confidence_margin = 0.15`) alongside the absolute threshold, so a ~0.40/0.36 split is treated as undecided instead of asserted. `below_threshold` now means "uncertain by either test", and the UI already routes that to *periksa sendiri*.

**The real fix is retraining on real field photographs.** Until then L1 should be presented as an early-warning prompt to go and look, never as a diagnosis — which is what huluhilir-rules §9 required anyway.

`pokok` (`whole_vine`) removed from the capture-target selector as requested. The enum value is retained so existing observation rows stay readable; nothing offers it any more.

### Verified (how)

22 backend tests pass (the live-LLM arbitration test excluded — it needs an idle GPU). `flutter analyze` back to the 4 pre-existing info items. Model claims above come from direct probes of the deployed ONNX file, not from documentation.

### Known gaps

- **The L1 model itself is the outstanding risk.** Everything around it is correct; it needs real-photo retraining, and no amount of threshold tuning substitutes.
- Map tiles need network. Offline the walk still works, but the map is blank.
- `signOut()` clears only local state; there is no server-side session to end.
- The pairwise question count is honest but heavy at scale — 10 blocks is 45 comparisons. If that proves unusable in the field, the fix is a smarter sort (merge-insertion needs ~n log n comparisons), not a return to the n−1 chain that never established an order.

---

## [Autonomy pass] Silent terrain reconstruction, durable media, and two MSYS traps

### The autonomous barometer path already worked — it was just invisible

Verified on the live service: a farm with a barometer and four well-separated blocks asks **zero questions**, and `resolve-elevation` returns the correct hulu→hilir ordering with 4.0 m drops and 6 flow edges, derived entirely from sensor readings plus GPS distances. The pieces were all there — `pairs_needing_farmer_input` returns nothing when the sensor separates every pair, `sort_key` falls through to `baro_rel`, and `build_flow_edges` does k-NN on haversine distance filtered by rank.

What was wrong is that **the farmer never saw it happen**. `elevation_screen` did `if (questions.isEmpty) await _submit()` and jumped straight to the dashboard, so the single most impressive thing the system does — reconstructing an entire slope from readings taken while someone walked — showed up as a spinner.

`/resolve-elevation` now also returns `derived_automatically`, `questions_answered`, and a per-block list with `drop_from_above_m`; `TerrainDerivedScreen` shows it. No confirmation control and no "correct this" button, deliberately: the ordering came from a measurement the farmer was never asked to make, and inviting them to second-guess it here would be the wrong place. §3 still holds — a farmer's answer beats the sensor — but the place to give that answer is the question flow, which is exactly what the MINIMAL path is.

### Media was still ephemeral while the database was not

The block profile showed no background image, and chasing it surfaced something worse: moving the DB to Cloud SQL without moving media left the two **out of step**. Observation rows survived a redeploy; the images they pointed at did not. `header_image_uri` resolved to a real URI that then 404'd — a broken reference that looked like a UI bug and was actually data loss.

Fixed by mounting a GCS bucket (`huluhilir-media`) as a Cloud Run volume at `/media`. No application code changed — `MEDIA_ROOT` points at the mount. Verified properly: uploaded a file, confirmed it appeared as an object in the bucket, forced a revision roll, and re-fetched it successfully (200, same bytes).

Also added a header fallback: seeded blocks carry a `seed/` placeholder path, so the demo farm — the one every judge opens — had no header image. It now falls back to the block's most recent observation photo, which is both valid and a more current view than the day it was marked.

### Two Git-Bash path-mangling traps, and one wrong fix

MSYS rewrites any argument that looks like a Unix path. It bit twice here:

- `--add-volume-mount "volume=media,mount-path=/media"` reached gcloud as `mount-path=C:/Program Files/Git/media` → *"should be a valid unix absolute path"*, naming a value nobody typed.
- Less obviously, `--set-env-vars "MEDIA_ROOT=/media"` was mangled the same way. The **volume mounted correctly** while the app wrote to a container-local directory literally named `C:/Program Files/Git/media`, so uploads still vanished and the bucket stayed empty. This one is nastier because the deploy succeeds and the config *looks* right until you read the deployed env.

**`MSYS_NO_PATHCONV=1` is not the fix** — it breaks gcloud's own launcher, which relies on that same conversion to locate `gcloud.py` (`can't open file 'C:\c\Users\...\gcloud.py'`). The working escape is a **double slash**: `//media` is left alone by msys and collapses to `/media` at both ends, verified by round-tripping the argument.

### Verified (how)

Autonomous flow driven end-to-end against the live service (0 questions, correct ranks, real drops). Media persistence proven by surviving a deliberate revision roll. RAG, settings, block history, tier banner, map and the absence of `pokok` all confirmed present in the **deployed** bundle by grepping `main.dart.js` over the network, and `/advisor/ask` + `/blocks/{id}/detail` exercised from the hosting origin. 22 backend tests pass; `flutter analyze` at the 4 pre-existing info items.

### Known gaps

- **The L1 model remains the outstanding risk** — unchanged by this pass, and no threshold repairs it. Retraining on real field photographs is the fix.
- `/advisor/ask` takes ~18 s (a full Vertex round trip with a tool call). Fine for a considered question, too slow to feel conversational.
- Two stray local dev servers from earlier debugging (ports 8077/8099) were left running across sessions and are now stopped; the only remaining periodic task is the walk-sample flush timer, which is necessary and correctly cancelled in `dispose()`.
- Test farms (`Durability Probe Farm`, `nCr Probe`, `Auto Terrain Probe`) are visible on `/farms`; delete before the pitch.

---
