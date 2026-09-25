<p align="center">
  <img src="docs/brand/banner.png" alt="PepperDex Sarawak" width="100%">
</p>

# PepperDex Sarawak

**Terrain-aware agentic early warning for Phytophthora foot rot in Sarawak black pepper.**

*AgroHack 2026 @ Sarawak AgroFest, Sibu, 25–27 September 2026*
Team **SMILING FACE WITH SUNGLASSES**: Nathan Yap Jia De (technical) · Zoe Tan An Xuen (deliverables) · Abraham Pang Exin (project management)

*(Formerly HuluHilir. The repository, Cloud Run service, database and bucket keep the old name on purpose; renaming them would create new services and URLs.)*

| | |
|---|---|
| **Landing page + Android app** | **https://sfws-aicc-workspace-1.web.app** (the APK is always at [`/pepperdex-latest.apk`](https://sfws-aicc-workspace-1.web.app/pepperdex-latest.apk)) |
| API | https://huluhilir-api-mfrzixfqeq-as.a.run.app · [interactive docs](https://huluhilir-api-mfrzixfqeq-as.a.run.app/docs) |

Install the APK on an Android phone (7 or newer), open it and tap **Try the demo farm** for a ready-made farm with diagnoses, agents at work and a 3D view of the slope.

---

## The problem

Existing plant-disease tools answer *"what is wrong with this leaf?"* A farmer with foot rot in one block already knows something is wrong. What they cannot see is **where it goes next, and when.**

Phytophthora foot rot does not spread continuously. It travels **downhill through water, in rain pulses.** A vine 40 metres downslope is at real risk after the next heavy rain; a vine 40 metres uphill is not. Sarawak grows over 98% of Malaysia's pepper, mostly on hill slopes planted that way for drainage, so the same runoff that keeps vines dry carries the pathogen from block to block.

## What PepperDex does

It models the farm as a **directed elevation graph** and arbitrates between four kinds of evidence that routinely disagree:

| Evidence | Source | Says |
|---|---|---|
| What is on the vine | L1 photo classifier | "Collar lesion, 91%, treat now" |
| What is allowed | L3 rules table | "This drench needs 24 h without rain" |
| When the rain comes | data.gov.my forecast | "~46 mm tomorrow" |
| Where the water goes | L2 spread graph | "Block 3 at risk in ~4 days (estimate)" |

The agent resolves them into **one action, one time, one reason** per block:

> *"Clear the drain today. Drench Thursday morning."*

Deterministic checks sit around the agent, so a model mistake never reaches the farmer as advice: a rain-fast check re-times or defers every spray, a rules check drops unknown products, invented blocks and stale dates, the spread model always runs for every diseased block, and if the model is slow or fails the rules table decides alone and the app says so.

---

## Architecture

```
L0  Voice & language   speech playback in Bahasa Malaysia · recorded block names · NO speech recognition
L1  Diagnosis          MobileNetV3-Small, 6 classes, ONNX (the only classifier)
L2  Spread             deterministic directed elevation graph -- NOT machine learning
L3  Knowledge          JSON rules (authoritative) + hybrid retrieval (explanatory only) + farm history
L4  Agents             Google ADK router + specialist agents + Overrun Council
```

### Agent topology

```
Router agent (RootAgent) -- arbitrates; one plan per affected block
├── Deterministic tools   get_weather · compute_spread · get_treatment
│                         find_spray_window · query_farm_history
├── Setup wizard          loop agent, bounded -- the one-time farm walk
├── DiagnosisCoordinator  loop agent, bounded -- the block-by-block photo round
├── Advisor               answers from a live snapshot of the farm + knowledge base
├── Overrun Council       only when more than one block is Harmed:
│     agronomic urgency · cost feasibility · logistics -> orchestrator ranks
│     (its response schema has no field for a product, dose or time)
└── Google Calendar (MCP) read to avoid clashes; writes ONLY when the farmer
                          approves a proposal card
```

Loop termination is **deterministic Python**, never LLM judgement. After each photo round the Advisor chat shows a live feed of each agent's real steps (tool results and council transcripts), not a spinner.

