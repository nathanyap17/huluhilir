# MASTER_SHEET.md — PepperDex Sarawak: Project Master Sheet

> **Purpose.** The single, authoritative answer sheet for the six perspectives judges and funders ask about: problem and relevance, innovation, technology, impact, feasibility, and business model. It is written to be **rigorous** (every figure sourced or traced to the code), **easy to understand** (each section opens with a plain-language summary; a glossary is at the end), and **reliable** (what is proven, assumed or not yet verified is stated explicitly).
>
> **Project:** PepperDex Sarawak: terrain-aware early warning of Phytophthora foot rot for Sarawak black pepper smallholders
> **Team:** SMILING FACE WITH SUNGLASSES, Universiti Malaysia Sarawak (UNIMAS): Nathan Yap Jia De (technical lead) · Zoe Tan An Xuen (deliverables) · Abraham Pang Exin (project management)
> **Event:** AgroHack 2026, Sarawak AgroFest, Sibu, 25–27 September 2026
> **Try it:** https://sfws-aicc-workspace-1.web.app/ (free Android app, "Try the demo farm") · Code: https://github.com/nathanyap17/huluhilir
> **Status date:** 25 September 2026 (Android app build 20; backend live on Google Cloud Run)

### How to read the evidence labels

| Label | Meaning |
|---|---|
| **[n]** | Published source; see the reference list at the end |
| **(Built)** | Verified in the working system: code, tests or the live deployment |
| **(Design)** | A design choice or engineering assumption, not an empirical finding |
| **(Pending)** | Stated in good faith but **not yet verified**; listed in §7 |
| **Roadmap** | Planned, not built. Never presented as working |

---

## Executive summary

**In plain words:** pepper in Sarawak grows on hillsides. A deadly soil-borne disease, foot rot, travels with rainwater from the top of a farm to the bottom. Today's tools only look at one plant at a time. PepperDex is a free Android app that maps which part of a farm drains into which, watches the rain forecast, checks photos for early signs, and tells the farmer **one action, at one time, for one reason**, for example *"Clear the drain today. Drench Thursday morning."* It is built, deployed and downloadable. It is designed to be paid for by the institutions that already support farmers, so farmers use it free.

| Perspective | One-line answer |
|---|---|
| Problem & relevance | A water-borne disease spreading down Sarawak's hillside pepper farms, fought with single-plant tools |
| Innovation | Predicts *where the disease goes next and when*, and arbitrates conflicting evidence into one timed, rule-bound action |
| Technology | Android app + cloud backend; AI agents reason over deterministic models; plain-code safety checks stand between the AI and the farmer |
| Impact | Earlier action, treatments that hold, fewer wasted sprays, and accessible technology for smallholders |
| Feasibility | Working and deployed today; zero hardware; free public data; honest about what still needs field validation |
| Business model | B2B2C: institutions subscribe (maintenance + AI usage), farmers use it free; private growers pay per farm |

---

## 1️⃣ Problem & Relevance

> **In plain words:** almost all of Malaysia's pepper grows on Sarawak's hillsides. A soil germ that travels in water can move down a hillside farm with each heavy rain, killing vines and a large share of a farmer's income. Farmers can't see it coming, and treatments sprayed before rain wash away.

### 1.1 Context: who grows pepper, and where

- Sarawak produces **over 98% of Malaysia's pepper** [1].
- As of March 2026, **38,587 smallholders** cultivate **8,061 ha** of pepper in Sarawak [4], an average of about **0.2 ha per smallholder** (derived: 8,061 ÷ 38,587). These are very small family farms.
- Pepper is planted on **hilly slopes of about 25–30°**. One reason farmers choose hills is to **reduce soil-borne diseases caused by *Fusarium* and *Phytophthora*, which favour waterlogged conditions** [2].
- Sarawak receives **2,800–4,700 mm of rain per year**, and the crop needs a proper drainage system to avoid foot rot [2].

### 1.2 The disease and how it moves

- **Foot rot** (also called quick wilt) is caused by the oomycete ("water mould") ***Phytophthora capsici***.
- *P. capsici* **survives in soil for long periods as oospores** and **moves in surface water** [3].
- **The mechanism PepperDex is built on** (*Design*, a reasoned inference from [2] and [3]): on a slope, surface water flows downhill, so a heavy rain can carry the pathogen from an infected block to the blocks below it. Spread is therefore **directional** (downhill) and **episodic** (it happens with rain events, "rain pulses"), not uniform in all directions.

