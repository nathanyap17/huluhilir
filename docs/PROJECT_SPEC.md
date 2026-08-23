# PROJECT_SPEC.md — HuluHilir

> Master reference. `CLAUDE.md` is quick context; this is the detail.
> Schema in `DATA_MODEL.md`. Validation in `VALIDATION_CHECKLIST.md` and `../sandbox/EXPERIMENTS.md`.

---

## 1 · Identity

| | |
|---|---|
| **Name** | HuluHilir — *Upstream Alert* |
| **Tagline** | *Dari hulu ke hilir — sebelum penyakit sampai.* |
| **One line** | Terrain-aware agentic early warning for Phytophthora foot rot in Sarawak black pepper |
| **Competition** | **AI Code Competition 2026 (AICC) — SAIC** |
| **Track** | Track 3 · Agriculture & Rural Livelihoods · Category B (IPTA/IPTS) |
| **Status** | **Finalist** — Grand Finale 23–24 Aug, TDV Kuching |
| **Team** | SMILING FACE WITH SUNGLASSES — Nathan Yap Jia De · Zoe Tan An Xuen · Abraham Pang Exin |

---

## 2 · Problem

- **>30%** of vine mortality and crop loss in *Piper nigrum* attributed to *P. capsici*
- **USD 902/ha** ≈ **56% of annual net returns** at 9.64% vine mortality
- **No resistant cultivars** — management is the only lever
- **36,682** registered pepper farmers; **98% in Sarawak**; Sarawak = **>98%** of national production

### Three compounding failures
1. **Diagnosis arrives late** — by visible symptom the vine is often lost
2. **Farmers see only their own land** — an infection upslope is a scheduled arrival downslope
3. **Treatment timing is guesswork** — contact fungicides wash off; spraying before rain is money into the soil

### The insight
> **Foot rot spreads in rain pulses, not continuously.**
> The question is never *"did we catch it in time?"* but **"what happens at the next rain, and is the farm ready?"**

**Supporting evidence:** drainage management reduced foot rot losses by **24% (USD 439/ha)** — exceeding fungicide's 20%.

### Competitive position
| Existing | Gap |
|---|---|
| Dr.LADA | Rule-based, single-plant, no spatial spread, no timing |
| NutriLada | Records & education, per-farm, not predictive |
| MD AgTech | Not pepper-specific, not terrain-aware, no agent |
| MPB lab | Institutional, post-hoc, not a field tool |

**No product models pathogen transmission across smallholder terrain.**

---

## 3 · Layer specifications

### L0 · Voice & Language — three tiers

The farmer **never types** (except optional short block labels) and **no machine ever needs to understand their speech.**

| Mechanism | Direction | Who understands |
|---|---|---|
| Speech output | System → farmer | The **farmer** listens |
| Voice label | Farmer → storage → farmer | The **farmer** hears their own recording |
| ASR | Farmer → machine | ❌ **Avoided entirely** |

> **A voice label is an audio sticker, not data to be parsed.** The farmer records *"Kebun Tua"*; the app stores the blob and replays it beside the block photo. The machine never needs the words. This is why Iban works despite no Iban ASR existing.

#### Speech output tiers

| Tier | Mechanism | Status |
|---|---|---|
| **MVP** | **Pre-recorded `.wav` clips**, ~25 prompts, mapped by `template_id` | **Committed** — guaranteed to work |
| **OPTIMISED** | **Template + slot → MMS-TTS live synthesis** (seeded, SQL-cached) | Reach goal — pending EXP-2 |
| **Roadmap** | True BM→Iban machine translation + TTS | **Not viable now** — no reliable BM→Iban MT exists |

**Why the roadmap tier is out of reach:** LLMs have negligible Iban in training data and will produce fluent-sounding nonsense. There is no production BM→Iban MT. The template+slot approach is the honest middle ground — **dynamic synthesis of human-verified text.**

**Fallback chain:** MMS Iban → MMS BM → pre-recorded clip → `flutter_tts` `ms-MY` → text only.