---

## Stack

| Layer | Technology |
|---|---|
| App | React Native (Expo SDK 57), expo-router, TanStack Query, typed client generated from the API's OpenAPI |
| Backend | FastAPI (Python 3.11+), Pydantic v2, SQLAlchemy 2.0 async |
| Agents | Google ADK + LiteLLM: **cloud** Vertex AI `gemini-2.5-flash` · **local** Ollama `qwen2.5:14b` |
| Storage | **cloud** Cloud SQL Postgres + Cloud Storage for photos · **local** SQLite |
| Diagnosis | MobileNetV3-Small → ONNX, served by the backend |
| Calendar | Google Calendar through an MCP server, one linked owner farm, approval-only writes |
| Hosting | Cloud Run `huluhilir-api` (asia-southeast1) · Firebase Hosting for the landing page and APK |

Switching local ↔ cloud is **configuration only** (`API_BASE_URL`, `LITELLM_MODEL`, `DATABASE_URL`). No application code branches on the target. The app can also point at a different server at runtime (Settings → Server address).

---

## Design commitments

Held even where a shortcut would have been faster. Full list: [`.claude/skills/pepperdex-rules/SKILL.md`](.claude/skills/pepperdex-rules/SKILL.md).

1. **No speech recognition on the critical path.** Voice labels are stored as audio and replayed, never transcribed.
2. **The rules table is the only source of dose, product and timing.** Retrieval explains *why*; it never decides *what*.
3. **The farmer's elevation answer always overrides sensors.**
4. **No land boundaries or ownership are recorded**, only relative elevation order and spacing. NCR land is legally sensitive in Sarawak.
5. **Neighbour alerts and calendar events are drafted, never automatic.** Nothing is sent or scheduled without the farmer's tap.
6. **The app works with zero photographs taken.** Rain-pulse warnings and the Advisor run from day one.
7. **Every risk number is an estimate**, and says so. The spread model is physically motivated, not field-validated.
8. **The Overrun Council may re-rank; it may never prescribe.** Enforced by its response schema, not by convention.

There are no accounts or passwords: a phone is linked to its farm, and a private **restore code** (Settings) moves the farm to a new phone. Android app-data backup is switched off so a farm never moves without that code.

---

## Running it

### Backend, local

```bash
docker compose up --build        # or: cd backend && uvicorn app.main:app --host 0.0.0.0
ollama serve && ollama pull qwen2.5:14b   # native on the host, not in Docker
```

