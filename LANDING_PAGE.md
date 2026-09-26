# PepperDex Sarawak: AI Early Warning System for Sarawak Black Pepper
> **Header asset:** `pepperdex-workspace\pitch-and-design\PepperDex_Logo.png` — replaces the previous wordmark everywhere on this page, including the hero banner.
>
> **Content status (team note, not rendered):** updated 2026-09-24 to match the v2 app as built (APK v13). On-device verification of v13 is still pending; items marked ⚠ have not yet been confirmed on a phone. Anything not built is labelled **Roadmap** — never present it as a working feature.

*“Dari hulu ke hilir — sebelum penyakit sampai” (From upstream to downstream — before the disease arrives)* [1]

**Shortcuts** (see §8): GitHub repository · API documentation · Demo video · Download the Android app (QR)

---

## 1. Project Problem Statement: The Sarawak Pepper Crisis

Sarawak is the undisputed heart of Malaysia’s pepper industry, accounting for **over 98% of the nation’s pepper production** [2] across **36,682 registered smallholder farms** [2]. Because black pepper vines are highly sensitive to waterlogged soil, farmers in this undulating region deliberately plant their crops on **steep hill slopes** to ensure natural drainage [4]. However, this specific terrain has created an extreme systemic vulnerability to **Phytophthora foot rot** (caused by the pathogen *P. capsici*), the crop's most destructive disease [2].

The pathogen is soil-borne and water-driven; because of gravity, **the deliberate downhill runoff of water becomes a literal highway for the disease** [2, 4]. When an outbreak strikes, it causes **over 30% vine mortality and crop loss** [2], resulting in a devastating financial blow of **USD 902 per hectare**—effectively wiping out **56% of a smallholder’s annual net returns** [2].

The fundamental issue is that Phytophthora foot rot is **"a catchment-scale disease, fought with single-plant tools"** [3]. Because the pathogen spreads via downhill water flow, an infection on an upslope plot is essentially a scheduled arrival on the plots below [2]. Despite this highly predictable, terrain-linked transmission path, existing agricultural tools only evaluate individual plants or single farms in isolation [3]. This technical gap leaves rural growers exposed to **three compounding failures**:

*   **Late-Stage Detection:** The pathogen attacks the roots and collar first [3]. By the time visible symptoms like foliar yellowing or wilting appear on the leaves, the vine is already lost [3], and rural growers have limited access to extension advice [3].
*   **Catchment Blindness:** Because the disease is soil-borne and water-driven, transmission crosses property boundaries [3]. Farmers have no visibility beyond their own land; they cannot tell whether an upslope crop is infected or whether contaminated runoff is headed for their block next [3].
*   **Fungicide Guesswork & Wasted Capital:** Contact fungicides are effective, but they wash off easily in heavy tropical rain [3]. Spraying even two days before a major downpour washes the expensive chemical into the soil [3].

Traditional agricultural technologies are designed for flat-land plantation agriculture and ignore terrain topography [4]. In Sarawak, **"water, not proximity, determines exposure."** [12, 37]

---

## 2. Proposed Solution: PepperDex Sarawak

**PepperDex** is a terrain-aware, agentic early warning system for Sarawak's smallholder black pepper farms [1]. Existing tools diagnose a single plant; PepperDex models **where the disease travels next, and when** — because foot rot moves downhill through water in rain pulses, not continuously [6, 12]. It runs as an Android app on an ordinary phone: no hardware purchase, spoken output, tap-based setup.

### Methodology — how a decision is made

PepperDex combines four kinds of evidence and refuses to let any single one decide alone:

| Evidence | Source | What it contributes |
|---|---|---|
| **What is on the vine** | L1 — photo classifier (MobileNetV3-Small, `.onnx`) | Per-block class + confidence; low confidence means "go and inspect", never a diagnosis |
| **Where water carries it** | L2 — deterministic downhill graph of the farm's blocks | Risk %, arrival estimate in days, and the path — labelled as estimates, not measurements |
| **When rain comes** | data.gov.my forecast (qualitative text mapped to an mm estimate; cached fallback is flagged) | The next rain pulses and the rain-free windows |
| **What treatment is allowed, and when it holds** | L3 — rules table from MPB and DOA Sarawak guidance (6 treatments, with rain-fast hours) | The only source of product, dose and timing |

An AI agent (L4) arbitrates these into **one action, one time, one reason** — e.g. *“Clear the drain today. Drench Thursday morning.”* Around the agent sit deterministic safety checks, so a model mistake cannot reach the farmer as advice:

*   **Rain-fast check** — a spray or drench is re-timed to the real rain-free window, or deferred with a drain-clearing step first.
*   **Rules check** — the agent's plan is compared with the rules table. Invalid blocks, unknown products and stale dates are dropped, and an untreated diseased block gets its rules-table action back. Every correction is logged.
*   **Real spread numbers** — the spread model is deterministic, so it is always run for every diseased block; risk figures are never placeholders.
*   **Fallback** — if the AI model is slow or fails, the decision is made from the rules table alone, and the app says so openly.

### Block states — what the farmer sees change

| State | Set by | Rule |
|---|---|---|
| **Protected** | A confident healthy diagnosis, or no risk at all | An unsure (<60%) or unrelated photo never lowers a state |
| **Alerted** | The spread model, with no photo of that block needed | Projection can raise a block, never lower it |
| **Harmed** | A direct diagnosis of collar lesion or defoliation/wilt | Diagnosis always overrides projection |
| **Overrun** | Farm-wide: more than one block Harmed at once | Triggers the Overrun Council |

### The five layers

*   **L0 — Voice & Language:** Advice, agent messages and the rain forecast can be heard aloud in Bahasa Malaysia (tap to hear). Farmers record a spoken name for each block, which is stored and replayed — never transcribed. The interface is Bahasa Malaysia or English; Iban speech is machine-translated and says so, and Iban text falls back to Bahasa Malaysia until a native speaker verifies it.
*   **L1 — Photo Diagnosis:** A lightweight MobileNetV3-Small classifier, run on the server (`.onnx`), trained to catch **collar lesions** — the earliest visible sign of foot rot [11, 15] — before leaf yellowing. A photo that doesn't match the requested target (leaf vs stem base) prompts a retake; the farmer can always override.
*   **L2 — Terrain-Aware Spread:** Blocks become nodes in a directed downhill graph built from the setup walk (GPS, plus barometric pressure on phones that have a barometer). The farmer's own answer about which block is higher always wins over the sensors. From a confirmed case, the graph projects risk, path and arrival time for every downslope block [12, 13].
*   **L3 — Knowledge:** The rules table decides *what* (product, dose, rain-fast timing). A searchable knowledge base of 23 disease-management documents (semantic + keyword search) explains *why* — it can never decide *what* [14, 27].
*   **L4 — Agent Orchestration:** A RootAgent arbitrates; loop agents run setup and the photo round; an Advisor answers questions from the farm's own records; an Overrun Council ranks blocks during an outbreak; a Google Calendar connection (MCP) schedules approved actions. Details in §6.

---

## 3. Target Users

### 1. Primary Users: Sarawak Pepper Smallholders
The local farmers driving Malaysia’s national pepper industry [2] — highly exposed to crop loss and unserved by expensive agricultural technology [2, 26].

*   **Socio-Economic Profile:** Over **36,682 registered smallholders** manage these sloped plots, representing **98% of Malaysia's pepper production** [2]. A single outbreak can wipe out **56% of annual net returns** (USD 902/ha) [2].
*   **Accessibility & Language Barriers:** Many rural smallholders face literacy challenges and communicate primarily in local languages [7, 10].
*   **Technology Constraints:** No budget for IoT soil sensors [26]; they rely on **ordinary Android smartphones** and patchy highland connectivity [7, 10].
*   **NCR Land Trust Sensitivities:** Much Sarawak pepper is farmed on **Native Customary Rights (NCR) land** [26], where land boundaries are legally sensitive and apps that record them are distrusted [26].

**How PepperDex adapts to them:** no hardware purchase, tap-based setup, spoken advice [7, 21]. **No land boundaries or ownership records are ever saved** — only the relative elevation order and spacing of blocks, which is all the water model needs [26]. There are no accounts or passwords: a phone is linked to its farm, and a private restore code moves the farm to a new phone.

### 2. Secondary Users: Agricultural Extension Officers (DOA Sarawak & MPB)
Field officers and researchers from the **Department of Agriculture (DOA) Sarawak** and the **Malaysian Pepper Board (MPB)**.

*   **Overrun triage (built):** When more than one block is Harmed at once, PepperDex's Overrun Council ranks which block to treat first — ranking only, never a treatment [13]. Every step the agents took is recorded, giving a readable case history.
*   **Roadmap — officer escalation:** sending that ranked case history to a DOA officer, so they arrive with the file in hand [13].
*   **Roadmap — the missing record:** each farm already stores its diagnoses, rain, spread projections and actions. Anonymised aggregation into the first Sarawak dataset linking terrain, rainfall, treatment timing and outcome is future work [7, 36].
*   **Roadmap — extension-officer view:** catchment-level clustering across farms, so an officer can warn a whole valley before the runoff arrives [8, 36].

---

## 4. Sarawak Use Case: Why This Region is the Ultimate Testing Ground