### 1.3 The burden

The most detailed farm-level economic study found is from **west-coast India** (Goa and coastal Karnataka), not Sarawak [5]:

| Measure | Value [5] |
|---|---|
| Average vine mortality from foot rot | **9.64%** |
| Economic loss | **USD 902.04 per hectare**, about **56% of annual net returns** |
| Loss if unmanaged | USD 1,838 per hectare |
| Loss reduction from good drainage (avoiding water stagnation) | **24% (USD 439/ha)** |
| Loss reduction from fungicide use | 20% (USD 364/ha) |

**Transferability caveat:** no equivalent published Sarawak loss study was found. Sarawak's steeper slopes and heavier rainfall [2] suggest the problem is at least as relevant here, but the Indian figures are cited as **indicative**, not as Sarawak measurements.

### 1.4 Three compounding gaps

1. **Late detection.** Infection begins at the roots and collar (stem base). Visible leaf yellowing comes late, when a vine is often past saving.
2. **Catchment blindness.** Transmission follows water across block (and property) boundaries, but each farmer sees only their own blocks and cannot tell whether runoff from above is carrying disease.
3. **Mistimed treatment.** Fungicides need a rain-free period after application (the "rain-fast" period) to work; applied before heavy rain, they wash off. This wastes money and moves chemicals into soil and water.

### 1.5 Why this matters now

- **The most effective lever is cheap and known.** In [5], drainage cut losses more than fungicide did. What farmers lack is *where* and *when* to act, block by block.
- **The state is investing in pepper,** with plans for a 10,000 ha expansion and new technology [1]. Disease losses directly undermine that investment.
- **The enablers exist:** smartphones are widespread, and Malaysia's government publishes weather forecasts openly (data.gov.my).

---

## 2️⃣ Innovation

> **In plain words:** other tools answer "what is wrong with this plant?". PepperDex answers "**which part of my farm is next, when, and what should I do about it today, given the rain?**", and it can't make up a treatment.

### 2.1 What is new

| # | Innovation | What it means | Evidence |
|---|---|---|---|
| 1 | **Terrain-aware spread projection** | The farm is modelled as a *directed elevation graph*: blocks are points, arrows run only downhill. From one confirmed case, the model projects **risk, path and arrival time** for every block below | (Built) §3.3 |
| 2 | **Evidence arbitration by AI agents** | Four sources that often disagree (photo check, spread projection, rain forecast, treatment rules) are weighed together into **one action, one time, one reason** per block | (Built) §3.4 |
| 3 | **Rain-timed treatment** | Sprays and drenches are scheduled only in forecast windows that stay dry for the treatment's full rain-fast period, or deferred behind drain clearing | (Built) §3.3 |
| 4 | **Safety by construction** | The AI cannot set a product, dose or time: these come only from a fixed rules table, and plain-code checks correct any deviation. The outbreak "council" has no field in its output that could hold a treatment | (Built) §3.5 |
| 5 | **Visible reasoning** | The app shows each agent's real step as it happens (photo results → rain → spread → rules → decision), not a loading spinner | (Built) |
| 6 | **Consent-first actions** | Every scheduled action is an Approve/Reject card; nothing is written to a calendar or sent to a neighbour without the farmer's tap | (Built) |
| 7 | **Designed for Sarawak smallholders** | No land boundaries or ownership recorded (NCR land sensitivity); spoken Bahasa Malaysia; blocks named by the farmer's own voice recording (stored, never transcribed); works without special sensors | (Built) |

### 2.2 Positioning against existing tools

| | Plant diagnosis | Spread across terrain | Rain-timed treatment | Agent arbitration |
|---|---|---|---|---|
| Dr.LADA | Rule-based | — | — | — |
| NutriLada | Records, education | — | — | — |
| MD AgTech | General crops | — | — | — |
| MPB laboratory | Laboratory, after the fact | — | — | — |
| **PepperDex** | **Photo, on phone** | **Yes** | **Yes** | **Yes** |

Basis: the team's review of publicly described features, September 2026 (*Pending*: each cell to be re-confirmed before formal submission). To our knowledge, **no existing tool for pepper smallholders models pathogen transmission across farm terrain.**

### 2.3 What is deliberately *not* claimed as novel

