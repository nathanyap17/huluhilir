# HuluHilir: AI Early Warning System for Sarawak Black Pepper
*“Dari hulu ke hilir — sebelum penyakit sampai” (From upstream to downstream — before the disease arrives)* [1]

---

## 1. Project Problem Statement: The Sarawak Pepper Crisis

Sarawak is the undisputed heart of Malaysia’s pepper industry, accounting for **over 98% of the nation’s pepper production** [2] across **36,682 registered smallholder farms** [2]. Because black pepper vines are highly sensitive to waterlogged soil, farmers in this undulating region deliberately plant their crops on **steep hill slopes** to ensure natural drainage [4]. However, this specific terrain has created an extreme systemic vulnerability to **Phytophthora foot rot** (caused by the pathogen *P. capsici*), the crop's most destructive disease [2]. 

The pathogen is soil-borne and water-driven; because of gravity, **the deliberate downhill runoff of water becomes a literal highway for the disease** [2, 4]. When an outbreak strikes, it causes **over 30% vine mortality and crop loss** [2], resulting in a devastating financial blow of **USD 902 per hectare**—effectively wiping out **56% of a smallholder’s annual net returns** [2]. 

The fundamental issue is that Phytophthora foot rot is **"a catchment-scale disease, fought with single-plant tools"** [3]. Because the pathogen spreads via downhill water flow, an infection on an upslope plot is essentially a scheduled arrival on the plots below [2]. Despite this highly predictable, terrain-linked transmission path, existing agricultural tools only evaluate individual plants or single farms in isolation [3]. This technical gap leaves rural growers completely exposed to **three compounding failures**:

*   **Late-Stage Detection:** The pathogen attacks the roots and collar first [3]. By the time visible symptoms like foliar yellowing or wilting appear on the leaves, the vine is already lost [3], and rural growers have limited access to extension advice [3].
*   **Catchment Blindness:** Because the disease is soil-borne and water-driven, transmission crosses property boundaries [3]. Currently, farmers have zero visibility beyond their own land; they have no way of knowing if an upslope neighbour’s crop is infected or if contaminated runoff is headed straight to wipe out their block next [3]. 
*   **Fungicide Guesswork & Wasted Capital:** Contact fungicides are effective, but they wash off easily in heavy tropical rain [3]. Because farmers cannot accurately time their applications around rainfall windows, spraying a crop even two days before a major downpour washes the expensive chemical directly into the soil, wasting precious capital [3].

Traditional agricultural technologies fail because they are designed for flat-land plantation agriculture and completely ignore terrain topography [4]. In Sarawak, **"water, not proximity, determines exposure."** [12, 37] Without a terrain-aware system, smallholders are left fighting a collective watershed threat in complete isolation [4].

---

## 2. Proposed Solution: HuluHilir

**HuluHilir** is a terrain-aware, agentic early warning system designed specifically for Sarawak's smallholder black pepper farms [1]. Moving away from reactive, single-plant treatments, HuluHilir treats pepper disease as a collective watershed challenge [3, 33]. By modeling how gravity and rain move water across sloped farmlands, the system provides smallholders with the exact spatial foresight and precise timing they need to protect their crops before the pathogen ever reaches their soil [1, 33]. Operating entirely on low-spec Android phones with zero hardware purchases, typing, or literacy barriers [7], HuluHilir turns a devastating shared environmental risk into an active, coordinated community defense [8].

### The Five-Layer Architecture

The intelligence and accessibility of HuluHilir are driven by a cohesive five-layer architecture [10]:

