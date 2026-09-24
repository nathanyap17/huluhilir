# PLAN.md — PepperDex Development Plan

> ⚠️ **MIGRATION CONTEXT — READ BEFORE STARTING ANY TASK**
> A prior session already built and validated a working v1 system for a different competition (AICC): Flutter frontend, single-agent backend, live 24-hour build. **That backend logic works and is not being rebuilt.** This plan describes migrating it to v2 for a new competition (AgroHack 2026): full frontend rebuild (Flutter → React Native) plus six scoped backend extensions. **Your job is to realise these changes on the existing system, not to interpret this document as instructions for a system that doesn't exist yet.** If you find yourself writing `compute_spread`, the rules engine, or the CNN pipeline from scratch, stop — that already exists; extend it instead.

> **Competition:** AgroHack 2026 @ Sarawak AgroFest — Sibu Town Square, 25–27 Sept 2026
> **Build rule:** Product must be built **before** exhibition day — pre-building is expected, not restricted. This is the opposite of AICC's live-build-only rule; do not carry hour-by-hour clock discipline over by habit.
> **Submission criteria:** Product/Prototype · Bunting (80×200cm) · Presentation Slides · Demo Video · Poster A3

---

## ⏸ HOLD — shipping work is parked until the owner verifies local testing (set 2026-09-20)

**Rule for any session or agent reading this:** Stages 2–3 below are **decided but NOT started**. Do **not** begin them, and do not deploy anything, until the owner (Nathan) has said in chat that **Stage 1 (local APK testing) is verified and passed**. Until then, all work **navigates back to Stage 1**: local backend + the `local`-profile APK + fixing whatever the owner reports. If unsure whether the hold has been lifted, ask.

### The staged plan (owner's plan, verified 2026-09-20)

| Stage | What | Who | Gate to leave |
|---|---|---|---|
| **1 · NOW — local APK** | Backend runs on the laptop (`--host 0.0.0.0`). `eas build --profile local` produces a **standalone `.apk`** with the laptop's LAN address baked in. Install on the phone and test every feature — **no Metro/frontend server needed**. Steps: `../WORKSPACE_SETUP.md` § "Stage 1 — local-backend APK" | Owner runs `eas login`/`eas init`/`eas build`; agent fixes what testing finds | Owner says Stage 1 is verified and passed |
| **2 · SHIP** | Upload `.apk` to Firebase Hosting → landing page buttons (repo, docs, demo, `.apk`) + QR → sync backend to **Cloud Run** → push to **GitHub** (`origin` = `nathanyap17/huluhilir`, branch `master`, ~50 uncommitted changes at 2026-09-20) → build a **separate `cloud`-profile APK** pointing at the Cloud Run URL and use *that* one for judges | Agent prepares; owner runs the logins (`gcloud`, `firebase`, `eas`) | Judges' link works end to end |
| **3 · PIPELINE** | Script that automates: `eas build --profile cloud` → download → versioned + `pepperdex-latest.apk` → `version.json` → `firebase deploy` | Agent | — |