- **Photo-based plant disease detection** is an established field. PepperDex's classifier is a standard, lightweight network; its role is to trigger inspection, not to be the innovation.
- **Weather-based spray advice** exists in other crops. The novelty is **combining** it with a terrain spread model and a rule-bound agent, per block, for pepper.

---

## 3️⃣ Technology

> **In plain words:** the farmer's phone collects the farm layout and photos. A cloud server works out where water and disease flow, checks the forecast and the official treatment list, and a team of AI helpers combines everything into one plan. Before the farmer sees it, simple built-in checks make sure the plan follows the rules.

### 3.1 Architecture: five layers

| Layer | Purpose | Method (Built) | Key design rule |
|---|---|---|---|
| **L0 Voice & language** | Make advice usable regardless of literacy | Text-to-speech in Bahasa Malaysia; farmers' spoken block names stored as audio and replayed | **No speech recognition** anywhere |
| **L1 Diagnosis** | Spot early signs from a photo | MobileNetV3-Small image classifier, exported to ONNX, run on the server; 6 classes: healthy leaf, healthy collar, foliar yellowing, collar lesion, defoliation/wilt, unrelated | Unsure results (confidence < 60%) never lower a block's status; they prompt inspection |
| **L2 Spread** | Project downhill risk and timing | Deterministic directed elevation graph (§3.3) | **Not machine learning**; the farmer's elevation answer overrides sensors |
| **L3 Knowledge** | Decide *what* is allowed; explain *why* | A rules table of 6 treatments with rain-fast hours; 23 explanatory documents searched by meaning (sentence embeddings) plus keywords (full-text search) | Rules decide *what*; documents only explain *why* and cannot surface a dose |
| **L4 Agents** | Arbitrate everything into one plan | Google Agent Development Kit: Router agent, Setup wizard, DiagnosisCoordinator, Advisor, and a 4-agent Overrun Council | Loop termination and safety checks are plain code, never AI judgement |

### 3.2 Setting up a farm: building the elevation graph (Built)

1. **Walk and mark.** At each block the phone records GPS position (the median of several readings, to reject jitter), a photo, and the farmer's spoken name for the block.
2. **Rank by height.** Two paths:
   - *No barometer (minimal tier):* the farmer is asked "which is higher?" for **every pair** of blocks (6 blocks = 15 questions).
   - *Barometer (optimised tier):* the phone's air-pressure sensor ranks blocks, and the farmer is asked only where two blocks differ by **less than 2.0 m**.
   In both, **the farmer's answer always wins**; any disagreement with the sensor is logged, never silently resolved.
3. **Connect downhill.** Each block is linked to its **3 nearest neighbours**, keeping only links that run **downhill**. This guarantees the graph has no loops.
4. **Weight each link** (how strongly water carries from block *i* to block *j*):

   `flow_weight = 0.4 × slope + 0.3 × proximity + 0.3 × drainage(j)`, capped at 1

   - *slope* = elevation drop ÷ distance, normalised so a 1:10 slope scores 1 (0.5 if unknown)
   - *proximity* = 1 ÷ (1 + distance ÷ 50 m)
   - *drainage(j)* = 0.2 (good), 0.5 (fair) or 1.0 (poor) at the receiving block

   The weights 0.4 / 0.3 / 0.3 are an **engineering judgement (Design)**; no calibration dataset exists yet.

**Privacy:** only relative elevation order and distances between blocks are stored. **No land boundaries or ownership**, in respect of Native Customary Rights (NCR) land sensitivities.

### 3.3 The deterministic models (Built)

**Spread projection.** Given a diseased source block, the model finds the shortest downhill route to every reachable block (links marked as barriers, e.g. a bund or road, are excluded) and computes:

| Quantity | Formula | Notes |
|---|---|---|
| Source severity *s* | collar lesion 1.0 · defoliation/wilt 0.9 · foliar yellowing 0.5 · healthy/unrelated 0 | Healthy photos seed nothing |
| Rain factor *r* | min(1, (past 7-day rain + next 7-day rain) ÷ 100 mm) | 100 mm/week treated as a heavy week (*Design*) |
| **Risk** | min(1, (product of flow weights along the path) × *r* × *s*) | 0–1 |
| **Arrival (days)** | max(1, round(2 × hops ÷ max(0.2, *r*))), reported only if risk ≥ 0.05 | 2 days per hop in a heavy week (*Design*) |
| Confidence | 0.55–0.75 (minimal tier) or 0.75–0.95 (barometer tier), scaled by the share of links the farmer confirmed | Reflects input quality |