*   **L0 — Voice and Language Layer (Zero-Adoption Barriers):** Every interaction in the app is wrapped in speech [10]. Text-to-speech reads every prompt, diagnosis, and recommendation aloud in Bahasa Malaysia, heavily utilizing local **Sarawak Malay and Iban terms** [10]. To bypass fragile off-the-shelf Speech-to-Text models for indigenous languages, farmers simply record short voice labels for their land blocks, which are stored and replayed as audio files [10].
*   **L1 — On-Device CNN Diagnosis (Earliest Warning):** A lightweight, transfer-learned image classifier runs directly on the farmer's mobile phone [11]. It screens photos of the vine’s leaves and stem base [11]. Crucially, it is trained specifically to detect **collar lesions**—the dark, water-soaked tissue at the base of the stem that serves as the absolute earliest visible signature of foot rot [11, 15]—long before leaf yellowing or wilting sets in.
*   **L2 — Terrain-Aware Spread Projection (The Downhill Water Graph):** Plots are modeled as nodes in a directed graph ordered by relative elevation; edges represent downslope water pathways [12]. By integrating local weather API forecasts, HuluHilir models water-driven pathogen movement downhill [12]. If an infection is confirmed on an uphill block, the system automatically calculates the risk level, downhill path, and arrival time for every downslope plot in its path [12, 13].
*   **L3 — Treatment Knowledge (RAG + Rules):** The system maintains a deterministic rules table containing approved pesticide types, exact dosing, and **rain-fastness windows** curated from the Malaysian Pepper Board (MPB) and Department of Agriculture (DOA) Sarawak guidelines [14]. No AI hallucination is permitted here: the LLM is tightly bound to this database and cannot recommend any treatment or dosage absent from this verified lookup table [14, 27].
*   **L4 — Intelligent Agent Orchestration (The Decision Arbitrator):** A central LLM Root Agent orchestrates specialized sub-agents to resolve contradictory data [14, 16]. For example, if a vine shows infection (urging immediate spraying), but the weather forecast predicts heavy downpours tomorrow (which would wash the fungicide away), HuluHilir's agent holds all of these realities simultaneously to issue a single, logical, and sequenced instruction: **“Clear the drain today. Spray Thursday morning.”** [18, 20]

---

## 3. Target Users

HuluHilir is designed to bridge the gap between rural fields and institutional support, serving two critical user groups within Sarawak's agricultural ecosystem.

### 1. Primary Users: Sarawak Pepper Smallholders
These are the local farmers driving Malaysia’s national pepper industry [2]. They are highly vulnerable to crop loss but are completely unserved by expensive, high-tech agricultural tools [2, 26].

*   **Socio-Economic Profile:** Over **36,682 registered smallholders** manage these sloped plots, representing **98% of Malaysia's pepper production** [2]. Operating on thin margins, a single outbreak of foot rot wipes out **56% of their annual net returns** (USD 902/ha) [2].
*   **Accessibility & Language Barriers:** Many rural smallholders face literacy challenges and communicate primarily in local languages [7, 10]. 
*   **Technology Constraints:** Farmers cannot afford expensive IoT soil sensors or hardware [26]. They rely entirely on **low-spec Android smartphones** and frequently encounter spotty cellular connectivity in remote highland areas [7, 10].
*   **NCR Land Trust Sensitivities:** A large portion of Sarawak pepper is farmed on **Native Customary Rights (NCR) land** [26]. Because land boundaries are a highly sensitive legal subject on NCR lands, growers are deeply distrustful of applications that track GPS boundaries or record land ownership [26].

**How HuluHilir adapts to them:** 
The application requires **zero hardware purchases, zero typing, and zero reading literacy** [7, 21]. Every interaction is wrapped in speech, reading diagnoses and advice aloud in Bahasa Malaysia, utilizing local **Sarawak Malay and Iban terms** [10]. To protect farmer trust, **no land boundaries or ownership records are ever saved**—the system only models the relative elevation order of blocks to project water flow, completely bypassing NCR land mapping sensitivities [26].

### 2. Secondary Users: Agricultural Extension Officers (DOA Sarawak & MPB)
These are field officers and researchers from the **Department of Agriculture (DOA) Sarawak** and the **Malaysian Pepper Board (MPB)**. While they do not use the app daily in the fields, aggregating and analyzing individual farmer plots directly solves their biggest operational constraints.