**Corrections to the plan as first stated (things that would otherwise have bitten):**
1. **The Stage 1 APK is not the APK judges get.** The API address is baked in at build time, so a laptop-address APK is useless off your Wi-Fi. Judges need a second build (`cloud` profile) after Cloud Run exists — budget one more EAS build.
2. **A release APK blocks plain `http://`** (Android 9+). The `local` profile therefore enables cleartext via `frontend-rn/app.config.js` (`ALLOW_CLEARTEXT=1`, set only in that profile); `cloud`/`production` stay https-only.
3. **`frontend-rn/.env` is gitignored, so EAS never sees it.** The laptop address lives in `eas.json` → `build.local.env` (currently `http://192.168.0.6:8000`) and **must be edited if the laptop's IP changes** — best avoided by giving the laptop a fixed address (DHCP reservation in the router).
4. **Every screen change during Stage 1 needs a new build (~15 min, and EAS's free tier has monthly limits).** Cheaper for iterating: one `development` build + `npx expo start --dev-client`. Use the standalone `local` APK for final validation passes, not every tweak.
5. **The GitHub repo keeps the name `huluhilir`** -- decided 2026-09-24, see "Identity rule" below.

### Identity rule -- what changes and what never does (owner decision, 2026-09-24)

**Reuse everything already created on this branch:** GitHub repo `nathanyap17/huluhilir`, Cloud Run service **`huluhilir-api`** (its URL does not change -- only the code deployed into it becomes v2 PepperDex), GCP/Firebase project `sfws-aicc-workspace-1` and its landing URL, Cloud SQL `huluhilir-db`, secret `huluhilir-db-url`, bucket `huluhilir-media`, local `huluhilir.db`, CNN model files `huluhilir_l1*.onnx`, and every credential. **Never create a new project, service, bucket or database.**

**Change freely:** outward appearance and naming -- brand "PepperDex Sarawak", logo, agents, app architecture, backend *contents*, v2 filenames. `frontend-rn/` is the current frontend; `flutter_app/` (v1) is kept untouched on purpose. Brand images: until a real banner exists, `docs/brand/banner.png` and `landing/public/brand/{banner,logo}.png` are the PepperDex logo (set 2026-09-24).

**Cloud migration checklist (added 2026-09-24 -- do these as part of Stage 2):**
1. Fill `frontend-rn/eas.json` -> `build.cloud.env.EXPO_PUBLIC_API_BASE_URL` with the `huluhilir-api` URL and build the `cloud` APK separately (the in-app Settings -> Server address also accepts it).
2. Cloud SQL is a different database from the laptop's `huluhilir.db`: either migrate the team farm (Kebun MiaoMiao) or create the admin farm on cloud and pin its new id as `CALENDAR_OWNER_FARM_ID` on Cloud Run.
3. Cloud Run's filesystem is wiped per revision: keep `token.json` (Google) and the calendar owner in Secret Manager / GCS, not the container.
4. `LITELLM_MODEL` -> Gemini on Cloud Run (no Ollama there).
5. The cloud APK needs internet; the local setup keeps working offline on the hotspot LAN.

**End-of-project deliverables (Stage 2, still behind the HOLD):**
1. GitHub: push v2 "HuluHilir → PepperDex Sarawak" to the same repo, README renamed/rewritten for PepperDex.
2. Backend: deploy v2 into the **same** `huluhilir-api` via `./deploy-cloud.sh`.
3. Landing page at the same `https://sfws-aicc-workspace-1.web.app/`: refreshed to feature the v2 functions (agent feed, Overrun Council, farm-memory Advisor, MCP calendar with approval), with shortcuts for **repo, API docs, demo video, and a QR/link to download the `.apk`**.

**Decisions already made (so they aren't re-litigated):**
| Topic | Decision |
|---|---|
| Distribution | **Android only.** EAS-built `.apk`, hosted as a download on Firebase Hosting. **No iOS** — Apple only allows install via TestFlight (needs the paid Apple Developer account) or device-registered ad hoc builds; a hosted `.ipa` will not install. Revisit only if the owner gets an Apple Developer account approved |
| Hosting split | Cloud Run = backend API only · Firebase Hosting = landing page (QR target) + the `.apk` files + `version.json` · the installed app talks to Cloud Run over HTTPS |
| Landing page | Buttons: repo · docs · demo · `.apk` download; QR code → landing page; show version + checksum next to the download |
| **Landing URL (FIXED, decided 2026-09-20)** | **`https://sfws-aicc-workspace-1.web.app/`** (Firebase project `sfws-aicc-workspace-1`, site root). The **bunting QR encodes this root address only** — never `/app/`, an anchor, or a direct `.apk` filename. Owner chose to keep this URL (the "aicc" in the project ID is accepted; a cleaner second Hosting site was considered and declined). **Do not delete/recreate the Firebase project or site.** Until Stage 2 deploys, this URL still serves the old v1 "HuluHilir" page + Flutter `/app/` — **the new landing page must be live before 25 Sept** because anyone scanning earlier sees the old one. The `.apk` link behind the page changes freely via the fixed `pepperdex-latest.apk` name |
| Release pipeline | One script after each `eas build --profile cloud`: download `.apk` → versioned file + fixed `pepperdex-latest.apk` → write `version.json` (version/date/size/sha256) → `firebase deploy --only hosting`. Needs: auto-increment `versionCode` on the `cloud` profile, keep the EAS-managed signing key, `no-cache` + APK content-type headers in `firebase.json` |
| Web preview (the "demo" button) | Optional separate Expo web export at `/app/`, clearly labelled a **preview** — no barometer, live map or calendar sync in a browser. Full features = the APK only |
| Cloud Run settings | `--min-instances 1 --max-instances 1` (SQLite + photos live in the container; a second instance = "farm not found"); billing alert; cloud LLM = Gemini via LiteLLM (local `qwen2.5:14b` takes minutes) |
| Device limits (proposed, not built) | One registration per device, fixed quota on the LLM-costing endpoints (`/agent/run`, `/advisor/ask`), enforced **server-side** with a hashed device id (Android ID; iOS/web ids are weak). Quota must live somewhere that survives redeploys (Cloud SQL or Firestore) — the in-container SQLite does not |
| "Try the demo farm" button | Proposed: loads the seeded farm so judges (who cannot walk a hillside at the exhibition) land on a populated Home. Not built |
| Freeze | Freeze app screens ~2 days before 25 Sept, build the `.apk` once, then touch only the backend |

**Parked work list (in order, when the hold lifts):** demo-farm button → Cloud Run deploy settings → device registration + quota → `cloud`-profile APK + release script → landing page buttons/QR → web preview (optional).

---

## 0 · What's already done, and what this plan actually changes

**Already built, tested, and not being touched:** the spread graph (`compute_spread`), the rules engine (`get_treatment`, `find_spray_window`), the CNN classification pipeline (6 classes), the two-tier elevation capture logic, the SQLAlchemy schema (22 v1 tables), the deterministic Advisor verdict logic, and the core agent arbitration pattern. These are the hard-won parts. Extend them; don't re-derive them.

**What actually changes in v2:**
1. **Frontend — full rebuild, Flutter → React Native.** Not a refactor. See `docs/PROJECT_SPEC.md` §9 for why.
2. **Six backend extensions**, each already scoped: **3D terrain scene** with proportional layout (`@react-three/fiber` + `expo-gl` — corrected from an earlier flat-2D-canvas spec, see `docs/PROJECT_SPEC.md` §3 L2 and §9.6), the Overrun Council (triage-ranking only, structurally walled from generating treatments), the immediate-action drawer (UI exposure of already-computed fields), the Advisor↔Action cross-reference, the 7-day rain pulse chart, hybrid search (split correctly between unstructured knowledge docs and structured farm history), and MCP calendar sync (consent-gated).
3. **CNN inference path corrected:** `.onnx` is now the sole primary path. Gemini Vision — used briefly in v1 as a workaround for a label-order bug — is removed entirely, not demoted.

---

## 1 · Repo strategy

**Same repository. New frontend directory. Backend continues in place.**

```
pepperdex/
├── backend/              ← unchanged structure, extended in place — DO NOT rewrite
├── frontend-rn/          ← NEW — fresh Expo/RN project
└── frontend-flutter/     ← archive once RN reaches parity, then delete
```

No fresh clone (the backend is tested and working — a new repo throws that away for nothing). No in-place Dart→TSX edit (there is no incremental path — write clean against `docs/PROJECT_SPEC.md` §9's contracts, don't reverse-engineer old widgets).

---

## 2 · Phase plan

Given AgroHack allows pre-building, this is **ordered phases, not hour-blocks** — unlike the old AICC plan's 24-hour clock. Move to the next phase when the current one's exit condition is met, not when a clock says so. **Commands below are restored detail** — an earlier version of this plan compressed tasks to prose-only, which left the actual steps to be re-derived from `CLAUDE.md`/`WORKSPACE_SETUP.md` instead of being usable directly here.

### Phase A — Environment + validation

| Task | Command | Exit condition |
|---|---|---|
| Node/Expo/EAS environment | `npx expo --version && eas --version` | Both print clean versions — see `WORKSPACE_SETUP.md` for full install steps |
| Ollama reachable | `ollama serve` (separate terminal) then `curl http://<LAN_IP>:11434` from phone | Responds over your own hotspot, no internet needed |
| `.onnx` label-order parity check | `python sandbox/check_label_order.py --model backend/models/pepperdex_l1.onnx --labels backend/models/labels.txt` | Exits 0 — see §3 below |
| EXP-14: `capture_target` mismatch | `python sandbox/exp14_mismatch.py` | Leaf-tapped-as-collar → retake, not silent pass |
| EXP-15: Council dose-less schema | `python sandbox/exp15_council_wall.py` | `ValidationError` raised on a bad payload |
| EXP-16: Calendar consent gate | `python sandbox/exp16_calendar_gate.py` | `PermissionError` raised without a prior grant |

### Phase B — Frontend scaffold ✅ built 2026-09-18, needs on-device verification

| Task | Command | Exit condition |
|---|---|---|
| Scaffold RN project | `npx create-expo-app frontend-rn --template` | ✅ Project exports cleanly (`npx expo export --platform android`, 1466 modules); real-device "boots in Expo Go" not yet verified — no phone in this session |
| Generate TS types from backend | `npx openapi-typescript http://localhost:8000/openapi.json -o frontend-rn/src/api-types.ts` | ✅ Types compile clean (`npx tsc --noEmit`) against the running backend |
| Navigation shell | build `RootNavigator` per `docs/PROJECT_SPEC.md` §9.0 | ✅ Built (`app/_layout.tsx` + `app/index.tsx` gate + `(setup)`/`(tabs)` groups) — gate logic re-fetches `GET /farms/{id}` rather than trusting cached `setup_completed_at`, matching that endpoint's own docstring. Not yet verified on a real device |
| Setup wizard screens | build §9.9–9.13 in order | ✅ Built against the real API surface. §9.12 (drainage/neighbour contacts) folded into §9.10's block-capture screen — no `PATCH /blocks/{id}` exists to set drainage after the fact, and no `neighbour_contacts` table exists at all (see `docs/DATA_MODEL.md`) — see `frontend-rn/app/(setup)/walk.tsx`'s header comment. "Full setup → farm graph on a real phone" not yet verified — no phone in this session |
| Walk loop | `expo install expo-location expo-sensors` | Built (`frontend-rn/app/(setup)/walk.tsx`, `frontend-rn/src/utils/barometer.ts`) but **EXP-4 (barometer on `expo-sensors`) still needs a real device** — cannot be verified from this environment |

> ⚠️ **2026-09-18 correction, caught by on-device testing:** the first Phase B walk screen silently dropped three widgets the archived v1 Flutter build actually had (`TierBanner`, `WalkMap`, `AltitudeReadout` — see `flutter_app/lib/tier_banner.dart`/`walk_map.dart`), traced to a misread of `docs/PROJECT_SPEC.md`'s "silent" language. Corrected in the spec and rebuilt — see `docs/VALIDATION_CHECKLIST.md`'s log. **Lesson for future phases:** when a screen has a v1 Flutter equivalent, read its actual source (`flutter_app/lib/`), not just `docs/PROJECT_SPEC.md`'s summarised data dictionary, before deciding a feature isn't in scope.
>
> ⚠️ **2026-09-18, second on-device finding:** the restored live map (`expo-maps`) threw `Cannot find native module 'ExpoMaps'` on the same device that had already run other Expo modules fine — like the 3D scene, it needs an EAS *development build*, not plain Expo Go. Both failures happened at module-import time, which crashed the whole app at the splash screen rather than just the affected screen (expo-router couldn't resolve a default export from any file that imported the broken module). Fixed with `SafeTerrainScene.tsx`/`SafeWalkMapView.tsx` — guarded `require()` wrappers that degrade to an informative fallback instead of crashing. **Lesson: any new native module gets tested for a bare-`require()`-time throw before it's wired into a screen the whole setup flow depends on, not after.**

> ⚠️ **2026-09-19, third on-device finding:** the Diagnosis Capture screen (§9.8) was never built — the Advisor's "Begin Diagnosis" button pointed at a placeholder, so no user could ever produce a recommendation. Now built (`frontend-rn/app/diagnosis.tsx`); Home's priority card is always shown with bento metrics and a `/diagnose` shortcut; tab headers show the logo. **Still open:** the agent run is synchronous and slow on the local model (needs background job + polling); the capture flow has not been exercised on a real device yet.

**Also done, not in the original table:** app icon/adaptive-icon/splash generated from the real `pitch-and-design/PepperDex_Logo.png` mark (not recreated from a text description); Home/Advisor/Farm tab screens and the Block Detail screen (§9.1–9.3, §9.4–9.5, §9.6 list-placeholder, §9.7) built against the CURRENT backend response shapes — §9.6's real 3D canvas, the 7-day rain pulse, and the drawer fields are Phase C (backend fields don't exist yet); Settings screen (§9.16).

### Phase C — Backend extensions ✅ built 2026-09-18

| Task | Command / reference | Exit condition |
|---|---|---|
| **3D terrain scene** | `expo install expo-gl @react-three/fiber three` — geometry per `docs/PROJECT_SPEC.md` §3 L2 STEP 1–5 | ✅ `backend/app/tools/terrain.py` (rotation) + `frontend-rn/src/components/TerrainScene.tsx` (real `@react-three/fiber`/`expo-gl` scene, drag-to-orbit). EXP-17 passes (`backend/tests/test_terrain.py`) — an east-west farm still aligns "hulu" consistently, rotation confirmed an isometry. ⚠️ **Confirmed 2026-09-18: does not run inside plain Expo Go** (`TypeError: undefined is not a function` at import time) — needs an EAS *development build*. Guarded behind `SafeTerrainScene.tsx` (graceful fallback) so it no longer crashes the app; the real fix is building the dev client, not yet done |
| Overrun Council | ADK `sub_agents` per `docs/PROJECT_SPEC.md` §B.2 — **not** the A2A protocol | ✅ `backend/app/agent/council_agent.py` — real `SequentialAgent` of 3 specialists + orchestrator, dose-less `TriageRanking` (`extra="forbid"`), wired deterministically into `run_root_agent` (step 3a). Debate transcript logs to `council_debates` with the REAL specialist arguments (state read back from the nested runner's session, not an LLM echo). EXP-15 passes live against `qwen2.5:14b`, not just the sandbox schema check |
| `query_farm_history` + FTS5 | `CREATE VIRTUAL TABLE knowledge_docs_fts USING fts5(content)` | ✅ `backend/app/tools/knowledge_fts.py` (SQLite-only, guarded for a future Postgres path) + `backend/app/tools/farm_history.py`, both tested (`backend/tests/test_hybrid_search.py`). `retrieve_knowledge` now genuinely hybrid — FTS5 hit boosts the existing keyword-overlap score rather than replacing it |
| `draft_calendar_sync` + consent modal | `expo install expo-calendar` | ✅ Backend: `draft_calendar_sync` LLM-backed tool (single event per call — a JSON array was judged too unreliable for a local model, same reasoning as `_reconcile_spray_deferrals`) + `calendar_sync_grants` grant/revoke/status endpoints (`backend/app/routers/calendar.py`). Frontend: `CalendarConsentModal.tsx` — grant recorded server-side BEFORE the on-device `expo-calendar` write, never the reverse. EXP-16 passes against real endpoints (`backend/tests/test_calendar.py`), not just the sandbox pattern |
| 7-day rain pulse | extend `RainPulseResponse` per §10 API contract | ✅ `forecast_days` returns real 7-day data (was already computed, just collapsed to one day before); `frontend-rn/src/components/RainPulseCard.tsx` collapses/expands per §9.1 |
| Action drawer fields | expose existing `risk_assessments`/`recommendations` columns | ✅ Found and fixed a real gap first: nothing ever wrote to `risk_assessments` before this (`compute_spread`'s result was used in-memory and discarded) — `app/agent/runner.py`'s `_extract_risk_assessments` now persists it. `drawer` on `DashboardResponse` is null until a real row exists, never a placeholder. `frontend-rn/src/components/PriorityActionCard.tsx` renders it |

**Also fixed along the way:** `gemma2:9b` (Phase A's VRAM-safety swap) doesn't support tool calling at all — reverted to `qwen2.5:14b`; `find_spray_window`'s docstring strengthened after a live test showed the model sometimes omitting a known `rainfast_hours` value, silently skipping its own rainfast reasoning; `RetrievalQuery`'s default namespaces tightened to exclude `authoritative` (the one real caller already overrode it, but the default itself contradicted retrieval's own "explains why, never what" rule).

### Phase D — Integration + harden

| Task | Command | Exit condition |
|---|---|---|
| Full diagnosis cycle, phone → backend → arbitration | manual run on a real phone over local network | Arbitration case ("drain today, spray Thursday") reproduces with `defer_cause="rainfast"` logged |
| Block state precedence | `python sandbox/exp18_state_precedence.py` | All four assertions pass — see `docs/PROJECT_SPEC.md` §3 L4 block state model |
| Offline outbox | disable phone WiFi mid-capture, re-enable after 3 photos | Queue flushes automatically on reconnect |
| Two-target deployment | `docker compose up --build` (local) then `./deploy-cloud.sh` → existing service `huluhilir-api` in `sfws-aicc-workspace-1` (cloud; v1 identifiers kept on purpose) | Same container, config-only switch (`API_BASE_URL`/`LITELLM_MODEL`/`DATABASE_URL`) confirmed |

### Phase E — Deliverables

| Task | Owner | Note |
|---|---|---|
| Demo video | Abraham → Zoe | Record once Phase D is stable, don't wait until the last day |
| Bunting, poster, deck | Zoe | See `DESIGN_BUNTING-v2.md`, `MOCK_DESIGN.md`, `DECK.md` |
| Landing page | Nathan | `firebase deploy --only hosting,storage` — APK link, architecture diagram updated to RN + 3D stack |

---

## 3 · CNN inference — the one thing that must not regress

> *"The v1 build used Gemini Vision as a workaround for a label-order bug. After fixing label order, `.onnx` gives instant, accurate results."*

**`.onnx` is the sole primary path. No Gemini Vision branch exists anywhere in the fallback chain** — if `.onnx` fails to load, the path is identical to low-confidence: advise physical inspection. A mandatory CI check confirms `labels.txt` order matches training config before every deploy — this exact bug already cost real time once.

---

## 4 · Non-negotiables carried forward

Full list in `.claude/skills/pepperdex-rules/SKILL.md` (13 rules, code-enforced). The two v2 additions:

12. The Overrun Council may re-rank approved actions; it may **never** generate a treatment, dose, or timing — enforced by its response schema having no such field.
13. Calendar sync is drafted and consent-gated, never automatic.

---

## 5 · Cut order (if time runs short — pre-build still has limits)

1. MCP calendar sync → keep drafted-only, skip the actual device write
2. Overrun Council → deterministic triage (sort by risk score) instead of a real debate
3. Hybrid search → vector-only, skip FTS5
4. 3D terrain scene → fall back to a flat 2D canvas with the same proportional layout (loses depth/motion, keeps the correct relative positions)
5. On-device TFLite → backend `.onnx` only (already the default; don't attempt the optimised tier)

**Never cut:** the spread graph, agent arbitration, `tools_called` logging, `.onnx` diagnosis, the walk loop, the Overrun Council's treatment-identity wall (even in its degraded deterministic form, the wall stays).

---

## 6 · Open items — resolved before Phase B

1. **"Vine" vs "block" terminology** (`docs/PROJECT_SPEC.md` §9.7) — ✅ confirmed "block."
2. **Settings screen placement** — ✅ confirmed top-right icon, not a 4th tab.

---

## 7 · Task allocation

| Owner | Responsibility |
|---|---|
| **Nathan** | Backend extensions, agent/council, RN frontend, model, deployment |
| **Zoe** | Deliverables, submission, pitch deck, video edit |
| **Abraham** | Seed data, rules table, templates, testing |
