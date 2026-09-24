# PROJECT_SPEC.md — PepperDex (formerly HuluHilir)

> ⚠️ **MIGRATION STATUS — READ THIS FIRST**
> A previous development session already built and validated a working v1 system: Flutter frontend, single-agent backend, AICC competition target. That build is **done and real** — the backend logic described below (spread graph, rules engine, CNN pipeline, agent arbitration) was tested and works. **This is not a spec for a system that doesn't exist yet.**
>
> This document has since been updated in place for **v2**: a full frontend rebuild (Flutter → React Native) plus six scoped backend extensions, for a new competition (AgroHack 2026, not AICC). Sections marked **🔄 v2** were changed or added after the v1 build; everything else is the original, still-working v1 design. **Your job on this system is to realise the v2 changes on top of the existing v1 logic — not to rebuild from a blank slate, and not to leave v2 half-applied.**
>
> Full component-level frontend detail lives in **§9** (new in v2 — v1 had no RN component catalogue to merge from).

---

## 1 · Identity

| | |
|---|---|
| **Name** | **PepperDex** *(formerly HuluHilir — 🔄 v2 rename, same project, same functions)* |
| **Tagline** | *Dari hulu ke hilir — sebelum penyakit sampai.* (kept — describes the mechanism, not the old name) |
| **One line** | Terrain-aware agentic disease diagnosis and management for Phytophthora foot rot in Sarawak black pepper |
| **Competition** | 🔄 v2: **AgroHack 2026 @ Sarawak AgroFest** — Sibu Town Square, 25–27 Sept 2026. *(v1 targeted AICC/SAIC — that build's constraints, e.g. the 24h live-build rule, do not apply here.)* |
| **Frontend** | 🔄 v2: **React Native (Expo)** — Android APK. *(v1 was Flutter — see §9 for why this was a full rebuild, not a refactor.)* |
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

### L0 · Voice & Language — three tiers (unchanged in v2)

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

**Fallback chain:** MMS Iban → MMS BM → pre-recorded clip → device TTS `ms-MY` → text only.

🔄 v2 note: on RN, device TTS fallback is `expo-speech` (was `flutter_tts` in v1). Voice recording is `expo-av`/`expo-audio` (was `record`). No logic change — library swap only.

### L1 · CNN Diagnosis

| Item | Decision |
|---|---|
| Task | Image **classification** (not detection — no bounding boxes) |
| Backbone | MobileNetV3-Small, ImageNet pretrained |
| Classes | `healthy_leaf` · `healthy_collar` · `foliar_yellowing` · `collar_lesion` · `defoliation_wilt` · `unrelated` |
| Input | 224×224 RGB |
| Split | Stratified 70/15/15 — **split BEFORE augmentation** |
| Export | `.tflite` and `.onnx`, both — see inference path below |
| Threshold | `confidence < 0.60` → advise physical inspection |

**🔄 v2 — inference path corrected.** v1 briefly used Gemini Vision as a production workaround for a label-order bug (fixed — see `PLAN.md` §3). **`.onnx` backend inference is now the confirmed sole primary path. Gemini Vision is removed entirely, not demoted.** A cloud fallback on the diagnosis path contradicts this project's offline-tolerant / no-paid-API claims regardless of where it sits in a fallback chain.

```python
def diagnose_leaf(image, capture_target) -> DiagnoseResponse:
    try:
        result = onnx_session.run(preprocess(image))
    except (ModelLoadError, InferenceError):
        return DiagnoseResponse(below_threshold=True,
                                 advice="Sila periksa secara fizikal.")  # SAME path as low confidence
    # No Gemini Vision branch. Removed, not demoted.
```

**Mandatory regression test, tied to a real v1 incident:** an automated check confirming `labels.txt` order matches the training config exactly, run before every deploy — this exact bug already caused a silent misclassification once.

| Class | Malay | Meaning | Agent implication |
|---|---|---|---|
| `healthy_leaf` | SIHAT (DAUN) | Confirms leaf checked, clear | No action |
| `healthy_collar` | SIHAT (PANGKAL) | Confirms collar checked, clear | No action |
| `collar_lesion` | LESI PANGKAL | **Decisive, earliest** | → Harmed, urgent |
| `foliar_yellowing` | DAUN MENGUNING | Lagging, non-specific | Context decides |
| `defoliation_wilt` | GUGUR DAUN / LAYU | Advanced | Vine likely lost → triage |
| `unrelated` | TIADA KAITAN | Not a plant subject | Retake prompt, not recorded as a check |

**Why six, not four.** `healthy` alone could not tell the difference between "the collar is fine" and "the farmer photographed a leaf while meaning to check the collar." Splitting by body part turns the model's prediction into a cross-check against `capture_target`.

**Evaluation:** per-class recall (**headline**, priority on `collar_lesion`) · confusion matrix · precision/F1 per class · accuracy (last).

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

**Where the machine advantage lies:** *combinatorial computation*, not pattern discovery.

**Roadmap:** logged observations become the first dataset capable of calibrating edge weights against observed arrival times.

#### 🔄 v2 — Terrain canvas layout (3D, not 2D — correcting an earlier oversimplification)

**This was previously specified as a flat 2D canvas. That was wrong — it silently dropped a real requirement.** 3D terrain rendering was one of the two concrete reasons React Native was chosen over Flutter in the first place (`@react-three/fiber` + `expo-gl` — native GPU 3D, versus Flutter's WebView-wrapped workaround). A 2D canvas was designed at one point in this project's history for a legitimate reason (NCR land-boundary safety), but that reasoning does not actually require flatness — it requires *no literal georeferenced survey*, which is a different constraint and is fully compatible with 3D.

**The resolution: a stylised 3D scene built from the same relative, proportional data — not a literal terrain reconstruction.** This is not a full topographic mesh derived from dense elevation data (which doesn't exist — only a handful of per-block GPS+barometer points are ever collected, nowhere near enough to reconstruct an accurate continuous surface). It is the *same* `x_rot_m`/`y_rot_m` graph, rendered with a third (height) axis derived from `elevation_rank`/`baro_rel_m`, giving genuine depth and motion — blocks as raised nodes on a gently inclined stylised plane, water-flow edges rendered as flowing 3D paths between them.

```
STEP 1 — Flat-earth local projection (valid at farm scale, ~1–3°N in Sarawak)
    origin = centroid of all block (lat, lon)
    x_m = (lon − origin.lon) × 111320 × cos(origin.lat in radians)
    y_m = (lat − origin.lat) × 111320

STEP 2 — Rotate so upslope → downslope points into the scene consistently
    flow_vector = mean(to.pos_m − from.pos_m) across all flow_edges
    θ = angle to align flow_vector with the scene's "into the distance" axis
    apply rotation R(θ) to every (x_m, y_m) → (x_rot_m, y_rot_m)
    # rotation is an isometry — all real relative distances are preserved
    # WHY: raw lat/lon plotted directly would often break the "hulu at top"
    # convention for a farm not oriented north-south — this fixes that,
    # in 3D exactly as it did in the earlier flat-canvas design.

STEP 3 — Height axis (NEW — this is what makes it 3D, not a cosmetic change)
    z_rot = normalise(elevation_rank OR baro_rel_m) × HEIGHT_SCALE
    # a relative height for VISUAL depth, not a survey-accurate elevation.
    # HEIGHT_SCALE is a stylistic constant, tuned for legibility, not accuracy.

STEP 4 — Adaptive scale — CLIENT-SIDE, not backend, not a fixed constant
    Same principle as before, now scaling all three axes together so the
    scene fits the viewport and camera framing chosen by the frontend.

STEP 5 — Render: blocks as raised 3D nodes, flow edges as flowing 3D paths,
    a simple stylised ground plane beneath (not a literal terrain mesh)
```

**Guardrails — unchanged in substance, restated for the 3D context:**
1. **No absolute lat/lon, no compass rose, no north indicator** rendered anywhere in the scene — nothing that makes it readable as a survey document, in 2D or 3D.
2. **No filled parcel polygon, no accurate terrain mesh derived from dense elevation data.** The ground plane is a stylised visual base, not a claim about the farm's actual topography.
3. **Never exported in a geo-referenced format.** This stays a private, proportional, on-device scene — a *stylised* 3D representation of relative positions, never a portable map.

**Split of responsibility, updated for 3D:** backend computes `x_rot_m`/`y_rot_m`/height input (deterministic, device-independent, derived at response time — not persisted). Frontend owns the actual 3D scene — camera position, lighting, adaptive scale-to-viewport, and rendering via `@react-three/fiber` + `expo-gl`. See §9.6 for the component-level detail.

### L3 · Knowledge

```
NAMESPACE A · authoritative → JSON rules table (dose, product, rain-fast)  [MPB/DOA only]
NAMESPACE B · advisory      → MPB/DOA guidance docs                        [retrieval]
NAMESPACE C · local         → farmer uploads                               [retrieval, attributed]
```

**Rules table decides *what*. Retrieval explains *why*. Never the reverse.**

#### 🔄 v2 — Retrieval split by data shape

| Data | Path |
|---|---|
| `knowledge_docs` (Namespace B/C) | **Hybrid**: vector similarity + SQLite FTS5 full-text |
| Historical diagnoses / risk assessments / recommendations | **New tool** `query_farm_history(farm_id, filters)` — direct SQL, never embedded as text |

**Why not force both into one vector store:** structured data loses its structure the moment it's flattened for embedding. A tool call over real rows is more reliable than hoping semantic search retrieves the right number.

### L4 · Agent

```
RootAgent (LlmAgent) — router + arbitrator
├── FunctionTools (deterministic)
│     diagnose_leaf (.onnx only) · get_weather · compute_spread (+rotation)
│     get_treatment · find_spray_window · query_farm_history 🔄
├── FunctionTools (LLM-backed)
│     explain_why · draft_alert · draft_calendar_sync 🔄
├── AgentTool → SetupCoordinator      (LoopAgent, max_iterations=25)
├── AgentTool → DiagnosisCoordinator  (LoopAgent, max_iterations=30)
├── AgentTool → Advisor               (LlmAgent + hybrid RAG, non-loop)
└── AgentTool → OverrunCouncil 🔄      (ADK-native sub_agents — NOT the A2A protocol)
      ├── AgronomicUrgencyAgent · CostFeasibilityAgent · LogisticsAgent
      └── CouncilOrchestrator — ranks only, dose-less response schema
```

> **Precision with judges:** the root agent arbitrates between deterministic tools and LLM-backed generation tools. `explain_why`, `draft_alert`, `draft_calendar_sync` are **tools, not agents**. The genuine multi-agent claim rests on the sub-agents — Setup, Diagnosis, Advisor, and (v2) the Overrun Council — each with its own instruction, tools, and termination condition.

**🔄 v2 — the Overrun Council.** Fires **only** when `farm_state == 'overrun'` **and** more than one block is simultaneously `Harmed`. It is not part of a normal diagnosis. **Structural treatment-identity wall:** its response schema has no field capable of holding a dose, product, or timing —

```python
class TriageRanking(BaseModel):
    block_id: str
    rank: int
    rationale_ms: str
    # no treatment_id, dose_text, or recommended_at field — enforced by
    # the schema, not by convention. An agent hallucinating a dose has
    # nowhere in this type to put it.
```

The council may re-order which already-approved action happens first. It never decides what those actions are — `get_treatment` and `find_spray_window` remain the only source of that. Every debate is logged to `council_debates`.

**On A2A:** not needed. All four agents live inside one ADK process; native `sub_agents`/`AgentTool` composition with shared session state handles this. A2A solves cross-process/cross-vendor agent interop, which nothing here requires.

**🔄 v2 — MCP calendar integration.** `draft_calendar_sync` converts scheduled actions into calendar-shaped text. Same consent pattern as `draft_alert`: draft → farmer approves → sync. Never automatic. Provider scope for v2: Google Calendar via the Google Calendar MCP Server (with direct Google Calendar API as a fallback). Native device calendar integration via Expo's calendar API has been explicitly removed.

#### RootAgent instruction — full text (🔄 v2 supersedes v1 wholesale)

**This replaces the v1 prompt; it is not layered alongside it.** Only steps 3a and 7 are new — everything else is byte-identical to the working v1 instruction.

```
You coordinate pepper disease management for one farm.

SEQUENCE
1. If setup incomplete → delegate to setup_coordinator. Stop.
2. On new diagnosis cycle → get_weather, then compute_spread ONCE after all
   blocks are captured (not per block — partial projection causes flapping).
3. If any block risk >= threshold → get_treatment, then find_spray_window.
3a. If farm_state == 'overrun' AND more than one block is simultaneously
    Harmed → delegate to overrun_council for a triage ranking BEFORE
    arbitrating. The council may only re-order which already-approved
    action happens first; it never invents a treatment, dose, or timing —
    its response schema has no field capable of holding one.
4. ARBITRATE:
   - Weigh diagnosis urgency vs treatment rainfast_hours vs forecast vs spread ETA
   - If the council produced a ranking, follow its block order when sequencing
   - If rain falls inside the rain-fast window → DEFER the spray,
     log defer_cause="rainfast", and sequence drainage work FIRST
   - Order actions by sequence; drainage before spraying when water
     movement is the dominant risk
5. Produce exactly ONE recommendation per block: action + time + one reason.
6. If a downslope block belongs to another farmer → draft_alert (never send).
7. If any recommendation carries a schedulable date → draft_calendar_sync,
   and surface it to the farmer for consent. Never sync without approval.

CONSTRAINTS
- Never output a treatment absent from get_treatment results.
- Never invent doses, timings, or product names.
- overrun_council may re-rank blocks; it may never supply a treatment, dose,
  or timing — enforced by its response schema, not by this instruction alone.
- Always call explain_why to render the reason in plain Bahasa Malaysia.
- Log every deferral with its cause.
```

#### The arbitration — core demo moment (unchanged, still the best line)
> L1: *treat now* · L3: *24 h rain-fast* · Weather: *46 mm tomorrow* · L2: *downslope risk in 4 days*
> → **"Clear the drain today. Spray Thursday morning."**

#### Block state model — the precedence rule connecting L2's projection to what the farmer sees

**This was previously undocumented** despite being load-bearing: nothing before this stated who updates `blocks.current_state`, or which source wins when a direct diagnosis and an L2 spread projection disagree about the same block.

| State | Set by | Trigger |
|---|---|---|
| `protected` | Default | No confirmed case in the catchment, no elevated projected risk |
| `alerted` | **L2 projection only — no diagnosis required** | `compute_spread` returns an elevated `risk_band` for this block from a confirmed case upslope |
| `harmed` | **Direct diagnosis only** | `diagnose_leaf` returns `collar_lesion` or `defoliation_wilt` for *this* block |
| `overrun` | Derived, farm-wide | More than one block simultaneously `harmed` |

**Precedence rule, evaluated on every agent run that touches a block:**
1. **A direct diagnosis on a block always overrides any projected state for that same block.** Diagnosis is ground truth; projection is an estimate.
2. **A block may be projected UP (`protected` → `alerted`) with zero photographs of that block.** This is the concrete mechanism behind rule 6 (the app must work with zero photographs) — the projection alone is sufficient to alert a farmer to a downslope risk before they've ever pointed a camera at it.
3. **A block's state is never silently downgraded by an improving projection alone.** If B is `alerted` and the upstream risk later subsides (upslope block treated, no further rain), B **stays** `alerted` until a direct diagnosis confirms `healthy_leaf`/`healthy_collar` on B itself. This avoids flickering a farmer's block status based on noisy week-to-week projections — trust in the state display depends on it only ever moving on real evidence.
4. **Every transition writes `state_changed_at` and is shown on the dashboard as an explicit change**, never silently absorbed into a refreshed view.

> 🟡 **Open — time-based decay.** No rule yet exists for whether an `alerted` state should ever auto-clear after enough time passes with no confirming diagnosis (e.g., "alerted 30 days ago, never confirmed, revert to protected"). Left unspecified deliberately rather than guessed — resolve before it matters in practice, not by default behaviour discovered during a demo.

---

## 4 · Two-tier elevation capture (unchanged logic — 🔄 v2 only swaps the sensor library)

Detection is **automatic and silent**.

| | **MINIMAL** (default) | **OPTIMISED** (barometer) |
|---|---|---|
| Trigger | No pressure sensor | Pressure sensor readable |
| Elevation source | Farmer water-direction answers only | Barometric ranking, farmer-confirmed on ambiguity |
| Pairwise questions | All adjacent pairs (n−1) | Only where Δh < 2.0 m |
| `confidence` | 0.55 – 0.75 | 0.75 – 0.95 |
| Functionality lost | **None** | — |

**Three invariants:** farmer answer always wins on conflict · same schema and code path downstream · `elevation_tier` stored so risk outputs trace to input quality.

> *"The system works fully on a RM400 phone; a barometer only makes setup faster."*

🔄 v2: barometer access is `expo-sensors` (was `sensors_plus`). GPS is `expo-location` (was `geolocator`). **This is why React Native was chosen over Flutter — see §9.** No change to the tier logic, thresholds, or invariants above.

---

## 5 · Setup flow (unchanged)

```
① Register + session
② GPS permission → locate → bind rainfall station
③ Device probe → barometer? → set elevation_tier          [silent]
④ BLOCK CAPTURE LOOP (walk → tap → photo + label + voice) → more blocks?
⑤ ELEVATION RESOLUTION → only possible after ④ completes
⑥ DRAINAGE per block (two-photo tap)
⑦ Optional neighbour contacts
⑧ setup_validator → coherence check → escalate or re-prompt
```

### Graph derivation
```
① POSITION   centroid = median(lat, lon in ±5 s window)
② ELEVATION  [OPTIMISED] baro_rel = baro_alt − baseline; rank = sort desc
③ GATE       Δh >= 2.0 m → accept sensor; Δh < 2.0 m → ASK farmer; MINIMAL → ASK all
④ EDGES      k-NN (k=3); keep i→j iff rank_i < rank_j (acyclic); flow_weight = f(slope, dist, drainage)
⑤ DEM CHECK  query SRTM; flag on contradiction; NEVER auto-override
```

---

## 6 · Diagnosis cycle

**Diagnosis is an event, not a habit.** It covers all blocks and produces one coherent farm-wide picture.

```
DiagnosisCoordinator (LoopAgent, max_iterations=30)
  ├── CaptureChecker → CapturePrompter → ClassifyStep → ProjectStep (once) → TreatmentStep → ArbitrateStep
  exit: escalate() when all blocks captured OR user aborts
```

**Cycles are resumable.** `status: in_progress` survives app close.

**Multi-sample capture (additive):** 2–4 photos per block, worst-class-wins aggregation, `unrelated` excluded from the count rather than treated as evidence either way.

**🔄 v2 — hard routing rule.** Every `/diagnose` command, from any entry point (Advisor chat or Farm block detail), passes through `Advisor.evaluate()` first. This was implicit in v1's "recommends, never blocks" principle; v2 makes it a routing rule so no screen can call `DiagnosisCoordinator` directly and skip it.

### Advisor

```python
def should_diagnose(farm) -> AdvisorVerdict:
    rain_48h   = sum(rainfall, last 48h)
    days_since = now - last_completed_cycle.completed_at
    if rain_48h >= 30 and days_since >= 3:            return HIGH,   "heavy_rain_recent"
    if any(block.state in (ALERTED, HARMED)) and days_since >= 5: return HIGH, "active_infection"
    if blocks_all_protected and rain_since_last < 20 and days_since < 14: return LOW, "protected_stable"
    if days_since >= 21:                              return MEDIUM, "stale"
    return NONE, "no_action_needed"
```

**The Advisor recommends; it never blocks.** The "Begin Diagnosis" path is always available regardless of verdict — this is non-negotiable, not a UI nicety.

---

## 7 · Non-negotiables

Full list with code-level enforcement in `.claude/skills/pepperdex-rules/SKILL.md` (13 rules). Summary:

1–8 unchanged from v1: no ASR · rules-table-only dosing · farmer-overrides-sensor · no land boundaries · consent-gated alerts · works with zero photos · everything speakable · `is_estimate` on every risk number.

**🔄 v2 additions:**
12. The Overrun Council may re-rank; it may never generate a treatment, dose, or timing.
13. Calendar sync is drafted and consent-gated, never automatic.

---

## 8 · Deployment

**🔄 v2 — cloud is a first-class target, not a gated stretch goal.** v1 gated cloud behind a "17:00 on build-day" hackathon clock, because AICC's live-build rule created real time pressure. AgroHack's build-before-exhibition rule removes that pressure entirely — there is no reason to still treat cloud deployment nervously.

```
LOCAL                                    CLOUD
PHONE (RN APK)                           PHONE (RN APK, different base URL)
        │ own hotspot / any network             │ public HTTPS
LAPTOP (docker compose up)               GOOGLE CLOUD
  · api :8000 FastAPI · ADK · tools        · Cloud Run — same container
  · SQLite file                            · SQLite in image → Cloud SQL
  · ollama :11434 native                   · Gemini API via LiteLLM
                                           · Firebase Hosting/Storage
```

**Switching is configuration only** — `API_BASE_URL`, `LITELLM_MODEL`, `DATABASE_URL`. No application code branches on target.

**Cloud notes:** `min-instances = 1` avoids ONNX cold start during demos, `0` when idle. Speech is pre-rendered static audio — no TTS server in the request path. No paid API on the critical path.

### AgroHack deliverables (🔄 v2 — replaces v1's AICC-specific list)

| Deliverable | Note |
|---|---|
| Product / Prototype | Pre-built is expected — no live-build constraint |
| Source code | Public GitHub repository |
| Bunting (80×200cm) | New physical asset — see `DESIGN_BUNTING-v2.md` |
| Presentation Slides | See `DECK.md` |
| Demo Video | Record once stable, don't wait until the last hour |
| Poster A3 | Re-scoped for AgroHack, not the AICC one reused blind |

---

## 9 · Frontend Components (React Native)

> **This section was previously compressed to one-line summaries per component — that lost real, load-bearing detail (field names, types, sources) a coding agent needs to implement against directly rather than re-deriving from a diagram. Restored to full detail below.**

### 9.0 · Navigation Shell

```
RootNavigator
├── SetupWizardStack        ← rendered INSTEAD OF tabs while setup_completed_at is null
│   └── 9.9 → 9.10 → 9.11 → 9.12 → 9.13
└── TabNavigator             ← rendered once setup is complete
    ├── HomeStack     → 9.1, 9.2, 9.3, 9.14, 9.15
    ├── AdvisorStack  → 9.4, 9.5
    └── FarmStack     → 9.6, 9.7, 9.8
```

**Channeling rule:** the root navigator checks `setup_completed_at` on every cold start. This is a hard gate — the tab shell must be structurally unreachable until setup finishes, not just hidden behind a prompt.

**Header (owner preference, 2026-09-19):** every tab screen shows the **PepperDex Sarawak logo at the top left** instead of the page name (Home / Advisor / Farm — those names stay only as the bottom tab-bar labels). The asset is the real `pitch-and-design/PepperDex_Logo.png` with transparent margins trimmed (`frontend-rn/assets/brand/pepperdex-wordmark-header.png`) — never a recreated wordmark. Settings stays the top-right icon (§9.16). Pushed screens (Block Detail, Settings, Diagnosis) keep a normal back-arrow + title header, since the logo would compete with the back button.

**Data Dictionary**

| Field | Type | Source | Notes |
|---|---|---|---|
| `setup_completed` | bool | `GET /farm/{id}` → `setup_completed_at != null` | Gate condition |
| `active_tab` | enum(`home`,`advisor`,`farm`) | local nav state | |
| `home_badge_count` | int | `dashboard.pending_alerts.length` | Shown on Home tab icon |

---

### 9.1 · Home — Rain Pulse Card (upgraded from single-day to 7-day)

**Location:** Home, top of screen, always rendered.
**Purpose:** the "works with zero photographs" claim, made visible every time the app opens.
**Channeling logic:** tapping the card expands it in place (no navigation) to show the full 7-day chart; collapsed state shows only the next pulse.

**Data Dictionary**

| Field | Type | Source | Notes |
|---|---|---|---|
| `forecast_days[]` | array\<`DailyForecast`\> | `GET /farm/{id}/rain-pulse` | Was a single next-pulse object in v1 |
| `DailyForecast.date` | date | — | |
| `DailyForecast.rainfall_mm` | float | — | |
| `DailyForecast.is_pulse` | bool | derived: `rainfall_mm >= pulse_threshold_mm` | Drives the colour-coded wave rendering |
| `DailyForecast.is_cached_fallback` | bool | `weather_observations.is_cached_fallback` | Honesty flag — shown as a small "estimated" tag, never hidden |
| `station_id` | string | `farms.weather_station_id` | |
| `speech_template_id` | string | — | Every card must be speakable per non-negotiable rule 7 |

---

### 9.2 · Home — Priority Action Card + Bento Metrics (was: extensible drawer)

> 🔄 **Revised 2026-09-19 (owner preference).** The card is **always rendered**, and the old tap-to-expand drawer is replaced by **always-visible bento tiles** — nothing to tap to see the metrics.
>
> | State | What the card shows |
> |---|---|
> | **Before any diagnosis** (`top_action` null) | "No diagnosis yet" + a primary shortcut, **"Start your first diagnosis"** |
> | **After a diagnosis** | The immediate action (type, when, one-sentence reason) → the diagnosis metrics as **square bento tiles** → "View block" / "Add to calendar" links → a secondary **"Diagnose again in Advisor"** shortcut |
>
> **The shortcut** (both states) opens the Advisor tab with `/diagnose` **typed into the send box but not sent** — the farmer taps send themselves. It passes `prefill=/diagnose` plus a per-tap nonce so tapping twice re-applies it. This is the same Advisor gate §6 mandates: no screen starts a diagnosis except through the Advisor.
>
> **Bento tiles** (all values are estimates; the "estimates, not measurements" note is persistent): **Risk**, **Confidence** *(input quality, not disease certainty)*, **Arrives in** (ETA days), **Rain 7d** — from the `risk_assessments` row behind the action; a **Deferred** tile (`rainfast`, etc.) when the arbitration deferred something; **Last check** (days since / result) and **Rain since** from the Advisor's own evidence. Tiles whose source doesn't exist are omitted, never shown as a placeholder zero — a fully-healthy cycle has no spread projection, so it shows only the Advisor-evidence tiles.

**Location:** Home, below Rain Pulse.
**Purpose:** the single arbitration output — one action, one time, one reason, plus the numbers behind it.
**Channeling logic:** tapping the action text plays the TTS reason (no navigation). Tapping "View block" navigates to 9.7 (Farm → Block Detail). The shortcut button opens Advisor with `/diagnose` prefilled.

**Data Dictionary**

| Field | Type | Source | Notes |
|---|---|---|---|
| `recommendation_id` | string | `recommendations.recommendation_id` | |
| `block_id`, `block_label` | string | `blocks` | Tap target → 9.7 |
| `action_type` | enum | `recommendations.action_type` | |
| `recommended_at`, `window_start`, `window_end` | datetime | `recommendations` | |
| `reason_ms` | string | `recommendations.reason_ms` | One sentence, always shown collapsed |
| `speech_template_id` | string | `recommendations.speech_template_id` | |
| **`drawer.risk_score`** | float | `risk_assessments.risk_score` | Shown only when drawer expanded |
| **`drawer.confidence`** | float | `risk_assessments.confidence` | Input-quality, not disease certainty; label accordingly |
| **`drawer.eta_days`** | int? | `risk_assessments.eta_days` | |
| **`drawer.defer_cause`** | string? | `recommendations.defer_cause` | This is the arbitration evidence; e.g. `"rainfast"` |
| **`drawer.rainfall_7d_mm`** | float | `risk_assessments.rainfall_7d_mm` | |
| `is_estimate` | bool | always `true` | Rendered as a persistent disclaimer, not just on first view |

---

### 9.3 · Home — Advisor Summary Card (cross-reference is new)

**Location:** Home, below Priority Action.
**Purpose:** surfaces the Advisor's current verdict inline, cross-linked to the action card above it.
**Channeling logic:** tapping "Ask more" navigates to 9.4 (Advisor chat) with the current verdict pre-loaded as context. Only rendered when `urgency != none`.

**Data Dictionary**

| Field | Type | Source | Notes |
|---|---|---|---|
| `urgency` | enum(`high`,`medium`,`low`,`none`) | `advisor_verdicts.urgency` | Card hidden entirely if `none` |
| `reason_code` | string | `advisor_verdicts.reason_code` | e.g. `protected_stable` |
| `reason_ms` | string | `advisor_verdicts.reason_ms` | |
| **`related_recommendation_id`** | string? | `advisor_verdicts` field | Links this verdict to 9.2's current action, if any |
| `last_cycle_result`, `days_since_last_cycle`, `rain_since_last_cycle_mm` | mixed | `advisor_verdicts` | Evidence for a "not yet" verdict — shown to justify inaction, not just assert it |

---

### 9.4 · Advisor — Chat Screen (entirely new screen)

**Location:** Advisor tab, root screen.
**Purpose:** free-form farmer questions over hybrid-search RAG, and the entry point for the `/diagnose` command.
**Channeling logic:** a message beginning with `/diagnose` is intercepted client-side and routed to the diagnosis-necessity flow (9.5) instead of the general chat endpoint — see §B.1 for why this routes through the Advisor rather than starting `DiagnosisCoordinator` directly.

**Data Dictionary**

| Field | Type | Source | Notes |
|---|---|---|---|
| `messages[]` | array\<`ChatMessage`\> | local state + `POST /advisor/chat` | |
| `ChatMessage.role` | enum(`user`,`advisor`) | — | |
| `ChatMessage.text` | string | — | |
| `ChatMessage.citations[]` | array\<string\>? | response `source_ref`s | From `knowledge_docs` — always attributed, never bare assertion |
| `ChatMessage.is_command` | bool | client-side regex on input | `true` if message matched `/diagnose` |
| `input_text` | string | local state | |
| `is_typing` | bool | local state | While awaiting response |

---

#### 9.4a · Live agent feed (added 2026-09-23)

After the photo loop, `app/diagnosis.tsx` starts the run with `POST /agent/run {background: true}` (returns the `agent_runs` row with `status: "running"` at once) and opens this chat with `runId`. The chat polls `GET /agent/runs/{run_id}/events?after=<seq>` every 1.5 s: `{status, done, current, events[]}`, each event `{seq, agent, kind, text_ms, text_en, speech_template_id: "_adhoc"}`.

- **Agents shown:** `diagnosis_coordinator`, `spread_model`, `rules_table`, `advisor_rag`, `council_agronomic` / `council_cost` / `council_logistics` / `council_orchestrator` (only when the farm is Overrun), `calendar_mcp`, `root_agent`. `kind`: `step | warning | debate | final | approval`.
- **Every event is derived from something that happened** (a logged tool call, a `council_debates` row, a fallback/guard decision) -- never a model narrating itself afterwards. A finished run's feed is rebuilt from the DB if the in-memory feed is gone.
- **Order the farmer sees:** CNN results per block -> (council debate, if Overrun) -> weather, spread, treatment, spray window -> any `rules_guard` / fallback warning -> the decision -> "N schedule proposals await your approval" -> the proposal cards. Home is refreshed when `done`.
- **Known limit:** council turns appear together once the council finishes (the transcript is written at the end), not turn by turn.

### 9.5 · Advisor — Diagnosis Necessity Card

**Location:** rendered inline within 9.4's chat thread, triggered by `/diagnose`.
**Purpose:** the Advisor evaluates whether a diagnosis cycle is warranted right now — **and must show a working path forward regardless of its own verdict.**
**Channeling logic — ⚠️ non-negotiable:** the "Begin Diagnosis" button is **always rendered and always enabled**, whether the verdict is "necessary" or "not yet." The Advisor recommends; it never blocks. Tapping the button navigates to 9.8 (Diagnosis Capture Flow).

**Data Dictionary**

| Field | Type | Source | Notes |
|---|---|---|---|
| `verdict` | `AdvisorVerdict` | `POST /farm/{id}/advisor/evaluate` (triggered by `/diagnose`) | Reuses the verdict shape from 9.3 |
| `can_begin_diagnosis` | bool | **hardcoded `true`** | ⚠️ Never computed from the verdict — see channeling rule above |
| `cycle_resume_available` | bool | `diagnosis_cycles.status == 'in_progress'` | If true, button label changes to "Resume Diagnosis (n/m blok)" |

---

### 9.6 · Farm — Terrain Risk Canvas — **3D scene, corrected from an earlier flat-canvas spec**

**Location:** Farm tab, root screen.
**Purpose:** the signature visual — blocks spaced by real relative distance, rendered with genuine 3D depth, oriented so upslope reads consistently regardless of true compass bearing.
**Rendering:** `@react-three/fiber` + `expo-gl` — native GPU 3D, not a flat 2D canvas, not a WebView. Blocks as raised 3D nodes; flow edges as flowing 3D paths; a stylised ground plane beneath (not a literal terrain mesh — see §3 L2 for why dense elevation data doesn't exist to build one).
**Channeling logic:** tapping a block node navigates to 9.7. Camera supports orbit/pan/zoom — this is the one screen where that extra interaction genuinely helps.

**Data Dictionary**

| Field | Type | Source | Notes |
|---|---|---|---|
| `blocks[]` | array\<`BlockNode`\> | `GET /farm/{id}/dashboard` | |
| **`BlockNode.x_rot_m`, `BlockNode.y_rot_m`** | float | Computed backend-side, §3 L2 | Rotated local-metre coordinates — backend's job, not frontend's |
| **`BlockNode.z_height`** | float | Derived client-side from `elevation_rank`/`baro_rel_m` | Stylistic depth, not a survey height |
| `BlockNode.elevation_rank`, `state`, `label`, `photo_uri` | mixed | `blocks` | Unchanged from v1 |
| `edges[]` | array\<`EdgeSummary`\> | `flow_edges` | Rendered as flowing 3D paths, not straight 2D lines |
| **`scene_scale`** | float | Computed client-side — adaptive fit to viewport + camera framing | Device-dependent; must never be computed backend-side |
| `elevation_tier` | enum | `farms.elevation_tier` | Drives whether a confidence-tint overlay is shown (optional stretch) |

---

### 9.7 · Farm — Block Detail / Diagnosis History Screen (was a bottom sheet in v1; promoted to a full screen since Farm is now its own tab)

**Location:** Farm stack, pushed from 9.6.
**Purpose:** everything about one block — history, current state, and the entry point to a targeted diagnosis.
**Channeling logic:** the "Diagnose" button here does **not** start capture directly — it routes to 9.4 with `/diagnose` pre-filled, exactly like the general flow, so the Advisor gate is never bypassed by entering through Farm instead of Advisor.

> ✅ **Resolved — "block" terminology confirmed.** This screen shows one block's aggregated history, not an individual plant's.

**Data Dictionary**

| Field | Type | Source | Notes |
|---|---|---|---|
| `block` | `BlockDetail` | `GET /blocks/{id}` | |
| `voice_label_uri` | string? | `blocks.voice_label_uri` | Playback only — never transcribed (rule 1) |
| `state_timeline[]` | array | `risk_assessments` history for this block | Rainfall overlaid |
| `diagnosis_history[]` | array\<`Diagnosis`\> | `diagnoses` joined on `observations.block_id` | |
| `treatment_log[]` | array\<`TreatmentApplication`\> | `treatment_applications` | Includes the `rain_within_rainfast` "wasted spend" flag |
| `is_external` | bool | `blocks.is_external` | ⚠️ If true, **only `current_state` is rendered** — no diagnosis, no photo, no treatment history (rule 4) |

---

### 9.8 · Diagnosis Capture Flow

> ✅ **Built 2026-09-19** (`frontend-rn/app/diagnosis.tsx`). It was missing before — the Advisor's "Begin Diagnosis" button pointed at the Farm tab as a placeholder and stopped there, which a tester on Expo Go reasonably read as an Expo Go limitation; it was not. **As built:** a one-block-at-a-time flow over the backend's cycle API (`POST /farms/{id}/diagnosis-cycles` resumes an in-progress cycle → per block: pick leaf/collar → photo → `POST /media` → `POST /observations`). A mismatch shows the retake prompt; **"Use this photo anyway"** re-submits with `force_accept` (the farmer beats the classifier — rule 3's principle); after 2 rejected attempts the backend accepts it. When the cycle completes, `POST /agent/run` arbitrates one recommendation per block — that is what populates the Home priority card (§9.2). The whole-vine target is not offered (removed from the selector in v1, enum retained). **Known limits:** (1) the agent run takes minutes on the local `qwen2.5:14b`, so the client just holds a spinner with an honest message — a background job + polling is the proper fix, not yet built; (2) a resumed cycle knows *how many* blocks are counted but not *which*, so resume assumes the first N by elevation rank (the order this screen visits them).

**Location:** modal stack, entered from 9.5 only (the Advisor gate, §6) — Block Detail's "Diagnose" routes through Advisor with `/diagnose` prefilled, never here directly.
**Purpose:** the multi-sample capture loop — 2–4 photos per block, worst-class-wins aggregation.
**Channeling logic:** driven by `DiagnosisCoordinator` (backend LoopAgent) — the client polls or streams cycle state and renders whichever block the loop currently wants captured.

**Data Dictionary**

| Field | Type | Source | Notes |
|---|---|---|---|
| `cycle_id` | string | `diagnosis_cycles.cycle_id` | |
| `blocks_total`, `blocks_captured` | int | `diagnosis_cycles` | Drives progress UI |
| `current_block_id` | string | LoopAgent's `CapturePrompter` output | |
| `captured_target` | enum(`leaf`,`collar`,`whole_vine`) | user tap before shutter | Feeds the mismatch check below |
| `capture_target_mismatch` | bool? | backend response to submitted photo | ⚠️ If true, prompt a retake, not a recorded check |
| `is_resumable` | bool | `diagnosis_cycles.status == 'in_progress'` | |

---

### 9.9 · Setup Wizard — Registration & Location

> ⚠️ **Corrected 2026-09-18 — a v1 widget went missing in the v2 rewrite.** The archived Flutter build (`flutter_app/lib/tier_banner.dart`) shows `TierBanner` on **both** this screen and §9.10's walk screen. The v2 rebuild dropped it after misreading the line below as "never show the tier at all" — the real distinction, stated in that file's own doc comment, is narrower: **detection** is silent and automatic (the farmer is never asked, never chooses which tier to be on); the **result** is reported plainly and neutrally once known, framed as a fact about the phone, not a verdict on the farmer ("a phone without a barometer is not broken, it just means the farmer answers the elevation questions themselves"). Restored below and in §9.10 — see `docs/VALIDATION_CHECKLIST.md`'s 2026-09-18 log entry.

**Data Dictionary**

| Field | Type | Source | Notes |
|---|---|---|---|
| `display_name`, `phone`?, `district` | string | user input | `phone` optional, PII — flag for encryption at rest |
| `language_pref` | enum(`ms`,`iba`,`en`) | user input | |
| `gps_lat`, `gps_lon` | float | `expo-location` | |
| `weather_station_id` | string | `POST /farms` response | Backend binds nearest station |
| **`tier_banner`** | `{available: bool, blockCount?: int}` | client-side barometer probe (silent, automatic) | **Shown**, once detection finishes: `"Barometer dikesan"` (OPTIMISED) or `"Tiada barometer"` (MINIMAL), plus — on the MINIMAL path — a preview of how many pairwise elevation questions the walk will end with (`C(n,2)`), so the farmer isn't surprised mid-walk. Neutral framing, never "lesser version"; a retry action when a barometer might be present but wasn't detected yet |

### 9.10 · Setup Wizard — Block Capture Loop

**Data Dictionary**

| Field | Type | Source | Notes |
|---|---|---|---|
| `walk_session_id` | string | `POST /farms/{id}/walk-sessions` | |
| `sample_stream[]` | array\<`{lat, lon, gps_alt_m, baro_alt_m?, accuracy, t}`\> | `expo-location` + `expo-sensors` @ 2 s interval | `baro_alt_m` present only if barometer detected |
| `current_block_draft` | `{photo_uri, label, voice_label_uri}` | camera + `expo-av` | Committed on "Button A" tap |
| `elevation_tier` | enum(`minimal`,`optimised`) | client-side sensor probe, set once | **Detection** is silent — the farmer is never asked to choose a tier. The **result** is shown via `tier_banner` (same widget as §9.9), repeated here so it stays visible during the walk itself, not just at registration |
| **`tier_banner`** | see §9.9 | same as §9.9 | Same widget, same data — shown again here per the archived v1 build (`TierBanner` appeared "on both registration and the walk screen") |
| **`walk_map`** | `{track: LatLon[], blocks: BlockPin[], current: LatLon?}` | `expo-location` live stream + already-captured blocks | Live map: the GPS track walked so far (a line), a numbered pin per captured block (numbered by capture order or `elevation_rank` once known), and a distinct live position marker. Auto-follows the farmer; any manual pan/zoom releases auto-follow, with a recentre button to resume it. Draws the walked path and marked points **only** — no boundary, polygon, or parcel outline is ever drawn, inferred, or stored (rule 4, NCR land is legally sensitive). Map tiles need network; offline, the walk still works and the map just renders blank/stale rather than blocking capture |
| **`altitude_readout`** | `{relative_m: float?}` | `expo-sensors` barometer, live, relative to the session's baseline pressure | Compact live readout during the walk ("+3.2 m from start") — OPTIMISED tier only; shows "—" when no barometer, never a fabricated number. Relative only, never an absolute altitude (a phone barometer cannot honestly claim one) |
| **`position_readout`** | `{lat: float, lon: float, accuracy_m: float, distance_to_last_mark_m?: float}` | `expo-location`, live | Live numeric lat/lon + GPS accuracy while walking, and the straight-line distance to the most recently marked block — lets a farmer confirm they've actually moved to a new spot before tapping "Mark this block" again, rather than accidentally re-marking the same corner |

### 9.11 · Setup Wizard — Elevation Resolution

**Data Dictionary**

| Field | Type | Source | Notes |
|---|---|---|---|
| `ambiguous_pairs[]` | array\<`{block_a, block_b}`\> | backend — pairs where `Δh < 2.0m` or MINIMAL tier (all pairs) | |
| `farmer_answer` | enum(`a_higher`,`b_higher`) | user tap | ⚠️ Always wins on conflict — logged to `elevation_conflicts`, never auto-resolved (rule 3) |

### 9.12 · Setup Wizard — Drainage & Neighbour Contacts

**Data Dictionary**

| Field | Type | Source | Notes |
|---|---|---|---|
| `drainage` | enum(`good`,`fair`,`poor`) | two-photo tap comparison | Per block |
| `neighbour_contacts[]`? | array\<`{name, phone, water_direction}`\> | user input, optional | Farmer-entered only — never scraped (rule 4) |

### 9.13 · Setup Wizard — Validator Summary

**Data Dictionary**

| Field | Type | Source | Notes |
|---|---|---|---|
| `is_complete` | bool | `SetupCoordinator` LoopAgent escalation | |
| `flagged_issues[]` | array\<string\> | deterministic `check_setup_state` | e.g. missing photo, unresolved conflict |
| `farm_graph_preview` | reuses 9.6's 3D canvas component | — | Farmer's first look at their own farm, rendered before entering the main tabs |

---

### 9.14 · Neighbour Alert Approval Card (cross-cutting)

**Location:** surfaces on Home (badge-driven) and inside 9.7.

**Data Dictionary**

| Field | Type | Source | Notes |
|---|---|---|---|
| `alert_id`, `message_ms`, `risk_band_shared` | mixed | `alerts` | ⚠️ Only a risk band is ever shown — never diagnosis detail (rule 4) |
| `approved_by_farmer` | bool | user tap — **defaults false, never pre-checked** | Rule 5 |

### 9.15 · Calendar Sync Consent Modal

**Location:** triggered whenever a new recommendation carries a schedulable action (spray/fertiliser dates).
**Channeling logic:** ⚠️ never auto-triggers a sync; always presents a draft the farmer approves, exactly matching 9.14's consent pattern reused, not reinvented.

**Data Dictionary**

| Field | Type | Source | Notes |
|---|---|---|---|
| `draft_events[]` | array\<`{title, date, description}`\> | `draft_calendar_sync` LLM-backed tool | |
| `granted` | bool | user tap — defaults false | |
| `provider` | enum(`device_calendar`) | fixed for v2 | Google Calendar MCP is a later stretch |

### 9.16 · Settings Screen

**Note:** not a bottom tab — accessed via a top-right icon on any screen, to keep the 3-tab structure clean. *(Confirmed placement.)*

**Data Dictionary**

| Field | Type | Source | Notes |
|---|---|---|---|
| `language_pref` | enum | user setting | |
| `elevation_tier` | enum | read-only display | Shows current tier, no override — sensor detection is automatic |
| `reset` | action | long-press only | ⚠️ Never a visible one-tap control |

---

### Package migration (Flutter → React Native)

| Flutter | React Native (Expo) |
|---|---|
| `geolocator` | `expo-location` |
| `sensors_plus` | `expo-sensors` |
| `camera` | `expo-camera` |
| `record` / `just_audio` | `expo-av` / `expo-audio` |
| `sqflite` | `expo-sqlite` |
| `riverpod` | Zustand + TanStack Query |
| `dio` | `fetch`, typed via `openapi-typescript` |
| `tflite_flutter` | `react-native-fast-tflite` (only if OPTIMISED on-device tier pursued) |
| — | `@react-three/fiber` + `expo-gl` (native 3D — **now actually used, by 9.6**, not just listed) |

**Why this was a rebuild, not a refactor:** no incremental path exists from `.dart` to `.tsx`. Two concrete blockers drove the switch: Flutter's barometer library was silently absent (later traced to a `sensors_plus` version below v6.0.0), and Flutter has no mature native 3D path — the v1 workaround required wrapping a WebView around a browser-based 3D viewer. Both are structural to the Flutter ecosystem, not bugs to patch.

---

## 10 · API Contract Reference (Pydantic) — restored, was dropped during an earlier merge

These are the concrete request/response models backing §9's components. Define once, reuse for FastAPI validation, ADK tool schemas, and generated TypeScript types.

```python
class DailyForecast(BaseModel):
    date: date
    rainfall_mm: float
    is_pulse: bool
    is_cached_fallback: bool

class RainPulseResponse(BaseModel):          # was single-pulse in v1
    forecast_days: list[DailyForecast]       # now 7 entries
    station_id: str

class RecommendationDrawer(BaseModel):
    risk_score: float
    confidence: float
    eta_days: int | None
    defer_cause: str | None
    rainfall_7d_mm: float

class AdvisorVerdict(BaseModel):
    urgency: AdvisorUrgency
    reason_code: str
    reason_ms: str
    related_recommendation_id: str | None
    last_cycle_result: str | None
    days_since_last_cycle: int
    rain_since_last_cycle_mm: float

class BlockNode(BaseModel):                  # feeds the 3D canvas, §9.6
    block_id: str
    elevation_rank: int
    current_state: BlockState
    label: str
    photo_uri: str
    x_rot_m: float                           # backend-computed
    y_rot_m: float                           # backend-computed
    # z_height and scene_scale are client-side only — not in this response

class TriageRanking(BaseModel):              # see §3 L4 — deliberately dose-less
    block_id: str
    rank: int
    rationale_ms: str

class DraftCalendarEvent(BaseModel):
    title: str
    date: date
    description: str
```

## 11 · Data Model Deltas (v2 additions — full schema in `docs/DATA_MODEL.md`)

New tables: `calendar_sync_grants`, `council_debates`, `knowledge_docs_fts` (search index only). New computed (not persisted) fields on block responses: `x_rot_m`, `y_rot_m`. Full detail in `DATA_MODEL.md`.
