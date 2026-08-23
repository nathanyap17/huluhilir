# HuluHilir

Terrain-aware agentic early warning system for Phytophthora foot rot in Sarawak black pepper.

**Competition:** AI Code Competition 2026 (AICC) — SAIC · Track 3 · Category B · **Finalist**
**Build window:** 23 Aug 10:00 → 24 Aug 10:00, on-site at TDV Kuching
**Team:** SMILING FACE WITH SUNGLASSES — Nathan (technical) · Zoe (deliverables) · Abraham (PM)

> **Read `PLAN.md` before starting any task.** `docs/PROJECT_SPEC.md` holds system design; `docs/DATA_MODEL.md` holds the schema. Do not invent behaviour that contradicts them.

---

## The one-sentence product

Existing tools diagnose a single plant. HuluHilir models **where the disease travels next, and when** — because foot rot moves downhill through water in rain pulses, not continuously.

---

## Stack

| Layer | Technology |
|---|---|
| Frontend | Flutter (Dart) — Android APK |
| Backend | FastAPI (Python 3.11+), Pydantic v2 |
| Agent | Google ADK + LiteLLM |
| LLM | **Local:** Ollama (Gemma / Qwen), native on host · **Cloud:** Gemini API — one LiteLLM line |
| Storage | SQLAlchemy 2.0 async + SQLite (`aiosqlite`) → Cloud SQL if cloud path taken |
| CNN | MobileNetV3-Small → `.tflite` (on-device) with `.onnx` backend fallback |
| Speech | Pre-recorded clips (MVP) → MMS-TTS (optimised) |
| Deploy | **Local:** Docker Compose + own hotspot · **Cloud:** Cloud Run + Firebase (stretch) |

---

## Architecture — five layers

```
L0  Voice & Language   pre-recorded clips → MMS-TTS · voice labels · NO ASR
L1  Diagnosis          MobileNetV3-Small, 6 classes
L2  Spread             Deterministic directed elevation graph — NOT ML
L3  Knowledge          JSON rules (authoritative) + retrieval (explanatory only)
L4  Agent              ADK root + 2 LoopAgents + 1 advisor
```

### Agent topology

```
RootAgent (LlmAgent) — router + arbitrator
├── FunctionTools (deterministic)
│     diagnose_leaf · get_weather · compute_spread
│     get_treatment · find_spray_window
├── FunctionTools (LLM-backed)
│     explain_why · draft_alert
├── AgentTool → SetupCoordinator      (LoopAgent, max_iterations=25)
├── AgentTool → DiagnosisCoordinator  (LoopAgent, max_iterations=30)
└── AgentTool → Advisor               (LlmAgent + RAG, non-loop)
```

**The differentiator is arbitration**, not the framework. When L1 says "treat now", L3 says "24 h rain-fast", weather says "46 mm tomorrow", and L2 says "downslope risk in 4 days" — the agent outputs **one action, one time, one reason**: *"Clear the drain today. Spray Thursday morning."*

---

## Non-negotiable rules

Product commitments made in a submitted proposal. **Never violate them, even for a shortcut.**

1. **No ASR on the critical path.** Voice labels are stored as audio and replayed — never transcribed.
2. **The rules table is the only source of dose, product, and timing.** Retrieval explains *why*; it never decides *what*.
3. **Farmer's elevation answer always overrides sensors.** Log conflicts, never auto-resolve against the farmer.
4. **No land boundaries or ownership recorded.** Only `elevation_rank` ordering. NCR land is legally sensitive.
5. **Neighbour alerts are drafted, never auto-sent.** `approved_by_farmer` defaults false. Only a risk band is stored against another farmer's block.
6. **The app must work with zero photographs taken.** Rain-pulse warnings and the Advisor run without any diagnosis cycle existing.
7. **Every user-facing string has a `speech_template_id`.** Literacy is not assumed.
8. **Every risk number carries `is_estimate: true`.** The spread model is physically-motivated, not field-validated.

---

## Conventions

- **Pydantic models are the single contract.** Define tool I/O once; reuse for FastAPI validation, ADK tool schema (`.model_json_schema()`), and generated Dart classes. Contract drift is the top integration risk.
- **IDs are ULIDs**, generated client-side so offline capture works. Never rely on DB autoincrement.
- **Timestamps** ISO 8601, `Asia/Kuching` (UTC+8).
- **SQLite has no array type** — use `JSON` columns for `path_block_ids`, `applies_to`, `all_scores`, `embedding`.
- **Loop agents must always set `max_iterations`.** Never allow an unbounded loop.
- **Loop termination checkers are deterministic Python**, not LLM judgement. The LLM only picks which `template_id` to speak.
- Language codes: `ms` (Bahasa Malaysia), `iba` (Iban), `en`.

---

## Two deployment targets

**LOCAL is the committed baseline. CLOUD is a stretch goal, gated at 17:00 on 23 Aug.**

| | LOCAL (must work) | CLOUD (if ahead of schedule) |
|---|---|---|
| Backend | Docker Compose on laptop | Cloud Run container |
| LLM | Ollama, offline | Gemini API via LiteLLM |
| DB | SQLite file | SQLite in image → Cloud SQL |
| Reached by | Phone on own hotspot | Public HTTPS, any device |
| Depends on | Nothing external | Venue connectivity |

**Rules for the cloud path:**
- Never break LOCAL to enable CLOUD. Local must remain runnable at all times.
- Switching is **configuration only** — `API_BASE_URL`, `LITELLM_MODEL`, `DATABASE_URL`. No application code branches on target.
- Build **two APKs** (`--dart-define=API_BASE_URL=...`): one local, one cloud.
- If the 17:00 gate is missed, stop. Local plus a public GitHub repo is a complete, acceptable submission.

---

## Commands

```bash
# Backend (repo root)
docker compose up --build

# Ollama — native on host, NOT in Docker
ollama serve

# Flutter
flutter run --dart-define=API_BASE_URL=http://<LAPTOP_LAN_IP>:8000
flutter build apk --release

# Demo mirroring
scrcpy --stay-awake

# Cloud (stretch only — after the 17:00 gate)
gcloud run deploy huluhilir-api --source . --region asia-southeast1 \
  --allow-unauthenticated --min-instances 1
firebase deploy --only hosting,storage
```

---

## What to never cut

Spread graph · agent arbitration · `tools_called` logging · CNN diagnosis · walk loop.

See `PLAN.md` § Cut Order for what to sacrifice under time pressure.