**MMS deployment notes** (if OPTIMISED reached): lowercase and strip punctuation before tokenising; **seed the VITS model** (it is stochastic); ~145 MB PyTorch per language → separate `tts` container, weights as volume; cache by `sha256(template_id + slots + lang + seed)`.

### L1 · CNN Diagnosis

| Item | Decision |
|---|---|
| Task | Image **classification** (not detection — no bounding boxes) |
| Backbone | MobileNetV3-Small, ImageNet pretrained |
| Classes | `healthy_leaf` · `healthy_collar` · `foliar_yellowing` · `collar_lesion` · `defoliation_wilt` · `unrelated` |
| Input | 224×224 RGB |
| Split | Stratified 70/15/15 — **split BEFORE augmentation** |
| Augmentation | Train split only: rotation ±25°, h-flip, brightness ±20%, zoom ±15% |
| Training | Colab T4, target <20 min |
| Export | **Both** `.tflite` and `.onnx` |
| Threshold | `confidence < 0.60` → advise physical inspection |

| Class | Malay | Meaning | Agent implication |
|---|---|---|---|
| `healthy_leaf` | SIHAT (DAUN) | Confirms leaf checked, clear | No action |
| `healthy_collar` | SIHAT (PANGKAL) | Confirms collar checked, clear | No action |
| `collar_lesion` | LESI PANGKAL | **Decisive, earliest** | → Harmed, urgent |
| `foliar_yellowing` | DAUN MENGUNING | Lagging, non-specific | Context decides |
| `defoliation_wilt` | GUGUR DAUN / LAYU | Advanced | Vine likely lost → triage |
| `unrelated` | TIADA KAITAN | Not a plant subject | Retake prompt, not recorded as a check |

**Why six, not four.** `healthy` alone could not tell the difference between "the collar is fine" and "the farmer photographed a leaf while meaning to check the collar" — both returned the same class. Splitting by body part turns the model's prediction into a cross-check against `capture_target`, closing that gap. `unrelated` stops the model confidently mislabelling obvious non-plant photos as a health class.

**Evaluation:** per-class recall (**headline**, priority on `collar_lesion`) · confusion matrix · precision/F1 per class · accuracy (last) · confidence distribution.

> *"We optimise for recall on collar lesion — a false negative costs a vine, a false positive costs one inspection walk."*

### L2 · Spread Model

**Deterministic directed graph. NOT machine learning.** No labelled transmission-timing dataset exists.

```
IN:  source_block, farm_graph{nodes, edges}, rainfall_7d, forecast_7d
OUT: [{block_id, risk 0–1, risk_band, eta_days, path[], confidence}]

for each block reachable downhill from source:
    path         = shortest downhill path (edge weights)
    cumulative_w = Π flow_weight along path
    rain_factor  = f(rainfall_7d, forecast_7d)      # pulses
    risk         = cumulative_w × rain_factor × severity(source_class)
    eta_days     = base_transit(path_length) ÷ rain_intensity
    confidence   = g(elevation_tier, gps_accuracy, farmer_confirmed)
```

**Where the machine advantage lies:** *combinatorial computation*, not pattern discovery. A farmer knows water runs downhill; they cannot hold six blocks × water paths × 7-day forecast × 3 treatments × rain-fast windows simultaneously.

**Roadmap:** logged observations become the first dataset capable of calibrating edge weights against observed arrival times.

### L3 · Knowledge

```
NAMESPACE A · authoritative → JSON rules table (dose, product, rain-fast)  [MPB/DOA only]
NAMESPACE B · advisory      → MPB/DOA guidance docs                        [retrieval]
NAMESPACE C · local         → farmer uploads                               [retrieval, attributed]
```

**Rules table decides *what*. Retrieval explains *why*. Never the reverse.**
MVP: JSON file + in-memory similarity over ~40 chunks. No vector database.

### L4 · Agent

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

