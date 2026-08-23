# PLAN.md — HuluHilir Development Plan

> **Competition:** AI Code Competition 2026 (AICC) — SAIC
> **Build window:** 23 Aug 10:00 → 24 Aug 10:00 (24 h, on-site, TDV Kuching)
> **Rule:** all code created on-site. Prep produces *assets and knowledge*, not committed code.
> ✅ **Organiser ruling confirmed (EXP-1):** pre-trained model weights and pre-recorded audio assets are allowed on-site.

---

## Phase 0 — Prep (now → 22 Aug)

**Permitted:** research, interviews, paper sketches, dataset gathering, asset preparation, tooling installation.
**Not permitted:** repo commits, design files, pitch decks, coded prototypes.

Validation experiments run in `../sandbox/`, **not here.** See `../sandbox/EXPERIMENTS.md`.

| # | Task | Owner | Output |
|---|---|---|---|
| 0.1 | EXP-1 · organiser ruling on pre-built assets | Zoe | ✅ Allowed — pre-trained weights & audio permitted on-site |
| 0.2 | EXP-2 · MMS Iban TTS verification | Nathan | ✅ Audio generated (~0.3–0.5s); speaker verdict pending |
| 0.3 | EXP-3 · Ollama over hotspot | Nathan | ⏳ Working ping (needs phone) |
| 0.4 | EXP-4 · barometer availability + threshold | Nathan | ⏳ Threshold value (needs phone) |
| 0.5 | EXP-5 · LLM tool-calling reliability | Nathan | ✅ Model locked: `qwen2.5:14b` / `gemma4:e2b` (`gemma2:9b` failed) |
| 0.6 | EXP-6 · GPS under canopy | Nathan | ⏳ Accuracy profile (needs phone) |
| 0.7 | EXP-7/8 · CNN train + export both formats | Nathan | ✅ Best model exported (`huluhilir_l1.onnx` in `classifier/best-model/`, F1 0.934) |
| 0.8 | EXP-12 · ~25 Iban templates + audio clips | Abraham | ⏳ `templates.json`, `.wav` set (needs Iban speaker) |
| 0.9 | Rules table from MPB/DOA with citations | Abraham | `rules.json` |
| 0.10 | EXP-9 · weather APIs + cached fallback | Abraham | ✅ `cached_weather_kuching.json` saved (data.gov.my active) |
| 0.11 | Environment setup — see `../WORKSPACE_SETUP.md` | All | ✅ Flutter 3.41.2, Python 3.12, scrcpy v4.1, Git 2.51.2, gcloud, firebase |
| 0.12 | **Warm Gradle cache** (throwaway `flutter create`) | Nathan | ⏳ Needs phone connected |
| 0.13 | Pre-pull Docker images + HuggingFace models | Nathan | ✅ HuggingFace cached; Docker v29.1.3 daemon running |
| 0.14 | Record real farm walk as demo seed | Nathan | GPS/baro trace |
| 0.15 | APK signing keystore | Nathan | `.jks` |
| 0.16 | EXP-11 · scrcpy rehearsal | Nathan | ⚠️ scrcpy v4.1 installed; phone mirror test pending |
| 0.17 | EXP-13 · GCP project, billing, APIs enabled, `gcloud`/`firebase` | Nathan | ✅ `gcloud` (SDK 574.0.0) + `firebase` (v15.28.1 via npx) installed; account setup pending |

---

## Phase 1 — Build (23 Aug 10:00 → 24 Aug 10:00)

### Block A · 10:00–13:00 — Foundation (3 h)

| Task | Detail |
|---|---|
| Repo + structure | `backend/`, `flutter_app/`, `docker-compose.yml` |
| **Pydantic schemas first** | All tool I/O — this is the contract everything else depends on |
| SQLAlchemy models | From `docs/DATA_MODEL.md`; `create_all()`, skip Alembic |
| FastAPI skeleton | Health check, CORS, `/openapi.json` |
| Docker Compose | `api` + `tts` reachable from phone |
| Seed data | Rules, templates, demo farm, pre-trained CNN weights (EXP-1 allowed) |
| *(Block A fine-tuning)* | ~~Live fine-tune in Colab~~ *(Not needed — EXP-1 confirmed pre-trained assets allowed)* |

**Exit:** phone can `GET /health` over hotspot.

### Block B · 13:00–17:00 — Core tools (4 h)

| Task | Detail |
|---|---|
| `compute_spread` | Directed elevation graph — pure Python, deterministic |
| `get_weather` | DID Sarawak + data.gov.my, **cached fallback** |
| `get_treatment` | Rules lookup, never generative |
| `find_spray_window` | Arithmetic over forecast + `rainfast_hours` |
| `diagnose_leaf` | ONNX endpoint (backend path) |
| Unit tests | Graph acyclicity, edge weights, ETA monotonicity |

**Exit:** all five deterministic tools callable via `/docs` with valid Pydantic responses.

### ⏱ 17:00 GATE — cloud decision point

**Assess:** are Blocks A and B complete and is the agent layer started?

