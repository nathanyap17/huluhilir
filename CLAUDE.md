# PepperDex (formerly HuluHilir)

Terrain-aware agentic disease diagnosis and management system for Phytophthora foot rot in Sarawak black pepper.

**Competition:** AgroHack 2026 @ Sarawak AgroFest — Sibu Town Square, 25–27 September 2026
**Build rule:** Product must be built **before** exhibition day. Pre-building is expected, not restricted — this is the opposite of AICC's live-build-only rule. Do not apply AICC-era time-pressure instincts here.
**Team:** SMILING FACE WITH SUNGLASSES — Nathan (technical) · Zoe (deliverables) · Abraham (PM)

> **Read `PLAN.md` before starting any task.** `docs/PROJECT_SPEC.md` holds system design (v1 + v2 already merged into one document — no separate delta file exists anymore); `docs/DATA_MODEL.md` holds the schema; `docs/CREDENTIALS.md` holds every environment variable and the deployment URL, once captured. Do not invent behaviour that contradicts them. If two documents disagree, the more recently dated correction wins — flag the conflict rather than silently picking one.

---

## The one-sentence product

Existing tools diagnose a single plant. PepperDex models **where the disease travels next, and when** — because foot rot moves downhill through water in rain pulses, not continuously.

---

## Stack (v2)