Every risk and arrival figure is labelled **`is_estimate: true`** and shown to the farmer as an *estimate*.

**Worked example.** Block 1 has a collar lesion (*s* = 1.0). Rain: 60 mm in the past week and 40 mm forecast, so *r* = min(1, 100/100) = 1.0. The link Block 1 → Block 2 has flow weight 0.8; Block 2 → Block 3 has 0.7.
- Block 2: risk = 0.8 × 1.0 × 1.0 = **0.80**; arrival = round(2 × 1 ÷ 1.0) = **~2 days**
- Block 3: risk = 0.8 × 0.7 × 1.0 × 1.0 = **0.56**; arrival = round(2 × 2 ÷ 1.0) = **~4 days**
- If the fortnight were drier (*r* = 0.5), Block 3's risk halves to 0.28 and arrival stretches to ~8 days: **the rain drives the spread**.

**How block status changes** (*Built*, covered by automated tests):

| Status | Set by | Rule |
|---|---|---|
| Protected | A confident (≥ 60%) healthy leaf or healthy collar photo, or no projected risk | An unsure healthy result, an unrelated photo or an unknown result is **not evidence** and never lowers a status |
| Alerted | A foliar-yellowing photo, **or** the spread projection (no photo of that block needed) | A projection can raise a Protected block to Alerted; it never lowers a status and never sets Harmed |
| Harmed | A photo diagnosis of collar lesion or defoliation/wilt | Only a diagnosis can set Harmed |
| Overrun | Farm-wide, derived: more than one block Harmed at once | Triggers the Overrun Council |

Within one diagnosis round, the worst result for a block wins, so a retake never downgrades it. The first confident photo of a **new** round sets the block's status afresh, so a healthy re-check after treatment can return a block to Protected.

**Spray window.** For a treatment with a rain-fast period of *h* hours, a forecast window is viable only if **no forecast point within those *h* hours carries ≥ 5 mm of rain**. If no window is viable, the treatment is **deferred** and drain clearing (no rain-fast period) goes first. The chosen day is converted to a practical field slot: a date-only time becomes 08:00, never sooner than the next full hour at least 30 minutes away, and within 07:00–17:00.

### 3.4 How a diagnosis round runs (Built)

1. The farmer photographs each block; **DiagnosisCoordinator** checks that each photo shows the right part (leaf or stem base) and asks for a retake if not. The farmer can override.
2. The **photo classifier** scores each photo; block statuses update under the rules above.
3. **Weather** is fetched from data.gov.my (§3.6).
4. **Spread** is computed for **every** diseased block, always, by plain code; it is never left to the AI's discretion.
5. **Treatments** allowed for each diagnosis, with their rain-fast hours, are read from the **rules table**.
6. If more than one block is Harmed, the **Overrun Council** runs: three agents (agronomic urgency, cost feasibility, logistics) argue, and an orchestrator **ranks the blocks**. Its output schema contains only a block, a rank and a short rationale.
7. The **Router agent** arbitrates into one plan per block.
8. **Safety checks** run (§3.5); the plan becomes a **priority action**, a **live feed** of each step, and **Approve/Reject cards** for schedulable actions (spray, drench, clear drain).
9. On Approve, the action is written to **Google Calendar** through the Model Context Protocol (MCP), for the one farm linked to a Google account. Otherwise it is kept in the app.

### 3.5 Safety checks between the AI and the farmer (Built)

| Check | What it does |
|---|---|
| **Rain-fast reconciliation** | Re-times or defers any spray or drench so it falls in a dry window; puts drain clearing first when rain is coming |
| **Rules guard** | Drops recommendations naming a block not on the farm, an unknown action, or a treatment not in the rules table; replaces stale or unreadable dates; restores the rules-table action for any diseased block the AI left untreated. Every correction is logged |
| **Deterministic spread** | Always runs the spread model for every diseased block, so risk figures are never placeholders |
| **Time limit and fallback** | Each AI turn is time-limited (60 s on the cloud deployment). On timeout or error, the plan is built from the rules table alone, and the app says so |
| **Council schema wall** | The Overrun Council's output has no field for a product, dose or time, so it cannot prescribe even if the model tries |
| **Advisor boundary** | The Advisor answers questions from a live snapshot of the farm and the documents; it may repeat the app's plan but never states a dose itself |