#### How analyzing farmer plots helps DOA Sarawak and MPB:
*   **Automated Field Triage (Extending Limited Officer Capacity):** Extension officers are severely understaffed relative to the tens of thousands of geographically isolated smallholders. When a farmer’s plot enters an **"Overrun" state** (most blocks infected), HuluHilir automatically shifts from local prevention to triage [13]. It ranks the remaining blocks by salvageability and **escalates the case to DOA officers with a documented digital history** of the outbreak [13]. Officers no longer waste travel time on post-hoc diagnostics; they arrive at remote locations with a complete digital case file already in hand [13].
*   **Building the First Regional Dataset ("The Missing Record"):** There is currently no historical field record linking Sarawak’s steep topography, rain pulses, and actual crop outcomes. By analyzing individual plots, HuluHilir silently accumulates the **first Sarawak dataset linking terrain, rainfall, treatment timing, and success rates** [7]. MPB and DOA can use this aggregated, anonymized data to see exactly which treatments succeeded or washed away in heavy rain, allowing them to optimize national agricultural guidelines based on real-world evidence [36].
*   **District-Level Clustering (The "Extension-Officer View"):** Because Phytophthora is water-driven, transmission respects terrain slopes rather than property lines [2]. Plot-level data allows HuluHilir to unlock a macroscopic **"Extension-officer view"** across multiple smallholder farms [36]. Agencies can visualize disease transmission paths across an entire catchment [36]. Instead of reacting to isolated, single-farm complaints, officers can identify downhill pathogen pathways and **proactively warn an entire valley** before the contaminated runoff ever reaches their crops [8, 36].

---

## 4. Sarawak Use Case: Why This Region is the Ultimate Testing Ground

Sarawak is not merely one pepper-growing region among many—it is the absolute lifeblood of Malaysia's national pepper industry [4]. The geographic, environmental, and socio-economic realities of Sarawak make it both the most critical and the most scientifically viable environment to deploy HuluHilir [4]. 

### 1. The National Pepper Monolith (High Economic Concentration)
Sarawak represents the perfect geographic focus for a targeted, high-impact agtech intervention:
*   **Production Dominance:** Sarawak accounts for **over 98% of Malaysia’s entire black pepper production** [2]. 
*   **Geographical Indication (GI):** Sarawak pepper is a premium global product, holding official **Geographical Indication status since 2003** along with a statutory grading scheme [4]. 
*   **Smallholder Density:** The industry is powered by **36,682 registered pepper farmers** [2]. Because the crop is so highly concentrated in this single state, success here effectively secures the entire national industry.

### 2. The Topographic Paradox (Slopes as Pathways)
The physical layout of Sarawak's farms creates a unique, highly predictable transmission pathway that traditional agricultural tools cannot model:
*   **The Sloped Drainage Strategy:** Because black pepper vines are highly sensitive to waterlogged soil, farmers in Sarawak's undulating terrain deliberately plant their crops on **steep hill slopes** to ensure natural drainage [4].
*   **The Pathogen Highway:** This exact terrain design creates a dangerous paradox. *Phytophthora capsici* (foot rot) is a water-driven, soil-borne pathogen [2, 3]. Because of gravity, **the deliberate downhill runoff of water becomes a literal highway for the disease** [2, 4]. 
*   **Predictable Gravity Vectors:** Unlike flat-land plantation diseases that spread in random radiuses, transmission in Sarawak has a **consistent, predictable downhill direction** [2, 12]. This makes Sarawak the perfect place to deploy a **directed downhill water graph model (L2)** [12].