| Layer | Technology |
|---|---|
| Frontend | **React Native (Expo)** — Android APK. *(v1 was Flutter — fully replaced, not refactored.)* |
| Backend | FastAPI (Python 3.11+), Pydantic v2 |
| Agent | Google ADK + LiteLLM |
| LLM | **Local:** Ollama (Gemma / Qwen), native on host · **Cloud:** Gemini API — one LiteLLM line |
| Storage | SQLAlchemy 2.0 async + SQLite (`aiosqlite`) → Cloud SQL if cloud path taken |
| CNN | MobileNetV3-Small → **`.onnx` sole primary**. No Gemini Vision fallback — removed, not demoted (v1 used it only as a workaround for a label-order bug, since fixed) |
| Speech | Pre-recorded clips (MVP) → MMS-TTS (optimised) |
| Integrations | **MCP** — device calendar sync, consent-gated, drafted never automatic |
| Deploy | Docker Compose (local, always works) · Cloud Run + Firebase (public — **first-class target, not a gated stretch goal**; AgroHack's pre-build rule removes the time pressure that justified gating it in v1) |

---

## Architecture — five layers

```
L0  Voice & Language   pre-recorded clips → MMS-TTS · voice labels · NO ASR
L1  Diagnosis          MobileNetV3-Small, 6 classes, .onnx only
L2  Spread             Deterministic directed elevation graph — NOT ML
                        + rotation/proportional layout for the terrain canvas (v2)
L3  Knowledge          JSON rules (authoritative) + hybrid retrieval (explanatory only)
                        + query_farm_history tool for structured data (v2)
L4  Agent              ADK root + 2 LoopAgents + 1 Advisor + 1 Overrun Council (v2)
```

### Agent topology (v2)

```
RootAgent (LlmAgent) — router + arbitrator
├── FunctionTools (deterministic)
│     diagnose_leaf (.onnx only) · get_weather · compute_spread (+rotation)
│     get_treatment · find_spray_window · query_farm_history
├── FunctionTools (LLM-backed)
│     explain_why · draft_alert · draft_calendar_sync
├── AgentTool → SetupCoordinator      (LoopAgent, max_iterations=25)
├── AgentTool → DiagnosisCoordinator  (LoopAgent, max_iterations=30)
├── AgentTool → Advisor               (LlmAgent + hybrid RAG, non-loop)
└── AgentTool → OverrunCouncil        (ADK-native sub_agents — NOT the A2A protocol)
      ├── AgronomicUrgencyAgent · CostFeasibilityAgent · LogisticsAgent
      └── CouncilOrchestrator — ranks only, dose-less response schema (see rule 12)
```

**Full RootAgent instruction text:** `docs/PROJECT_SPECS-v2.md` §B.1a. That file's version supersedes any older instruction text — do not reconstruct the prompt from this summary alone.

**The differentiator is arbitration**, not the framework. When L1 says "treat now", L3 says "24 h rain-fast", weather says "46 mm tomorrow", and L2 says "downslope risk in 4 days" — the agent outputs **one action, one time, one reason**: *"Clear the drain today. Spray Thursday morning."*

**The council fires only during Overrun-state triage** — multiple simultaneously-Harmed blocks with no single deterministic priority order. It is not part of a normal diagnosis cycle. Do not present or build it as standard behaviour.

---

## Non-negotiable rules

Product commitments made in a submitted proposal. **Never violate them, even for a shortcut.** Full list with code examples: `.claude/skills/pepperdex-rules/SKILL.md` (13 rules).

1. **No ASR on the critical path.** Voice labels are stored as audio and replayed — never transcribed.
2. **The rules table is the only source of dose, product, and timing.** Retrieval explains *why*; it never decides *what*.
3. **Farmer's elevation answer always overrides sensors.** Log conflicts, never auto-resolve against the farmer.
4. **No land boundaries or ownership recorded.** Only `elevation_rank` ordering (+ proportional spacing in v2 — real distance, never a georeferenced map). NCR land is legally sensitive.
5. **Neighbour alerts are drafted, never auto-sent.** `approved_by_farmer` defaults false.
6. **The app must work with zero photographs taken.** Rain-pulse warnings and the Advisor run without any diagnosis cycle existing.
7. **Every user-facing string has a `speech_template_id`.** Literacy is not assumed.
8. **Every risk number carries `is_estimate: true`.** The spread model is physically-motivated, not field-validated.
9. **The Overrun Council may re-rank actions; it may never generate a treatment, dose, or timing.** Enforced by its response schema having no such field — not by convention.
10. **Calendar sync is drafted and consent-gated, never automatic.** Same approval pattern as neighbour alerts, reused not reinvented.

---

## Conventions

- **Pydantic models are the single contract.** Define tool I/O once; reuse for FastAPI validation, ADK tool schema (`.model_json_schema()`), and generated TypeScript types (`openapi-typescript`, replacing v1's generated Dart classes). Contract drift is the top integration risk.
- **A dose-less schema is a real guardrail, not documentation.** `TriageRanking` has no field that could hold a treatment — this is how rule 9 is actually enforced.
- **IDs are ULIDs**, generated client-side so offline capture works. Never rely on DB autoincrement.
- **Timestamps** ISO 8601, `Asia/Kuching` (UTC+8).
- **SQLite has no array type** — use `JSON` columns for `path_block_ids`, `applies_to`, `all_scores`, `embedding`.
- **Loop agents must always set `max_iterations`.** Never allow an unbounded loop.
- **Loop termination checkers are deterministic Python**, not LLM judgement. The LLM only picks which `template_id` to speak.
- Language codes: `ms` (Bahasa Malaysia), `iba` (Iban), `en`.

---

## Deployment — two targets, cloud is a real target now, not a stretch goal

**v1 gated cloud behind a "17:00 on 23 Aug" hackathon clock — that rule no longer applies.** AgroHack's build-before-exhibition rule removes the time pressure that justified treating cloud as a nervous stretch goal. Build it properly from the start.

| | LOCAL | CLOUD |
|---|---|---|
| Backend | Docker Compose on laptop | Cloud Run container, same image |
| LLM | Ollama, offline | Gemini API via LiteLLM |
| DB | SQLite file | SQLite in image → Cloud SQL |
| Reached by | Phone on own hotspot | Public HTTPS, any device |

**Rules that still hold:**
- Never break LOCAL to enable CLOUD. Local must remain runnable at all times.
- Switching is **configuration only** — `API_BASE_URL`, `LITELLM_MODEL`, `DATABASE_URL`. No application code branches on target.
- Build **two APKs**: one local, one cloud.

---

## Commands

```bash
# Backend (repo root) — unchanged
docker compose up --build
ollama serve   # native on host, NOT in Docker

# Frontend — React Native (Expo), replacing all Flutter commands below
npx expo start
./release-apk.sh [--deploy]   # local build (EAS quota spent until 1 Oct), EAS-key signed,
                              # staged as /pepperdex-latest.apk + version.json on the site
# eas build --platform android --profile cloud   # again once the EAS quota resets

# Cloud -- use the scripts; they target the EXISTING service/site (see note below)
./deploy-cloud.sh             # backend -> Cloud Run huluhilir-api (Vertex Gemini 2.5 Flash)
./build-site.sh [--deploy]    # landing page (+ latest APK) -> Firebase Hosting
```

**Cloud identifiers keep the v1 name on purpose** (owner decision 2026-09-24): Cloud Run service `huluhilir-api`, GCP/Firebase project `sfws-aicc-workspace-1`, region `asia-southeast1`, Cloud SQL `huluhilir-db`, secret `huluhilir-db-url`, bucket `huluhilir-media`, local DB `huluhilir.db`, repo `nathanyap17/huluhilir`. Renaming any of them creates a new service/URL. Deploy with `./deploy-cloud.sh`, which already uses these.

**Testing on a real phone over LAN/hotspot (start, stop, firewall, `.env` placement):** see
`../WORKSPACE_SETUP.md` § "Local hosting for phone testing" — the tested, working sequence,
not just the summary above. Covers why `--host 0.0.0.0` matters and how to find/kill a
backgrounded server by port.

---

## What to never cut

Spread graph · agent arbitration · `tools_called` logging · CNN diagnosis · walk loop · the council's dose-less schema wall.

See `PLAN.md` for the full v2 change list and open items.

---

## Shipping status

The hold was lifted on 2026-09-24 (owner verified local testing). The backend runs on Cloud Run
(always on, Vertex AI); the landing page at https://sfws-aicc-workspace-1.web.app/ serves the
PepperDex page and the latest APK at a fixed URL (the bunting QR). The v1 Flutter `/app` web build
is no longer published. Deploying and pushing to GitHub still need the owner's go-ahead each time.
