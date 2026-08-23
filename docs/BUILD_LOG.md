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