### 3. The Rain Pulse Mechanic (Climatological Catalyst)
Sarawak's tropical climate directly dictates how the disease behaves, transforming the early warning system from a diagnostic tool into a predictive planning tool:
*   **Rain Pulse Spread:** Foot rot does not spread continuously; **it spreads in distinct rain pulses** [6]. The pathogen relies on heavy rainfall events to wash spores downhill into neighboring soil [6].
*   **Shift to Active Readiness:** Because of this "pulse" mechanic, the core question for a Sarawak farmer is never just *"did we catch the disease?"* but rather **"what happens at the next rain, and is our catchment ready?"** [6]. This insight allows HuluHilir to remain active and highly valuable even on farms with zero detected disease, using regional rain forecasts to trigger proactive drainage maintenance and protective spraying [6, 13].

### 4. Native Customary Rights (NCR) Land Sensitivities
A significant portion of Sarawak’s pepper is cultivated on **Native Customary Rights (NCR) land** [26]. 
*   **Legal & Social Sensitivity:** Land boundaries on NCR land are historically complex and highly sensitive [26]. Rural farmers are deeply distrustful of commercial agtech apps that require them to draw GPS boundaries or register land ownership [26].
*   **Privacy-First Mapping:** HuluHilir respects this unique socio-legal reality by **never recording land boundaries or ownership** [26]. It only records the relative elevation order of blocks to calculate gravity-fed water runoff, entirely bypassing the need for sensitive geographical mapping [26].

---

## 5. UN SDG Alignment

HuluHilir directly aligns with the United Nations Sustainable Development Goals (SDGs) by transforming advanced AI into an accessible, low-cost utility that protects both rural livelihoods and the surrounding rainforest ecosystems of Sarawak [9, 10]. 

### Goal 2: Zero Hunger
*   **Target Focus:** Target 2.3 — Double the agricultural productivity and incomes of small-scale food producers.
*   **HuluHilir’s Contribution:** Phytophthora foot rot causes **over 30% vine mortality**, costing farmers **USD 902 per hectare** and wiping out **56% of their annual net returns** [2]. By replacing guesswork with precise, terrain-aware early warnings and timed drainage instructions, HuluHilir directly protects smallholder crop yields and preserves vital household income [7, 9]. Independent farm-level analysis found that avoiding water stagnation and ensuring good drainage reduced foot rot losses by **24% (USD 439/ha)**—exceeding the 20% reduction achieved through chemical fungicides [8]. HuluHilir turns general agronomic advice into a dated, actionable instruction [9].

### Goal 15: Life on Land
*   **Target Focus:** Target 15.9 — Integrate ecosystem and biodiversity values into national and local planning.
*   **HuluHilir’s Contribution:** Traditional reactive farming leads to massive fungicide waste [3, 25]. Contact fungicides are highly effective but wash off easily; spraying them within 24–48 hours of a heavy tropical downpour simply flushes these expensive chemicals directly into the soil and local river catchments [3]. HuluHilir’s **Rain-Fast Treatment Rules (L3)** and **Agent Orchestration (L4)** ensure chemical applications are strictly timed outside of rain-fastness windows [14, 25]. By prioritizing preventative physical drainage clearing over blind spraying, the system significantly reduces chemical runoff into Sarawak’s rich terrestrial and aquatic ecosystems [8, 9].

### Goal 9: Industry, Innovation, and Infrastructure
*   **Target Focus:** Target 9.c — Significantly increase access to information and communications technology and strive to provide universal and affordable access to the internet.
*   **HuluHilir’s Contribution:** Advanced agricultural technology is historically locked behind expensive hardware paywalls (like IoT soil sensors, cellular towers, and drone mapping) that rural smallholders cannot afford [26]. HuluHilir introduces a **low-cost, highly accessible AI infrastructure** specifically designed for rural users operating with **intermittent connectivity** on **low-spec Android smartphones** [7, 10]. It brings sophisticated multi-agent orchestration and local computer vision directly to the farm gate with **zero hardware purchases and zero adoption barriers** [7, 10].

---

## 6. The AI Component: Hybrid Multi-Agent Architecture

HuluHilir rejects generic chat prompts, instead deploying a **hybrid AI stack** that combines on-device computer vision, deterministic physical modeling, and a reasoning multi-agent system to deliver highly reliable, hallucination-free guidance directly to the field [10, 14, 33].

