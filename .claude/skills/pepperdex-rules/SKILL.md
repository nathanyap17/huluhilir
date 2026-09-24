---
name: pepperdex-rules
description: Non-negotiable domain and safety rules for PepperDex (formerly HuluHilir). Use whenever writing code that touches treatment recommendations, dose or timing, elevation and terrain data, neighbour alerts, voice or language handling, spread model output, or any user-facing text. These are commitments made in a submitted AICC 2026 proposal — violating them makes the submission dishonest.
---

# PepperDex (formerly HuluHilir) — Non-Negotiable Rules

Product commitments **already stated in a submitted AICC 2026 proposal**. Code that violates them makes the submission untrue. Enforce structurally, not by convention.

---

## 1 · Treatment safety — the rules table is authoritative

**The agent may only output a treatment that exists in `treatment_options`.**

```python
# CORRECT
treatments = get_treatment(disease_class=cls)   # DB lookup
chosen = treatments[0]
dose   = chosen.dose_text_ms                     # verbatim from DB
source = chosen.source_ref                       # citation mandatory

# FORBIDDEN — never let an LLM produce these
dose = llm("What dose of Bordeaux mixture for foot rot?")
```

- **Retrieval explains *why*. It never decides *what*.**
- Every recommendation carries a `source_ref`.
- Namespaces: `authoritative` (rules) · `advisory` (MPB/DOA) · `local` (farmer uploads).
- **`local` may never supply a dose, product, or timing** — context only, attributed as *"from your own notes"*.

---

## 2 · No ASR on the critical path

No production speech recognition exists for Iban or Sarawak Malay.

- Voice labels are recorded, **stored as audio blobs, replayed** beside the block photo.
- **Never transcribe a voice label.** The farmer recognises their own voice; the machine never needs the words.
- STT is optional, `ms-MY` only, for free-form notes where failure is harmless.
- Iban text comes from **human-translated templates + pre-translated slots** — never LLM-generated. LLMs cannot write reliable Iban, and no BM→Iban MT exists.

**Speech output tiers:** pre-recorded clips (MVP) → MMS-TTS live synthesis (optimised) → `expo-speech` BM (fallback). *(Was `flutter_tts` in v1 — RN library swap only, no logic change.)*

---

## 3 · The farmer's elevation answer always wins

```python
if farmer_says != sensor_says:
    log_conflict(ElevationConflict(
        farmer_says=farmer_says,
        barometer_says=baro,
        dem_says=dem,
        resolution="farmer",       # ALWAYS
    ))
    return farmer_says
```

Sensors are cross-checks. GPS altitude is ±20–50 m and unusable alone. Barometer is relative only. DEM (SRTM ~90 m) may not separate adjacent blocks. **Never auto-override the farmer.**

---

## 4 · Land and privacy

- **Never record land boundaries, polygons, or ownership claims.** Only `elevation_rank` ordering. NCR land is legally sensitive.
- For `is_external = true` blocks: store **only a risk band**. Never a diagnosis, photo, or treatment history.
- Neighbour contacts are farmer-entered only. **Never scraped or inferred.**

---

## 5 · Neighbour alerts are drafted, never sent

```python
alert = Alert(
    message_ms=drafted_text,
    risk_band_shared=band,          # ONLY this is shared
    status="draft",
    approved_by_farmer=False,       # NEVER default True
)
```

Dispatch requires explicit farmer approval. One farmer's disease status is socially sensitive in a smallholder community.

---

## 6 · The app must work with zero photographs

Rain-pulse warnings and the Advisor run **without any diagnosis cycle ever existing**. This is a stated proposal claim.

- The dashboard must render usefully on a fresh farm with no observations.
- Never gate the dashboard, rain banner, or Advisor behind a completed diagnosis.
- The Advisor **recommends** when to diagnose; it never **blocks** the farmer from starting one.

---

## 7 · The spread model is deterministic, never ML

No labelled dataset exists for foot-rot transmission timing across mapped terrain.

- `compute_spread` is a **pure Python graph algorithm**. Same inputs → same outputs.
- Every risk output carries `is_estimate: true`, surfaced in the UI.
- `confidence` reflects **input quality** (elevation tier, GPS accuracy, farmer confirmation) — **not disease certainty**.
- The graph is **acyclic by construction**: edges only run `from.elevation_rank < to.elevation_rank`.

---

## 8 · Everything is speakable

- Every user-facing string has a `speech_template_id`.
- Literacy is not assumed; text alone is never sufficient.
- Setup requires **no typing** except optional short block labels.
- Input modes: tap, photograph, hold-to-record.

---

## 9 · CNN classes — exactly six

| Class | Malay | Meaning |
|---|---|---|
| `healthy_leaf` | SIHAT (DAUN) | Normal leaf — negative example for `foliar_yellowing` |
| `healthy_collar` | SIHAT (PANGKAL) | Normal stem base — negative example for `collar_lesion` |
| `collar_lesion` | LESI PANGKAL | **Decisive, earliest sign** |
| `foliar_yellowing` | DAUN MENGUNING | Lagging, non-specific |
| `defoliation_wilt` | GUGUR DAUN / LAYU | Advanced, vine often lost |
| `unrelated` | TIADA KAITAN | Not a plant subject — soil, hand, sky, blur. Small real negative set, never zero-shot. |