### 3.6 Data sources

| Data | Source | Notes |
|---|---|---|
| Rain forecast | data.gov.my weather forecast API (free, government) | The forecast is **qualitative text**; PepperDex maps phrases to rainfall estimates (e.g. "hujan lebat", heavy rain, ≈ 40 mm/day) (*Design*). No live rain-gauge feed was reachable, so **past-week rain is also estimated from forecast text**. A cached snapshot is used, and flagged, if the API is down |
| Farm layout | The farmer's walk, answers and phone sensors | Stored per farm |
| Treatments | Rules table (6 entries, with rain-fast hours) | Drafted from general agronomic guidance for foot rot; citation to specific MPB/DOA documents is **Pending** (§7) |
| Explanations | 23 knowledge documents, in Bahasa Malaysia | Team-compiled summaries of foot-rot agronomy, used only to explain |

### 3.7 Stack (Built)

| Part | Technology |
|---|---|
| App | React Native (Expo), Android 7+; GPS, barometer when present, 3D terrain view |
| Backend | Python, FastAPI, Pydantic v2; one typed contract generates the app's API types |
| Agents | Google Agent Development Kit (ADK) with LiteLLM |
| Language model | **Gemini 2.5 Flash on Vertex AI** (cloud); **Qwen 2.5 14B via Ollama** (offline), switched by configuration only |
| Retrieval | all-MiniLM-L6-v2 sentence embeddings + SQLite FTS5 keyword search |
| Database and files | Cloud SQL (PostgreSQL) in the cloud, SQLite offline; photos in Cloud Storage |
| Calendar | Google Calendar through an MCP server; approval-gated writes |
| Hosting | Google Cloud Run (backend, asia-southeast1); Firebase Hosting (landing page and APK) |

### 3.8 Quality assurance (Built)

- **93 automated backend tests pass** (spread, graph, scheduling, block status, rules guard, council schema, calendar ownership, restore codes, and more). Two further tests exercise the live AI model end to end and need a model running.
- The app is developed against the backend's generated type contract, so request and response shapes cannot silently drift.
- Every tool call and every safety-check correction is logged per run (`tools_called`), giving a traceable record of how each recommendation was made.

---

## 4️⃣ Impact

> **In plain words:** farmers act earlier and at the right time, treatments stop washing away, fewer chemicals reach rivers, and small farms get technology that costs them nothing but the phone they already have.

### 4.1 Theory of change

```
Inputs                  Activities                       Outputs                          Outcomes                          Impact
Phone, photos,     →    Map drainage, project spread, →  One timed action per block,  →   Earlier drain clearing and     →   Fewer vines lost; more income
free forecast,          time treatments, check rules     early warnings, calendar          treatment; fewer wasted sprays     retained; less chemical runoff
official rules                                            entries the farmer approves
```

### 4.2 Expected benefits and the strength of evidence

| Beneficiary | Expected benefit | Evidence strength |
|---|---|---|
| **Farmers: income** | Drainage at the right time is the most effective single measure in the best available study (−24% losses, USD 439/ha) [5]; PepperDex turns it into a dated, per-block instruction | Mechanism supported by [5]; **PepperDex's own effect not yet measured** |
| **Farmers: early action** | Blocks downhill of a case are flagged before symptoms, prompting inspection and drainage | (Built); field accuracy of projections **not yet validated** |
| **Farmers: cost** | No hardware, no fee (under the institutional model), spoken advice | (Built) |
| **Environment** | Sprays moved out of rain windows or deferred, so less fungicide is washed into soil and water | Logical consequence of rain-fast timing (*Design*); not measured |
| **Institutions** | Extension reach to every farm between officer visits; ranked case history during outbreaks; a cross-farm disease picture (**Roadmap**) | (Built) for case history; Roadmap for the rest |
| **Inclusion** | Usable with limited literacy (spoken BM, icons, voice-named blocks); works on low-cost phones | (Built) |

### 4.3 Alignment with the UN Sustainable Development Goals

- **SDG 2, Zero Hunger:** target 2.3, raising the productivity and incomes of small-scale food producers.
- **SDG 15, Life on Land:** reducing chemical runoff through better-timed treatment and drainage.
- **SDG 9, Industry, Innovation and Infrastructure:** target 9.c, increasing access to information and communications technology.