Sarawak is not merely one pepper-growing region among many — it is the lifeblood of Malaysia's national pepper industry [4].

### 1. The National Pepper Monolith (High Economic Concentration)
*   **Production Dominance:** Sarawak accounts for **over 98% of Malaysia’s black pepper production** [2].
*   **Geographical Indication (GI):** Sarawak pepper holds official **Geographical Indication status since 2003** along with a statutory grading scheme [4].
*   **Smallholder Density:** The industry is powered by **36,682 registered pepper farmers** [2].

### 2. The Topographic Paradox (Slopes as Pathways)
*   **The Sloped Drainage Strategy:** Farmers deliberately plant on **steep hill slopes** to ensure natural drainage [4].
*   **The Pathogen Highway:** Because of gravity, **the deliberate downhill runoff of water becomes a literal highway for the disease** [2, 4].
*   **Predictable Gravity Vectors:** Transmission has a **consistent, predictable downhill direction** [2, 12] — exactly what a directed downhill graph (L2) models [12].

### 3. The Rain Pulse Mechanic (Climatological Catalyst)
*   **Rain Pulse Spread:** Foot rot spreads in **distinct rain pulses**, not continuously [6].
*   **Shift to Active Readiness:** The question is not *"did we catch it?"* but **"what happens at the next rain, and is the farm ready?"** [6]. PepperDex stays useful on a farm with **zero photos taken** — the rain forecast and the Advisor work from day one [6, 13].

### 4. Native Customary Rights (NCR) Land Sensitivities
*   **Legal & Social Sensitivity:** NCR land boundaries are historically complex and highly sensitive [26].
*   **Privacy-First Mapping:** PepperDex **never records land boundaries or ownership** [26] — only the relative order and spacing of blocks.

---

## 5. UN SDG Alignment

### Goal 2: Zero Hunger
*   **Target Focus:** Target 2.3 — Double the agricultural productivity and incomes of small-scale food producers.
*   **PepperDex’s Contribution:** Foot rot causes **over 30% vine mortality**, costing **USD 902 per hectare** and **56% of annual net returns** [2]. Independent farm-level analysis found that good drainage reduced foot rot losses by **24% (USD 439/ha)** — more than the 20% from fungicide alone [8]. PepperDex turns that general advice into a dated, per-block instruction [9].

### Goal 15: Life on Land
*   **Target Focus:** Target 15.9 — Integrate ecosystem and biodiversity values into national and local planning.
*   **PepperDex’s Contribution:** Spraying inside the rain-fast window flushes fungicide into soil and rivers [3]. PepperDex re-times or defers every spray and drench to a rain-free window, and puts drain clearing first when rain is coming [14, 25], reducing chemical runoff into Sarawak’s ecosystems [8, 9].

### Goal 9: Industry, Innovation, and Infrastructure
*   **Target Focus:** Target 9.c — Increase access to information and communications technology.
*   **PepperDex’s Contribution:** Multi-agent AI, computer vision and terrain modelling delivered on an ordinary Android phone, with **no hardware purchase** [7, 10], using free government weather data.

---

## 6. The AI Component: Agent Architecture

PepperDex is a **hybrid system**: machine learning where it is reliable (the photo classifier), deterministic models where safety matters (spread graph, rules table, rain-fast arithmetic), and language-model agents to arbitrate between them and talk to the farmer.

```
RootAgent (arbitrator) ─────────────────────────────────────────────
├── Deterministic tools   get_weather · compute_spread · get_treatment
│                         find_spray_window · query_farm_history
├── SetupCoordinator      loop agent — guides the setup walk (bounded)
├── DiagnosisCoordinator  loop agent — the block-by-block photo round
├── Advisor               answers questions from the farm's records + knowledge base
├── Overrun Council       only when >1 block is Harmed:
│      Agronomic Urgency · Cost Feasibility · Logistics → Council Orchestrator
│      (ranks blocks only — its output format has no field for a treatment)
└── Google Calendar (MCP) read: check free slots · write: only after the farmer approves
```

### The agents