**Why split by body part.** `capture_target` (the farmer's declared intent — leaf/collar/whole-vine) is not verified ground truth; it is only a button pressed before the photo. If `healthy` were one merged class, a farmer who taps "collar" but photographs a leaf by mistake would still get "healthy" back — and the collar would never actually have been examined. Splitting `healthy_leaf` from `healthy_collar` makes the model's own prediction an independent check on *what was actually photographed*, not just a rubber stamp on the farmer's intent. Mismatch between `capture_target` and the predicted body part must trigger a retake prompt, never a silent pass.

- Classification, **not object detection**. No bounding boxes.
- `confidence < 0.60` → advise physical inspection; **never assert a diagnosis**.
- Optimise for **recall on `collar_lesion`**.
- The **block**, not the plant, is the unit of analysis.
- `unrelated` catches obvious junk; the confidence threshold catches ambiguous real photos. Keep both — they cover different failures.

---

## 10 · Honest language in code and UI

| Don't say | Say |
|---|---|
| "predicts" spread | "estimates" / "projects" spread |
| "diagnoses" definitively | "screens" / "flags for inspection" |
| "multi-agent" for `explain_why` | "LLM-backed tool" |
| "trained spread model" | "physically-motivated estimate" |

---

## 11 · Deployment target must never fork the code

The system runs locally (Docker + Ollama + SQLite) and, if time allows, on Google Cloud (Cloud Run + Gemini + Cloud SQL). **These differ by configuration only.**

```python
# CORRECT — environment-driven
MODEL    = os.environ["LITELLM_MODEL"]      # ollama_chat/gemma2:9b | gemini/gemini-2.0-flash
DATABASE = os.environ["DATABASE_URL"]       # sqlite+aiosqlite:///... | postgresql+asyncpg://...

# FORBIDDEN — never branch application logic on deployment target
if IS_CLOUD:
    result = gemini_call(...)
else:
    result = ollama_call(...)
```

- **Local must remain runnable at all times.** Never break it to enable the cloud path.
- Tool behaviour, schemas, and agent logic are identical on both targets.
- Secrets come from the environment. **Never commit an API key.**

---

## 12 · The Overrun council may re-rank; it may never generate a treatment

`OverrunCouncil` fires only when `farm_state == 'overrun'` **and** more than one block is simultaneously `Harmed`. It exists to rank already-approved actions by urgency, cost, and logistics — never to decide what those actions are.

```python
# CORRECT — the council's output schema has no field capable of holding one
class TriageRanking(BaseModel):
    block_id: str
    rank: int
    rationale_ms: str
    # no treatment_id, dose_text, or recommended_at field exists here —
    # this is enforced by the schema, not by convention

# FORBIDDEN — never let the council's output reach get_treatment or override it
if council_verdict.suggested_treatment:   # this field must not exist
    apply_treatment(council_verdict.suggested_treatment)
```

- The wall is **structural**: no dose/product/timing field exists anywhere in the council's response type, so there is nowhere for a hallucinated treatment to go.
- `get_treatment` and `find_spray_window` remain the only source of *what* to do. The council only ever answers *in what order*.
- Every debate is logged to `council_debates` — the transcript is demo evidence, not just an internal record.

## 13 · Calendar sync is drafted and consent-gated, never automatic

`draft_calendar_sync` produces text; it never writes to a calendar directly.

```python
# CORRECT
draft = draft_calendar_sync(recommendation_ids)
# farmer sees the draft, taps approve
if farmer_approved:
    sync_to_device_calendar(draft)

# FORBIDDEN — no silent sync path may exist
sync_to_device_calendar(draft)   # without an explicit approval gate first
```

- Same consent pattern as `draft_alert`: draft → farmer approves → action. Never invented fresh, always reused.
- Sync is revocable — `calendar_sync_grants.revoked_at` must be checked before any future write.

---

## Checklist before committing agent or tool code

- [ ] Does any dose, product, or timing come from anywhere but the rules table?
- [ ] Does anything transcribe a voice label?
- [ ] Can a sensor override the farmer's elevation answer?
- [ ] Is a boundary, polygon, or ownership field being stored?
- [ ] Can an alert send without `approved_by_farmer = True`?
- [ ] Does the dashboard still work with zero observations?
- [ ] Is `is_estimate` set on every risk output?
- [ ] Does every user-facing string have a `speech_template_id`?
- [ ] Does any code branch on deployment target instead of reading configuration?
- [ ] Is any secret or API key hard-coded rather than read from the environment?
- [ ] Does the council's output type have a field that could hold a dose, product, or timing? *(It must not.)*
- [ ] Can a calendar sync fire without a prior farmer approval check?
- [ ] Does a block's `current_state` ever get silently downgraded by an improving projection alone, rather than only by a direct diagnosis?