### 4.4 How impact will be measured (pilot design, Roadmap)

| Indicator | Measured as |
|---|---|
| Vine mortality | % of vines lost per season, pilot farms vs comparison farms |
| Wasted applications | Share of sprays followed by ≥ 5 mm rain within the rain-fast period, before vs after |
| Timeliness | Days from first warning to drain clearing or treatment |
| Projection accuracy | Share of *Alerted* blocks later confirmed diseased (calibrates §3.3) |
| Adoption | Active farms per week; share of proposals approved |

---

## 5️⃣ Feasibility

> **In plain words:** it already works and anyone can download it today. It needs no equipment, uses free government data, and the team knows exactly which parts still need testing on real farms.

### 5.1 Technical feasibility: what exists today (Built)

- **Android app build 20**, publicly downloadable from the landing page; a pre-populated **demo farm** lets anyone try the full flow without walking a hillside.
- **Backend live on Google Cloud Run** with Cloud SQL, Gemini 2.5 Flash on Vertex AI, and the Google Calendar connection; a typical Advisor answer returned in about 19 seconds on the cloud deployment.
- **Offline mode:** the same code runs on a laptop with an open-weight model, so the system does not depend on venue connectivity or a single AI provider.
- **Automated tests:** 93 passing (§3.8).
- **Farm portability:** a private restore code moves a farm to a new phone; there are no accounts or passwords.

### 5.2 Operational and economic feasibility

| Factor | Situation |
|---|---|
| Farmer equipment | Their existing Android phone (Android 7+); no sensors to buy. A barometer only makes setup faster |
| Data costs | Weather forecast free (data.gov.my); no paid data feeds on the critical path |
| Running costs | Cloud hosting (one service shared by all farms) + AI model usage per diagnosis or question (§6.5) |
| Language and literacy | Spoken Bahasa Malaysia; icon- and colour-led screens; voice-named blocks |
| Land sensitivity | No boundaries or ownership stored |

### 5.3 Validation status: what is proven, what is not

| Component | Status |
|---|---|
| Software pipeline end to end | **Proven** (Built, deployed, tested) |
| Safety checks and council schema wall | **Proven** by automated tests |
| Spread model | **Working, not field-validated.** Parameters are engineering judgements; all outputs labelled estimates |
| Photo classifier | **Working, weak in the field.** Trained on about 530 original images, largely generated rather than photographed. It scores well on its own test set, but that does not reflect field photos, so it is used only to prompt inspection |
| Rain data | **Working, approximate.** Rainfall is estimated from forecast text; no gauge data; a single forecast location (Kuching) until farm-to-station matching is added |
| Treatment rules citations | **Pending** verification against MPB/DOA documents (§7) |
| Iban language | Interface in Bahasa Malaysia and English; Iban speech is machine-translated and labelled as such; verified Iban pending a native speaker |

### 5.4 Risks and mitigations

| Risk | Likelihood | Mitigation |
|---|---|---|
| Misleading photo result | Medium | Low confidence never lowers a status; photos only trigger inspection; retrain on real Sarawak photos in the pilot |
| Projection wrong for a specific farm | Medium | Always labelled an estimate; farmer's elevation answers override sensors; calibrate on logged outcomes |
| AI error or outage | Low–medium | Rules guard on every plan; rules-only fallback; offline mode; alternative model by configuration |
| Unverified treatment guidance | Medium until resolved | Verify every rule against MPB/DOA documents before any field pilot (§7) |
| Low adoption | Medium | Free to farmers; spoken BM; delivered through extension officers farmers already trust |
| Institution does not subscribe | Medium | Second revenue stream (direct per-farm plans); low running cost; open-weight offline option |

### 5.5 Roadmap

| Phase | Milestones |
|---|---|
| **Now** (built) | One farm, one disease; agents, council and calendar; public app and cloud backend |
| **Next** | Verify the rules table with MPB/DOA; retrain the classifier on real field photos; match each farm to its nearest weather station; field pilot with a DOA district office or MPB; officer escalation; verified Iban |
| **Then** | Multi-farm extension-officer view; neighbour-alert review and sending (alerts are drafted today, never auto-sent) |
| **Later** | Calibrate spread parameters on logged outcomes |
| **Beyond** | Other crops on the same terrain engine |

---