### 1. Edge Computer Vision: L1 CNN Diagnosis
To detect infection without relying on fragile rural internet connections, a lightweight **MobileNetV3-Small model** runs entirely on-device [11, 34].
*   **The Early-Symptom Focus:** Instead of waiting for obvious leaf yellowing [11], the model is trained to detect **collar lesions** (dark, water-soaked stem wounds) [11, 15], which represent the earliest treatable window.
*   **Structured 6+1 Class Map [15]:** Images are classified into precise diagnostic states to feed the reasoning engine:
    *   `healthy_leaf` (*SIHAT (DAUN)*): Confirms leaf check — no action [15].
    *   `healthy_collar` (*SIHAT (PANGKAL)*): Confirms collar check — no action [15].
    *   `foliar_yellowing` (*DAUN MENGUNING*): Chlorosis; marked as ambiguous—context decides [15].
    *   `collar_lesion` (*LESI PANGKAL*): Dark water-soaked lesion at stem base (**Harmed — urgent escalation**) [15].
    *   `defoliation_wilt` (*GUGUR DAUN / LAYU*): Advanced infection; triggers salvage triage [15].
    *   `unrelated` (*TIADA KAITAN*): Non-plant clutter/blur; triggers immediate retake prompt [15, 16].

### 2. Zero-Hallucination Guardrails: L3 RAG + Rules
To guarantee agricultural safety, the system separates **natural language explanation** from **clinical dosage calculation** [14, 27]:
*   **The Rules Table:** Exact fungicide types, safe chemical dosages, and rain-fastness windows are locked in a deterministic database compiled from official MPB and Department of Agriculture (DOA) Sarawak guidelines [14].
*   **The Guardrail:** The LLM is strictly prohibited from generating, modifying, or inventing dosages [27]. It is only permitted to retrieve and read directly from this verified lookup table [14, 27].

### 3. Multi-Agent Orchestration: L4 Decision Arbitrator
A fixed software pipeline cannot handle conflicting data (e.g., advising a farmer to spray a sick plant when heavy rain is forecast to wash it away tomorrow) [18]. HuluHilir uses a **multi-agent topology** to hold these complex, competing factors simultaneously [14, 18]:

*   **RootAgent (LlmAgent):** The central arbitrator [16]. It sequences workflows, routes tool calls, and logs every deferred action to keep the system's logic fully auditable [16].
*   **SetupCoordinator (LoopAgent):** Guides the farmer step-by-step through mapping plot elevations until a coherent downhill water graph is constructed [17].
*   **DiagnosisCoordinator (LoopAgent):** Guides block-by-block visual capture after major rain events to ensure a complete farm-level picture is established before running spread projections [17, 23].
*   **Advisor (LlmAgent + RAG):** Evaluates rainfall history and proactively prevents alert fatigue by advising *against* unnecessary inspections (e.g., reassuring the farmer when past checks were healthy and rain has been minimal) [17, 24].

### The Orchestration in Action (The Core Moment) [20]
When a farmer scans an infected block on a sloped plot, the agents coordinate instantly:
1.  **L1 CNN** detects a `collar_lesion` on an upslope block [20].
2.  **L2 Terrain Graph** projects that gravity-fed runoff will carry the pathogen downhill to a neighboring plot within 4 days [20].
3.  **L3 Rules Table** pulls the required fungicide, which requires a 24-hour dry, rain-fast window [20].
4.  **Weather API** forecasts a massive 46 mm downpour tomorrow afternoon [20].

Instead of a wasteful instruction to spray immediately (which would wash the fungicide into the soil), the **RootAgent arbitrates**: it defers the chemical spray, orders immediate physical drainage clearing to divert runoff today, and schedules the chemical spray for Thursday morning after the rain pulse passes [20].

The final output is delivered via the speech-wrapped interface: **"Clear the drain today. Spray Thursday morning."** [20]