> **Precision with judges:** *"The root agent arbitrates between five deterministic tools and two LLM-backed generation tools. Setup and diagnosis coordination run as sub-agents with their own tools and reasoning loops."* `explain_why` and `draft_alert` are **tools, not agents** — do not call them multi-agent.

#### Root agent instruction

```
You coordinate pepper disease management for one farm.

SEQUENCE
1. If setup incomplete → delegate to setup_coordinator. Stop.
2. On new diagnosis cycle → get_weather, then compute_spread ONCE after all
   blocks are captured (not per block — partial projection causes flapping).
3. If any block risk >= threshold → get_treatment, then find_spray_window.
4. ARBITRATE:
   - Weigh diagnosis urgency vs treatment rainfast_hours vs forecast vs spread ETA
   - If rain falls inside the rain-fast window → DEFER the spray,
     log defer_cause="rainfast", and sequence drainage work FIRST
   - Order actions by sequence; drainage before spraying when water
     movement is the dominant risk
5. Produce exactly ONE recommendation per block: action + time + one reason.
6. If a downslope block belongs to another farmer → draft_alert (never send).

CONSTRAINTS
- Never output a treatment absent from get_treatment results.
- Never invent doses, timings, or product names.
- Always call explain_why to render the reason in plain Bahasa Malaysia.
- Log every deferral with its cause.
```

#### The arbitration — core demo moment
> L1: *treat now* · L3: *24 h rain-fast* · Weather: *46 mm tomorrow* · L2: *downslope risk in 4 days*
> → **"Clear the drain today. Spray Thursday morning."**

---

## 4 · Two-tier elevation capture

Detection is **automatic and silent**.

| | **MINIMAL** (default) | **OPTIMISED** (barometer) |
|---|---|---|
| Trigger | No pressure sensor | Pressure sensor readable |
| Elevation source | Farmer water-direction answers only | Barometric ranking, farmer-confirmed on ambiguity |
| Pairwise questions | All adjacent pairs (n−1) | Only where Δh < 2.0 m |
| Slope | Categorical (farmer taps) | Continuous (Δh ÷ distance) |
| `confidence` | 0.55 – 0.75 | 0.75 – 0.95 |
| Setup time | ~4–6 min | ~2–3 min |
| Functionality lost | **None** | — |

**Both tiers capture GPS position** — only *altitude* differs.

**Three invariants:** farmer answer always wins on conflict · same schema and code path downstream · `elevation_tier` stored so risk outputs trace to input quality.

> *"The system works fully on a RM400 phone; a barometer only makes setup faster."*

---

## 5 · Setup flow

```
① Register + session
② GPS permission → locate → bind rainfall station
③ Device probe → barometer? → set elevation_tier          [silent]
④ BLOCK CAPTURE LOOP  ←──────────┐
     walk to block                │
     tap → capture position       │
     + photo + label + voice      │
     [OPTIMISED: pressure sampled continuously]
     more blocks? ────────────────┘
⑤ ELEVATION RESOLUTION            ← only possible after ④ completes
     MINIMAL   → pairwise water-direction, all adjacent pairs
     OPTIMISED → barometer ranking; ask only where Δh < 2.0 m
⑥ DRAINAGE per block (two-photo tap)
⑦ Optional neighbour contacts
⑧ setup_validator → coherence check → escalate or re-prompt
```

### Graph derivation

```
① POSITION   centroid = median(lat, lon in ±5 s window)   # median rejects jitter

② ELEVATION  [OPTIMISED] baro_rel = baro_alt − baseline
             rank = sort by baro_rel desc

③ GATE       Δh >= 2.0 m  → accept sensor
             Δh <  2.0 m  → ASK farmer
             MINIMAL      → ASK all pairs
             # farmer ALWAYS overrides; conflict logged

④ EDGES      horizontal_dist = haversine(i, j)
             slope           = Δh / horizontal_dist
             candidates      = k-NN (k=3) on 2D position
             keep i→j iff rank_i < rank_j        # acyclic
             flow_weight = w1·norm(slope) + w2·(1/dist) + w3·drainage(j)

⑤ DEM CHECK  query SRTM; if contradicts barometer AND farmer → flag
             # NEVER auto-override
```