## 6️⃣ Business Model

> **In plain words:** the farmer uses PepperDex for free. The organisations whose job is to support farmers, and who gain when farms are healthy, pay a yearly subscription that covers running and maintaining it. Growers who aren't covered can subscribe themselves, per farm.

### 6.1 Customers and users

| Segment | Role | Value proposition | Size / basis |
|---|---|---|---|
| **Pepper smallholders** | **Users** | Early warning, one timed action per block, spoken advice, at no cost | 38,587 in Sarawak [4] |
| **DOA Sarawak** (agricultural extension) | **Paying customer** | Reach every farm between officer visits with consistent, rules-based advice; outbreak cases flagged to officers (Roadmap) | State agency |
| **Malaysian Pepper Board (MPB)** | **Paying customer** | Protect production in a state producing >98% of national pepper [1]; grower registration as a distribution channel | National board |
| **Estates and cooperatives** | **Paying customer** | One subscription for all their farms or members; multi-farm view (Roadmap) | To be sized in pilot |
| **Private / commercial growers** not covered by an institution | **Paying user** | The same app on a direct plan | To be sized in pilot |

### 6.2 How institutions and farmers connect (B2B2C)

```
Institution ──pays annual subscription──▶ PepperDex (software maintenance + AI usage)
     ▲                                              │
     │ healthier farms, protected output,            │ free app: early warning,
     │ case history, cross-farm view (Roadmap)       │ one timed action per block
     └────────────────────────────────────────── Farmers
```

Institutions already advise and register pepper farmers. PepperDex extends that reach to every farm, so the body that benefits from healthier farms pays, and farmers adopt without a cost barrier. Smallholders farm about 0.2 ha on average (§1.1), so charging them directly would be the biggest obstacle to adoption.

### 6.3 Revenue model

> **An annual subscription for institutions (DOA, MPB, estates and cooperatives) covering software maintenance and AI usage (tokens), so their farmers use PepperDex free; private growers can subscribe directly on a per-farm plan.**

**Pricing approach (cost-plus, per farm per year):**

`price per farm ≈ (AI usage per farm + hosting share per farm + maintenance share per farm) × (1 + margin)`

- *AI usage per farm* = diagnosis rounds and Advisor questions per year × tokens per interaction × model price per token.
- *Hosting share* = the cloud service's fixed monthly cost ÷ number of farms served. It **falls as more farms join**.
- *Maintenance share* = rules-table updates, app releases and support, spread across subscribed farms.

No price is quoted until the per-farm cost is measured from actual cloud billing during the pilot (*Pending*).

### 6.4 Channels and go-to-market

1. **Pilot:** one DOA district office or MPB programme, a small group of farms, measuring the indicators in §4.4.
2. **Institutional rollout:** subscription for registered growers, onboarded by the extension officers who already visit them.
3. **Direct plans:** private and commercial growers subscribe per farm through the landing page.
4. **Expansion:** additional crops and regions on the same terrain engine.

### 6.5 Cost structure

| Cost | Behaviour |
|---|---|
| Cloud hosting (backend, database, storage) | Mostly fixed; shared by all farms |
| AI model usage | Variable; scales with diagnoses and questions; can shift to the open-weight model to cut cost |
| Maintenance and rules updates | Semi-fixed; team time |
| Farmer hardware and data feeds | **None** |

### 6.6 Sustainability and defensibility

- **Revenue scales with usage:** the variable cost (AI usage) is exactly what the subscription recovers.
- **Two revenue streams** (institutional and direct) reduce dependence on any single customer.
- **Neutrality policy:** no agrochemical advertising or product placement, so the advice stays trustworthy to both institutions and farmers.
- **Defensibility:** the combination of terrain model, rule-bound agents, local language and institutional distribution is harder to copy than any single feature.

> **Status:** this is the team's **proposed** model. No agreement with DOA, MPB or any estate exists yet; a pilot is the next step.

---

## 7. Limitations and open verification items

Listed in one place so nothing is overstated.