- **Yes, and ahead** → create a `cloud` branch; one member proceeds with Cloud Run + Firebase deploy in parallel. **The `main` branch keeps working locally at all times.**
- **No, or on schedule** → stay local. Ship Docker Compose + public GitHub repo. This is a complete submission.

**Never sacrifice the local path to chase the cloud path.**

---

### Block C · 17:00–21:00 — Agent layer (4 h)

| Task | Detail |
|---|---|
| ADK RootAgent | Instruction from `docs/PROJECT_SPEC.md` §3 L4 |
| Register tools | 5 deterministic + 2 LLM-backed |
| `explain_why`, `draft_alert` | LiteLLM → Ollama |
| SetupCoordinator | LoopAgent, `max_iterations=25` |
| DiagnosisCoordinator | LoopAgent, `max_iterations=30` |
| Advisor | Deterministic verdict + RAG |
| `tools_called` logging | **Never cut — demo evidence** |

**Exit:** arbitration case yields *"drain today, spray Thursday"* with `defer_cause="rainfast"` logged.

### Block D · 21:00–02:00 — Flutter (5 h)

| Task | Detail |
|---|---|
| Project + Riverpod + dio | Generate Dart models from `/openapi.json` |
| Registration + session | |
| **Walk loop** | `geolocator` + `sensors_plus`; tier detection |
| Block capture | Camera, label, voice record |
| Elevation resolution UI | Pairwise water-direction; barometer path |
| Dashboard | Rain pulse · Advisor · Priority action · Terrain canvas |
| Terrain canvas | Blocks by `elevation_rank`, coloured by state, flow arrows |
| Block detail sheet | Photo, voice playback, timeline, treatment log |
| FAB | Diagnosis · Tanya · Tetapan (**hide reset**) |
| Outbox | `sqflite` — pending observations + walk samples |

**Exit:** full setup → diagnosis → recommendation on a real phone.

### Block E · 02:00–05:00 — Speech + integration (3 h)

| Task | Detail |
|---|---|
| **MVP: audio clip playback** | Map `template_id` → bundled `.wav`, play via `just_audio` |
| *(optimised)* MMS-TTS service | Template + slot → seeded VITS → WAV |
| *(optimised)* `audio_cache` | SQL memoisation by hash; **pre-warm before pitch** |
| `flutter_tts` fallback | `ms-MY` |
| On-device TFLite | **Optional** — only if backend path is stable |
| End-to-end rehearsal | Full flow, twice |

**Exit:** app speaks recommendations without perceptible delay.

### Block F · 05:00–08:00 — Harden (3 h)

| Task | Detail |
|---|---|
| Demo script | Rehearse the 5-min structure |
| Offline demo | Kill hotspot → capture → queue → restore → flush |
| Error handling | Every tool fails gracefully |
| Signed release APK | Not debug — avoids install warnings |
| Seed demo farm | Known-good state |
| **Freeze features** | No new work after 08:00 |

### Block G · 08:00–10:00 — Deliverables (2 h)

| Task | Owner |
|---|---|
| Demo video (**record ~hour 18** if stable; polish here) | Abraham → Zoe |
| Landing page (Firebase Hosting if cloud, else Vercel/GH Pages) + APK link | Nathan |
| Pitch deck — Problem 45 s → Solution 60 s → Demo 120 s → Impact 45 s → Future 30 s | Zoe |
| Final rehearsal | All |

---

## Cut order

1. **Cloud deployment → stay local** (first thing to drop)
2. Farmer file upload (Namespace C)
3. `setup_validator` sub-agent → deterministic validation only
4. MMS-TTS → pre-recorded clips → `flutter_tts` BM
5. DEM cross-check
6. On-device TFLite → backend ONNX
7. Outbox → require connectivity
8. Advisor RAG → deterministic verdict only

**Never cut:** spread graph · agent arbitration · `tools_called` logging · CNN diagnosis · walk loop.

---

## Stop rule

If a feature has consumed **45 minutes past its block allocation**, cut to the next cut-order item. Log the decision; do not renegotiate mid-build.

---

## Task allocation

| Owner | Responsibility |
|---|---|
| **Nathan** | Backend, agent, Flutter, model, deployment |
| **Zoe** | Deliverables, submission, pitch deck, video edit, **timekeeping against this plan** |
| **Abraham** | Seed data, rules table, templates, demo video capture, testing |

---

## AICC deliverables

| Deliverable | Approach |
|---|---|
| **Prototype public HTTP** | **Cloud:** live Cloud Run app · **Local fallback:** landing page + demo video |
| **Source code** | Public GitHub repository — **confirmed acceptable by organisers** |
| **Landing page** | Hero · embedded demo video · L0–L4 diagram · terrain insight · APK · repo · proposal |
| **Demo video** | scrcpy capture + voiceover, 2–3 min |
| **Pitch deck** | 5-min structure above |

> **APK depends on which target ships.** Local build points at the laptop LAN IP and is **booth-only** — label it *"requires joining our demo WiFi."* Cloud build points at a public HTTPS endpoint and is **genuinely downloadable and usable by anyone**. Build both; publish whichever is live.