---

## 6 · Diagnosis cycle

**Diagnosis is an event, not a habit.** It covers all blocks and produces one coherent farm-wide picture — matching how a farmer inspects after heavy rain.

```
DiagnosisCoordinator (LoopAgent, max_iterations=30)
  ├── CaptureChecker    → which blocks still lack an image this cycle?
  ├── CapturePrompter   → speak next block, wait for photo
  ├── ClassifyStep      → diagnose_leaf per new image
  ├── ProjectStep       → compute_spread ONCE after capture completes
  ├── TreatmentStep     → get_treatment + find_spray_window
  └── ArbitrateStep     → root produces one action per block
  exit: escalate() when all blocks captured OR user aborts
```

**Cycles are resumable.** `status: in_progress` survives app close; UI offers *"Sambung diagnosis (4/6 blok)"*.

### Multi-sample capture (optional, additive)

One photo per block remains the default and the minimum requirement of `CaptureChecker` above. Optionally, a farmer may submit **2–4 photos for a single block** in one cycle — different leaves or vines within that block — rather than exactly one. `ClassifyStep` runs `diagnose_leaf` independently on each; no change to the model or its contract. The block's resulting state is derived by **worst-class-wins**: any photo returning `collar_lesion` or `defoliation_wilt` sets the block to Harmed regardless of how many other sampled photos were healthy. This mirrors the presence-over-prevalence reasoning already applied to the block-state machine — see `docs/L1_MODEL_ROADMAP.md` §1 and §7.4 for the full rationale and aggregation logic.

### Advisor

Answers *"when should I diagnose?"* — and, more often, *"why not yet."*

```python
def should_diagnose(farm) -> AdvisorVerdict:
    rain_48h   = sum(rainfall, last 48h)
    days_since = now - last_completed_cycle.completed_at

    if rain_48h >= 30 and days_since >= 3:
        return HIGH,   "heavy_rain_recent"     # 3-day floor = incubation
    if any(block.state in (ALERTED, HARMED)) and days_since >= 5:
        return HIGH,   "active_infection"
    if blocks_all_protected and rain_since_last < 20 and days_since < 14:
        return LOW,    "protected_stable"      # evidence-backed "no action"
    if days_since >= 21:
        return MEDIUM, "stale"
    return NONE, "no_action_needed"
```

**The 3-day floor matters:** symptoms need incubation. Diagnosing the morning after a downpour finds nothing.

**The Advisor recommends; it never blocks.** Compute on backend at request time (`GET /farm/{id}/advisor`) — **do not build background polling.**

---

## 7 · Dashboard

`GET /farm/{farm_id}/dashboard → DashboardResponse`

```
┌─────────────────────────────────────┐
│ ☂ RAIN PULSE                        │  always present — works with 0 photos
│   Rabu · 46 mm · 2 hari lagi   ▶🔊  │
├─────────────────────────────────────┤
│ ⚠ ADVISOR                           │  conditional
│   "Hujan lebat 3 hari lalu.         │
│    Masa untuk diagnosis."     [MULA]│
├─────────────────────────────────────┤
│ ▶ TINDAKAN UTAMA                    │  actions[0] only — the arbitration
│   Buka parit Blok 4 hari ini        │
│   Sembur Khamis pagi.          ▶🔊  │
│   ↳ ditangguh: hujan Rabu           │
├─────────────────────────────────────┤
│      TERRAIN RISK MODEL             │  signature visual
│      blocks by elevation_rank       │
│      coloured by state + flow edges │
├─────────────────────────────────────┤
│ 📨 2 pesanan jiran menunggu    [>]  │  consent gate
└─────────────────────────────────────┘
                              ( ✦ )     FAB
```

**FAB:** 📷 Diagnosis · 💬 Tanya (RAG) · ⚙ Tetapan. **Reset hidden** behind long-press.