| # | Item | Current state | Action needed |
|---|---|---|---|
| 1 | **Treatment rules citations** | 5 of 6 rules carry `_verified_pending: true`: doses and timings were drafted from general agronomic guidance, not yet checked against specific MPB/DOA documents | Verify each rule and page reference with MPB/DOA before any field use or formal claim that rules are "from MPB/DOA" |
| 2 | **Drainage rule source label** | The drainage rule's source text says "MPB/DOA field study", but the 24% figure comes from the India study [5] | Correct the `source_ref` in `backend/seed/rules.json` to [5] |
| 3 | Sarawak-specific loss data | None found; Indian study used as indicative [5] | Seek MPB/DOA or UNIMAS data; measure in the pilot |
| 4 | Spread model parameters | Engineering judgement, not calibrated | Calibrate on pilot outcomes (§4.4) |
| 5 | Photo classifier | Trained on ~530 mostly generated images; not field-validated | Collect and label real Sarawak field photos; retrain |
| 6 | Rainfall input | Estimated from forecast text; single location (Kuching); no gauge data | Match farms to nearest stations; add gauge data where available |
| 7 | Competitor comparison | Team review of public descriptions | Re-confirm each tool's features before formal submission |
| 8 | Iban language | Machine-translated speech, unverified | Native-speaker verification |
| 9 | Business model | Proposed; no institutional agreement | Pilot discussions with DOA / MPB |
| 10 | Knowledge documents | Team-compiled summaries, not individually cited | Attach sources to each document |

---

## 8. Glossary

| Term | Plain meaning |
|---|---|
| **Foot rot / quick wilt** | A deadly disease of pepper vines that rots the stem base and roots |
| ***Phytophthora capsici*** | The water mould (oomycete) that causes foot rot; lives in soil, moves in water |
| **Collar / collar lesion** | The stem base at soil level / a dark rotting patch there, the earliest visible sign |
| **Block** | A section of a farm the farmer marks and names during setup |
| **Directed elevation graph** | A map of blocks with arrows pointing only downhill, showing where water can flow |
| **Rain-fast period** | Dry hours a treatment needs after application so rain doesn't wash it off |
| **Rain pulse** | A heavy rain event that can move the disease a step further downhill |
| **Deterministic** | Always gives the same output for the same input; plain calculation, not AI |
| **AI agent** | An AI helper with one job that can call tools (e.g. the weather or spread model) |
| **Router agent** | The coordinating agent that weighs all the evidence and decides the plan |
| **Overrun Council** | Three AI agents plus an orchestrator that rank which sick block to treat first when more than one is Harmed |
| **MCP (Model Context Protocol)** | A standard way for AI software to use outside tools, here Google Calendar |
| **ONNX** | A portable file format for running a trained image model |
| **NCR land** | Native Customary Rights land in Sarawak, where boundaries are legally sensitive |
| **B2B2C** | Business-to-business-to-consumer: an organisation pays so the end user gets the service |

---

## References

1. Edward, C. (2025, December 2). Pepper industry to be enhanced with new tech, 10,000ha expansion plan. *Borneo Post*. https://www.theborneopost.com/2025/12/02/pepper-industry-to-be-enhanced-with-new-tech-10000ha-expansion-plan/
2. Izzah, A. H., & Wan Asrina, W. Y. (2019). Black pepper in Malaysia: An overview and future prospects. *Agricultural Reviews, 40*(4), 296–302. https://doi.org/10.18805/ag.R-129
3. Granke, L. L., Quesada-Ocampo, L., Lamour, K., & Hausbeck, M. K. (2012). Advances in research on *Phytophthora capsici* on vegetable crops in the United States. *Plant Disease, 96*(11), 1588–1600. https://doi.org/10.1094/PDIS-02-12-0211-FE
4. Umpang, M. (2026, May 19). Sarawak still nation's largest pepper-producing region with 8,061 hectares cultivated. *Borneo Post*. https://www.theborneopost.com/2026/05/19/sarawak-still-nations-largest-pepper-producing-region-with-8061-hectares-cultivated/
5. Bhat, S., Arunachalam, V., Paramesha, V., & Gaonkar, N. (2025). Quantifying the economic impact and management strategies for foot rot (*Phytophthora capsici* L.) disease on black pepper cultivation in West Coast India: Farm-level insights. *Plant Science Today, 12*(1). https://doi.org/10.14719/pst.6764

*All references were checked against the publisher or news page on 25 September 2026. Technical claims marked (Built) were checked against the source code (`backend/app/tools/spread.py`, `graph.py`, `treatment.py`, `weather.py`, `scheduling.py`, `council.py`, `knowledge.py`; `backend/app/agent/runner.py`; `backend/seed/rules.json`) on the same date.*