*   **RootAgent — the arbitrator.** Calls the tools, weighs weather, spread and rules, and outputs one plan per affected block. Every tool call is logged, so each recommendation has a traceable "how this was decided".
*   **DiagnosisCoordinator — the photo round.** Walks the farmer block by block, checks each photo matches the target (leaf or stem base), prompts a retake if not (the farmer can always override), and reports the results per block when the round is complete.
*   **SetupCoordinator — the setup walk.** Guides the farmer through marking blocks and answering "which is higher?" questions until a valid downhill graph exists.
*   **Advisor — the farm's memory.** Answers free-form questions (*"Are my blocks safer now?"*) using a live snapshot of the farm: every block's state, the latest and previous diagnosis, the current plan, projected spread, rain, and schedule proposals — plus the recent conversation. General questions are answered from the knowledge base. It may repeat the app's plan, but never states a dose or product itself.
*   **Diagnosis-necessity check.** Typing `/diagnose` gets a verdict on whether a new photo round is worth doing, from rain since the last check and the blocks' states. It is a deterministic rule, not a model — and it never blocks the farmer from starting one anyway.
*   **Overrun Council — triage during an outbreak.** Three agents argue from different angles (agronomic urgency, cost, logistics) and an orchestrator ranks the blocks. It can re-order; it can never add a treatment, dose or timing.
*   **Google Calendar via MCP — schedules with consent.** After a decision, each schedulable action (spray, drench, drain clearing) becomes a **proposal card**. Nothing is written to a calendar until the farmer taps Approve on that card; the agent itself can only *read* the calendar, to avoid clashes.

### The agents, visible — the live activity feed

A diagnosis is not a spinner. After the photo round, the Advisor chat shows each agent's real step as it happens, each under its own name and icon: the photo results, the council's debate (if Overrun), rainfall, the spread projection, the approved treatments and rain-free window, any rules-check correction, the decision, and finally the schedule proposals waiting for approval. Every message comes from something that actually happened — a tool result or a council transcript — never a model describing itself afterwards. Tap any message to hear it.

### The orchestration in action (the core moment) [20]
1.  **L1** detects a `collar_lesion` on an upslope block [20].
2.  **L2** projects runoff carrying the pathogen to a downslope block within ~4 days [20].
3.  **L3** returns the approved drench, which needs a 24-hour rain-free window [20].
4.  **Weather** forecasts a heavy downpour tomorrow [20].

The RootAgent defers the drench, orders drain clearing today, and schedules the drench for the first rain-free morning. The farmer sees it arrive in the chat, approves the calendar proposal, and hears: **“Clear the drain today. Drench Thursday morning.”** [20]

### Built for the field, not the lab
*   **Local or cloud, same code:** a local open-weight model (Qwen 2.5 14B via Ollama) on a laptop, or Gemini on Cloud Run — one configuration line apart.
*   **Never stuck:** each AI turn is time-limited; on timeout the rules-table path decides and the app says so.
*   **Honest numbers:** every risk figure is labelled an estimate; the weather card says when it is showing cached data.

---

## 7. User Flow

1.  **Open the app.** A new phone offers three ways in: **Try the demo farm** (a ready-made farm with diagnoses, agents and 3D terrain), **Set up my farm**, or **Restore my farm** (a private code from Settings on the old phone).
2.  **Set up once.** Register (the phone checks for a barometer automatically), then walk the farm: at each block, tap to mark it, take a photo and record its spoken name. A live map shows your walk and every marked block, with a live position and altitude readout. Answer a few "which block is higher?" questions — your answer always wins — and the downhill graph is built.
3.  **Home, from day one.** The **rain card** shows the coming rain pulses from the official forecast (up to 7 days); the **Priority action card** shows the one thing to do next with its metrics (risk, confidence, arrival, rain); the **Advisor card** says whether a diagnosis is due. All of this works with zero photos.
4.  **Ask the Advisor.** Type `/diagnose` for a verdict, or ask anything about your farm. Tap **Begin Diagnosis** whenever you like.
5.  **Photograph each block.** DiagnosisCoordinator guides you block by block; a wrong-target photo prompts a retake.
6.  **Watch the agents work.** The chat fills with each agent's step, then the decision — one action, one time, one reason per block.
7.  **Approve the schedule.** Proposal cards appear; tap **Approve** to add an action to Google Calendar (on the team's linked phone) or keep it in the app, or **Reject** it.
8.  **See the farm change.** Home cards update from the new run; on the **Farm** tab, blocks change colour — Harmed from a diagnosis, Alerted from the projection downhill. ⚠ 3D terrain view pending on-device confirmation in v13.
9.  **Follow up.** Ask *"Does this mean my blocks are safer now?"* — the Advisor compares this round with the last one for your blocks.

---

## 8. Shortcuts (landing page buttons)

| Button | Target |
|---|---|
| **GitHub repository** | `https://github.com/nathanyap17/huluhilir` (repo keeps its original name; README is PepperDex) |
| **API documentation** | `https://huluhilir-api-mfrzixfqeq-as.a.run.app/docs` (same Cloud Run service, v2 contents) |
| **Demo video** | *(link to be added when the video is published)* |
| **Download the Android app** | QR code + link to the latest `.apk` on this site (fixed name `pepperdex-latest.apk`). Android only; allow "install unknown apps" for the browser when prompted. |

Site: `https://sfws-aicc-workspace-1.web.app/` — the same address printed on the bunting QR.