**Block detail sheet:** photo · voice label playback · state badge · timeline with rainfall overlay · diagnosis history · treatment log with *"hujan dalam tempoh tahan hujan · terbazir"* flag · current recommendation.

**Two UI rules:** every string has a `speech_template_id`; every risk number carries `is_estimate`.

**On app open mid-cycle:** land on the dashboard with a **resume prompt** — never drop straight into capture.

---

## 8 · Deployment — two targets, one codebase

**LOCAL is the committed baseline. CLOUD is a stretch goal gated at 17:00 on 23 Aug.**

```
LOCAL                                    CLOUD (stretch)
─────────────────────────────            ─────────────────────────────
PHONE (Flutter APK)                      PHONE (Flutter APK)
  · TFLite CNN / backend ONNX              · same build, different base URL
  · sqflite outbox                         · sqflite outbox
        │ own hotspot                            │ public HTTPS
LAPTOP (docker compose up)               GOOGLE CLOUD
  · api  :8000  FastAPI · ADK · tools       · Cloud Run — same container
  · SQLite file                             · SQLite in image → Cloud SQL
  · ollama :11434 native                    · Gemini API via LiteLLM
                                            · Firebase Hosting — landing page
                                            · Firebase Storage — .wav, photos, APK
```

**Switching is configuration only.** Three environment variables — `API_BASE_URL`, `LITELLM_MODEL`, `DATABASE_URL`. No application code branches on deployment target. That property is what makes the cloud path safe to attempt late.

| | LOCAL | CLOUD |
|---|---|---|
| Backend | Docker Compose on laptop | Cloud Run, scales to zero |
| Language model | Ollama, open-weight, offline | Gemini API through LiteLLM |
| Database | SQLite file | SQLite in image → Cloud SQL (~USD 7/mo) |
| Speech | Pre-rendered `.wav`, bundled | Pre-rendered `.wav` on Firebase Storage |
| Reached by | Phone on team hotspot | Public HTTPS — any device |
| Depends on | Nothing external | Venue connectivity |

**Why both are kept.** The local stack has no external dependency and cannot fail because of venue networking — it is the guaranteed demonstration path. The cloud deployment removes the laptop from the story: the landing page becomes a genuinely public prototype and the APK works for a judge testing from their own office. Keeping both is not indecision; it is the difference between a demo that always works and a product anyone can try.

**Cloud notes**
- `min-instances = 1` during judging avoids ONNX cold start; set to 0 when idle.
- Speech is **pre-rendered to static audio** — no TTS server in the request path, container stays small.
- SQLite is bundled in the image and reseeded on redeploy; migrate to Cloud SQL only if persistence across deploys is needed.
- Runs inside existing GCP credit. No paid API on the critical path.

**Docker caveats:** pre-pull base images · torch only in the `tts` container · weights as volumes · bind `0.0.0.0` · open Windows firewall for 8000/8001/11434.

### AICC deliverables

| Deliverable | Approach |
|---|---|
| **Prototype public HTTP** | **Cloud:** the live application · **Local fallback:** landing page with embedded demo video |
| **Source code** | **Public GitHub repository — confirmed acceptable by organisers** |
| **Landing page** | Hero · demo video · L0–L4 diagram · terrain insight · APK · repo · proposal |
| **Demo video** | scrcpy capture + voiceover, 2–3 min. **Record ~hour 18, not hour 23** |
| **Pitch deck** | Problem 45 s → Solution 60 s → Demo 120 s → Impact 45 s → Future 30 s |

**APK depends on which target ships.** The local build points at a LAN IP and is booth-only — label it *"requires joining our demo WiFi."* The cloud build points at public HTTPS and is genuinely downloadable. **Build both; publish whichever is live.**

**No web build of the app.** Flutter Web cannot access the barometer reliably and has coarser GPS — it would break the setup flow that justifies Flutter.

**Demo setup:** projector shows scrcpy (live phone) **beside** a live `tools_called` log. Visible orchestration beats described orchestration.