Phone testing over a hotspot (firewall, `.env`, finding the laptop's address): see `../WORKSPACE_SETUP.md` § "Local hosting for phone testing".

### App, development

```bash
cd frontend-rn
npx expo start
```

### Tests

```bash
cd backend && pytest
```

`tests/test_agent_arbitration.py` runs against a **live** LLM rather than a mock (it is the exit criterion for the agent layer), so it needs a model running; everything else runs offline.

---

## Releasing and deploying

| What | Command (Git Bash, repo root) |
|---|---|
| New Android release | `./release-apk.sh --deploy`: bumps `versionCode`, builds locally, signs with the project keystore, refuses to publish if the certificate differs, then republishes the site with the APK at its fixed URL |
| Landing page only | `./build-site.sh --deploy` |
| Backend | `./deploy-cloud.sh`: rebuilds and redeploys Cloud Run `huluhilir-api` with the same service, URL, database and secrets |

`release-apk.sh` builds without EAS (the free build quota is spent until 1 Oct 2026) and needs Android Studio plus the keystore files from `eas credentials`, which are gitignored. Once the quota resets, `eas build --platform android --profile cloud` works again with the same key.

### Keeping the shared demo farm tidy

Every phone on "Try the demo farm" shares one farm, so visitors' photos and runs change it for everyone. The admin freezes it in a good state and it is restored automatically **every night at 03:00 (Kuching)**, or on demand. Both actions need the restore code of the team's own farm (the Google Calendar owner), shown in Settings on the admin phone.

| Action | How |
|---|---|
| Check status | `GET /demo/snapshot` |
| Freeze the demo as it looks now | `POST /demo/snapshot` with `{"restore_code": "XXX-XXX-XXX"}` |
| Put it back now (e.g. before judging) | `POST /demo/restore` with the same body |

Easiest from a phone: open `https://huluhilir-api-mfrzixfqeq-as.a.run.app/docs`, find the endpoint, tap **Try it out**, paste the code, **Execute**. Phones already on the demo farm keep working; they see the restored state on their next refresh.

### The team farm is protected on the cloud

The cloud deployment pins the team's farm as the Google Calendar owner (`CALENDAR_OWNER_FARM_ID`). That farm's id is written in this public repository, so it is treated as public and **unlocks nothing on its own**:

- The calendar can't be read or written directly through the API; the only write path is the farmer approving a proposal card.
- Nobody can re-link a connected calendar or unlink it through the API.
- The team farm's **restore code is kept offline**: the API won't show or rotate it, so the admin phone's Settings no longer displays it. Keep the written copy safe. It is still what restores the farm onto a phone and what authorises the demo snapshot controls.

If the written code is ever lost, anyone with access to the Google Cloud project can read it from Cloud SQL (`SELECT code FROM farm_restore_codes WHERE farm_id = '<team farm id>'`).

### Turning services on and off

```bash
# Cloud Run: stop serving without deleting (scales to zero)
gcloud run services update huluhilir-api --project sfws-aicc-workspace-1 \
  --region asia-southeast1 --min-instances 0 --max-instances 0

# Cloud Run: resume (max 1 on purpose -- the live agent feed is held in memory)
gcloud run services update huluhilir-api --project sfws-aicc-workspace-1 \
  --region asia-southeast1 --min-instances 1 --max-instances 1

# Firebase Hosting: take the site down / bring it back
npx firebase-tools hosting:disable --project sfws-aicc-workspace-1
./build-site.sh --deploy
```

### Credentials & access

This repository never contains live credentials: no service-account key, API token, keystore or `.env`. Secrets live in Secret Manager and are mounted into Cloud Run by `deploy-cloud.sh`; the list of variables (not their values) is in [`docs/CREDENTIALS.md`](docs/CREDENTIALS.md). Access to the project `sfws-aicc-workspace-1` is granted per person:

```bash
gcloud projects add-iam-policy-binding sfws-aicc-workspace-1 \
  --member="user:their-email@example.com" --role="roles/run.admin"
gcloud projects add-iam-policy-binding sfws-aicc-workspace-1 \
  --member="user:their-email@example.com" --role="roles/firebasehosting.admin"
```

---

## Repository layout

```
backend/          FastAPI app, agents, deterministic tools, MCP calendar server, tests
  app/agent/        ADK agents, council, live progress feed, MCP client
  app/tools/        spread · weather · treatment · scheduling · farm context · diagnose
  app/routers/      HTTP surface (setup, diagnosis, agent, calendar, dashboard, speech)
  seed/             rules table, knowledge docs, speech templates, demo farm
  scripts/          one-off operations (e.g. copying a farm to Cloud SQL)
frontend-rn/      React Native (Expo) Android app -- the current frontend
flutter_app/      v1 Flutter client, kept for reference only (no longer built or published)
classifier/       MobileNetV3-Small training + exported ONNX model
landing/          landing page (React + anime.js), built into public_site/ by build-site.sh
docs/             specification, data model, credentials list, validation checklist
```

---

## Status and honest limits

The demo farm is synthetic, so the pipeline is demonstrable without a real outbreak. The spread model is physically motivated but **not field-validated**, which is why every risk figure it emits is flagged as an estimate.

**On the classifier.** MobileNetV3-Small scores 0.934 macro F1 on its own held-out test set, and that is all the number means. It was trained on roughly 530 originals, largely generated rather than photographed, and it does not generalise reliably to real field photos. L1 is therefore presented as a prompt to go and inspect a vine, never as a diagnosis on its own; an unsure result (below 60%) never lowers a block's state.

## Licence

Competition submission. Not licensed for production agricultural decision-making.
