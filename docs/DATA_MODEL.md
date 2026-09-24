# DATA_MODEL.md — PepperDex (formerly HuluHilir)

> ⚠️ **Migration status:** this schema was built and validated in v1 (Flutter era) and is unchanged in its core — the v2 rebuild is frontend + agent-layer, not a data model rewrite. **🔄 v2** marks the three genuinely new tables and two new computed (non-persisted) fields. Everything else below is the original, already-working v1 schema.
>
> SQLAlchemy 2.0 async. **SQLite locally; Cloud SQL (PostgreSQL) if the cloud path ships** — a connection-string change only, no schema change. IDs are **ULIDs** · timestamps ISO 8601 `Asia/Kuching` · **SQLite has no array type** — use `JSON` columns · `?` = nullable

---

## Enumerations

| Enum | Values |
|---|---|
| `DiseaseClass` | `healthy_leaf` · `healthy_collar` · `foliar_yellowing` · `collar_lesion` · `defoliation_wilt` · `unrelated` · `unknown` |
| `BlockState` | `protected` · `alerted` · `harmed` · `overrun` |
| `ElevationTier` | `minimal` · `optimised` |
| `DrainageCondition` | `good` · `fair` · `poor` |
| `SlopeCategory` | `gentle` · `moderate` · `steep` |
| `TreatmentType` | `contact` · `systemic` · `biological` · `cultural` |
| `ActionType` | `spray` · `drench` · `clear_drain` · `isolate_vine` · `remove_vine` · `inspect` · `notify_neighbour` · `no_action` |
| `AlertStatus` | `draft` · `approved` · `sent` · `dismissed` |
| `Language` | `ms` · `iba` · `en` |
| `SyncStatus` | `local_only` · `syncing` · `synced` · `failed` |
| `KnowledgeNamespace` | `authoritative` · `advisory` · `local` |
| `CycleStatus` | `in_progress` · `complete` · `abandoned` |
| `AdvisorUrgency` | `high` · `medium` · `low` · `none` |
| `CalendarProvider` 🔄 v2 | `google_calendar` |

---

## 1 · `users`

| Field | Type | ? | Notes |
|---|---|---|---|
| `user_id` | str(26) | | **PK** ULID |
| `display_name` | str(80) | | |
| `phone` | str(20) | ? | **PII** — E.164 |
| `district` | str(40) | | e.g. `Julau` |
| `language_pref` | `Language` | | default `ms` |
| `created_at` | datetime | | |

## 2 · `farms`

| Field | Type | ? | Notes |
|---|---|---|---|
| `farm_id` | str(26) | | **PK** |
| `user_id` | str(26) | | FK |
| `name` | str(80) | | |
| `centroid_lat` / `centroid_lon` | float | | Binds weather station |
| `weather_station_id` | str(30) | ? | Nearest DID station |
| **`elevation_tier`** | `ElevationTier` | | **Drives confidence downstream** |
| `barometer_available` | bool | | Device capability at setup |
| `total_area_ha` | float | ? | |
| `setup_completed_at` | datetime | ? | Null while in progress |
| `walk_session_id` | str(26) | ? | FK |

---

## 3 · `walk_sessions`

| Field | Type | ? | Notes |
|---|---|---|---|
| `walk_session_id` | str(26) | | **PK** |
| `farm_id` | str(26) | | FK |
| `started_at` / `ended_at` | datetime | /? | |
| `sample_interval_ms` | int | | default 2000 |
| `baseline_pressure_hpa` | float | ? | **Reference for all relative altitude** |
| `baseline_captured_at` | datetime | ? | Drift check |
| `total_samples` | int | | |
| `mean_gps_accuracy_m` | float | ? | Feeds `confidence` |

## 4 · `walk_samples`

| Field | Type | ? | Notes |
|---|---|---|---|
| `sample_id` | str(26) | | **PK** |
| `walk_session_id` | str(26) | | FK |
| `lat` / `lon` | float | | |
| `gps_alt_m` | float | ? | ±20–50 m — **never authoritative** |
| `gps_accuracy_m` | float | | Horizontal |
| `baro_alt_m` | float | ? | Null in MINIMAL |
| `pressure_hpa` | float | ? | |
| `recorded_at` | datetime | | |

> Retain raw samples — needed to recompute centroids if a block is re-marked, and evidence the walk happened.

---

## 5 · `blocks` — central entity

| Field | Type | ? | Notes |
|---|---|---|---|
| `block_id` | str(26) | | **PK** |
| `farm_id` | str(26) | | FK |
| `label` | str(30) | | **Farmer's own words** |
| `voice_label_uri` | str(255) | ? | Audio blob — **never transcribed** |
| `photo_uri` | str(255) | | Visual identity |
| `centroid_lat` / `centroid_lon` | float | | **Median** of ±5 s window |
| `marked_at` | datetime | | Button A press |
| **`elevation_rank`** | int | | **1 = highest. Unique per farm** |
| `baro_rel_m` | float | ? | Relative to session baseline |
| `dem_elevation_m` | float | ? | SRTM cross-check |
| `slope_category` | `SlopeCategory` | ? | MINIMAL tier |
| `drainage` | `DrainageCondition` | | default `fair` |
| `area_ha` | float | ? | |
| `vine_count` | int | ? | Drives loss estimate |
| `variety` | str(40) | ? | |
| `current_state` | `BlockState` | | default `protected` |
| `state_changed_at` | datetime | ? | |
| `last_diagnosis_id` | str(26) | ? | FK |
| `last_treated_at` | datetime | ? | |
| `is_external` | bool | | True = neighbour's land |
| `external_owner_name` | str(80) | ? | **PII** |
| `external_owner_phone` | str(20) | ? | **PII** |

**🔄 v2 — computed, not persisted, added to API responses only:** `x_rot_m`, `y_rot_m` (rotated local-metre coordinates for the terrain canvas — recomputed at response time from `centroid_lat/lon` + `flow_edges`, never stored, so layout can't go stale after a graph edit). Not new columns on this table.

**Constraints**
- `elevation_rank` **unique per farm** — ties break the graph
- If `is_external = true`: store **only** `current_state`. No diagnosis, photo, or treatment history.

## 6 · `flow_edges`

| Field | Type | ? | Notes |
|---|---|---|---|
| `edge_id` | str(26) | | **PK** |
| `farm_id` | str(26) | | FK |
| `from_block_id` / `to_block_id` | str(26) | | Upslope → downslope |
| `horizontal_dist_m` | float | | Haversine — **v2 now also drives canvas layout, not just spread weight** |
| `elevation_drop_m` | float | ? | OPTIMISED only |
| `slope_ratio` | float | ? | Δh ÷ distance |
| `flow_weight` | float | | 0–1 |
| `barrier` | bool | | Bund/road blocks flow |
| **`source`** | str(20) | | `farmer` · `barometer` · `dem` |
| **`farmer_confirmed`** | bool | | |
| `conflict_logged` | bool | | |

> **Acyclic by construction:** `from.elevation_rank < to.elevation_rank` always.

## 7 · `elevation_conflicts`

| Field | Type | ? | Notes |
|---|---|---|---|
| `conflict_id` | str(26) | | **PK** |
| `farm_id` | str(26) | | FK |
| `block_a_id` / `block_b_id` | str(26) | | Disputed pair |
| `farmer_says` | str(20) | | `a_higher` · `b_higher` |
| `barometer_says` | str(20) | ? | |
| `dem_says` | str(20) | ? | |
| `resolution` | str(20) | | **Always `farmer`** |
| `delta_h_m` | float | ? | Triggered gate if < 2.0 |
| `logged_at` | datetime | | |

---

## 8 · `diagnosis_cycles`

| Field | Type | ? | Notes |
|---|---|---|---|
| `cycle_id` | str(26) | | **PK** |
| `farm_id` | str(26) | | FK |
| `trigger_reason` | str(30) | | `rain_pulse` · `stale` · `user_initiated` · `agent_recommended` |
| `triggering_rain_mm` | float | ? | |
| `triggering_rain_date` | date | ? | |
| `started_at` / `completed_at` | datetime | /? | |
| `blocks_total` / `blocks_captured` | int | | Resume progress |
| `status` | `CycleStatus` | | |
| `run_id` | str(26) | ? | FK → `agent_runs` |

## 9 · `observations`

| Field | Type | ? | Notes |
|---|---|---|---|
| `observation_id` | str(26) | | **PK** |
| `cycle_id` | str(26) | ? | FK — null for ad-hoc |
| `block_id` / `user_id` | str(26) | | FK |
| `image_uri` | str(255) | | |
| `image_hash` | str(64) | | SHA-256, dedup |
| `capture_target` | str(20) | | `leaf` · `collar` · `whole_vine` |
| `captured_at` | datetime | | |
| `gps_lat` / `gps_lon` | float | ? | |
| `sync_status` | `SyncStatus` | | |

## 10 · `diagnoses`

| Field | Type | ? | Notes |
|---|---|---|---|
| `diagnosis_id` | str(26) | | **PK** |
| `observation_id` | str(26) | | FK, unique |
| `cycle_id` | str(26) | ? | FK |
| `predicted_class` | `DiseaseClass` | | 6-class |
| `confidence` | float | | 0–1 |
| `all_scores` | JSON | | Full softmax |
| `second_class` | `DiseaseClass` | ? | |
| `below_threshold` | bool | | `< 0.60` → advise inspection |
| `model_version` | str(20) | | **Required for auditability** |
| `inference_ms` | int | ? | |

---

## 11 · `risk_assessments`

| Field | Type | ? | Notes |
|---|---|---|---|
| `assessment_id` | str(26) | | **PK** |
| `run_id` | str(26) | | Groups one execution |
| `cycle_id` | str(26) | ? | FK |
| `block_id` / `source_block_id` | str(26) | | |
| `risk_score` | float | | 0–1 |
| `risk_band` | `BlockState` | | Derived |
| `eta_days` | int | ? | Null below threshold |
| `path_block_ids` | JSON | ? | Route through graph |
| **`confidence`** | float | | **Input quality, not disease certainty** |
| `rainfall_7d_mm` / `forecast_7d_mm` | float | | **Input snapshot** |
| `elevation_tier_used` | `ElevationTier` | | Traceability |
| `model_version` | str(20) | | |
| `is_estimate` | bool | | **Always true** |
| `computed_at` | datetime | | |

---

## 12 · `treatment_options` — Namespace A, seeded

| Field | Type | ? | Notes |
|---|---|---|---|
| `treatment_id` | str(30) | | **PK** slug |
| `name_ms` / `name_en` | str(80) | | |
| `type` | `TreatmentType` | | |
| `applies_to` | JSON | | array of `DiseaseClass` |
| **`rainfast_hours`** | int | ? | **Drives spray-window logic** |
| `dose_text_ms` | str(200) | ? | Verbatim from source |
| `application_method` | `ActionType` | | |
| `reentry_hours` | int | ? | Safety |
| **`source_ref`** | str(200) | | **Mandatory citation** |
| `source_url` | str(255) | ? | |

> **Hard rule:** the agent — and the v2 Overrun Council — may never output a treatment absent from this table.

## 13 · `treatment_applications`

| Field | Type | ? | Notes |
|---|---|---|---|
| `application_id` | str(26) | | **PK** |
| `block_id` / `treatment_id` | | | FK |
| `applied_at` | datetime | | |
| `followed_recommendation` | bool | ? | |
| `recommendation_id` | str(26) | ? | FK |
| **`rain_within_rainfast`** | bool | ? | **Outcome signal — computed after** |
| `rainfall_after_mm` | float | ? | |

---

## 14 · `knowledge_docs`

| Field | Type | ? | Notes |
|---|---|---|---|
| `doc_id` | str(26) | | **PK** |
| **`namespace`** | `KnowledgeNamespace` | | **`local` may never supply dose/product/timing** |
| `title` | str(200) | | |
| `publisher` | str(80) | ? | `MPB` · `DOA Sarawak` · `UNIMAS` · `farmer` |
| `uploaded_by_user_id` | str(26) | ? | Set for `local` only |
| `chunk_index` | int | | |
| `content` | text | | |
| `embedding` | JSON | | Float array |
| `citation` | str(255) | | **Mandatory** |

## 14a · `knowledge_docs_fts` 🔄 v2 *(search index, not a new logical entity)*

SQLite FTS5 virtual table mirroring `knowledge_docs.content`, for the lexical half of the hybrid search described in §L3. No new source of truth — an index only.

---

## 15 · `agent_runs`

| Field | Type | ? | Notes |
|---|---|---|---|
| `run_id` | str(26) | | **PK** |
| `farm_id` | str(26) | | FK |
| `trigger` | str(20) | | `observation` · `scheduled` · `manual` · `setup_validation` |
| `cycle_id` | str(26) | ? | FK |
| **`tools_called`** | JSON | | `[{name, args, latency_ms, result_summary}]` |
| `subagent_invoked` | str(40) | ? | 🔄 v2: now may also be `overrun_council` |
| `llm_model` | str(40) | | |
| `token_count` | int | ? | |
| `started_at` / `completed_at` | datetime | /? | |
| `status` | str(12) | | `ok` · `partial` · `failed` |

> **Keep `tools_called` and show it in the demo.** Visible orchestration convinces judges more than a named protocol.

## 16 · `recommendations`

| Field | Type | ? | Notes |
|---|---|---|---|
| `recommendation_id` | str(26) | | **PK** |
| `run_id` / `block_id` | str(26) | | FK |
| `sequence` | int | | 1 = do first (drain before spray) |
| `action_type` | `ActionType` | | |
| `treatment_id` | str(30) | ? | FK |
| `recommended_at` | datetime | | **When to do it**, not when generated |
| `window_start` / `window_end` | datetime | ? | Viable spray window |
| `reason_ms` | str(300) | | **One sentence. Mandatory.** |
| `speech_template_id` | str(30) | ? | FK |
| **`deferred_from`** | datetime | ? | Set when agent delays |
| **`defer_cause`** | str(40) | ? | `rainfast` · `spread_priority` · `resource` |
| `confidence_note` | str(120) | ? | |

> `deferred_from` + `defer_cause` **are the arbitration record.**

## 17 · `alerts`

| Field | Type | ? | Notes |
|---|---|---|---|
| `alert_id` | str(26) | | **PK** |
| `run_id` / `target_block_id` | str(26) | | FK |
| `recipient_name` / `recipient_phone` | str | ? | **PII** |
| `message_ms` | text | | LLM-drafted |
| `risk_band_shared` | `BlockState` | | **Only this is shared** |
| `status` | `AlertStatus` | | default `draft` |
| **`approved_by_farmer`** | bool | | **default false — never auto-true** |
| `approved_at` / `sent_at` | datetime | ? | |

---

## 18 · `advisor_verdicts`

| Field | Type | ? | Notes |
|---|---|---|---|
| `verdict_id` | str(26) | | **PK** |
| `farm_id` | str(26) | | FK |
| `urgency` | `AdvisorUrgency` | | |
| `reason_code` | str(30) | | `heavy_rain_recent` · `active_infection` · `stale` · `protected_stable` · `no_action_needed` |
| `reason_ms` | str(300) | | Spoken sentence |
| `suggested_date` | date | ? | |
| `days_until_recommended` | int | ? | |
| `last_cycle_at` | datetime | ? | **Evidence for "why not yet"** |
| `last_cycle_result` | str(20) | ? | `all_healthy` · `some_alerted` · `some_harmed` |
| `days_since_last_cycle` | int | | |
| `rain_since_last_cycle_mm` | float | | |
| `blocks_all_protected` | bool | | |
| **`related_recommendation_id`** | str(26) | ? | 🔄 v2 — links this verdict to the Home screen's current Priority Action card |
| `computed_at` | datetime | | |

---

## 19 · `speech_templates`

| Field | Type | ? | Notes |
|---|---|---|---|
| `template_id` | str(30) | | **PK** |
| `language` | `Language` | | |
| `category` | str(30) | | `setup_prompt` · `diagnosis` · `recommendation` · `validation` · `alert` |
| `text_template` | str(300) | | With `{slots}` |
| `slots` | JSON | | Slot names |
| `audio_clip_uri` | str(255) | ? | **MVP: bundled pre-recorded `.wav`** |
| **`translated_by`** | str(80) | ? | **Native-speaker provenance** |
| `verified` | bool | | |

## 20 · `slot_vocabulary`

| Field | Type | ? | Notes |
|---|---|---|---|
| `slot_id` | str(40) | | **PK** e.g. `day_thursday` |
| `slot_type` | str(20) | | `day` · `number` · `action` · `state` |
| `text_ms` / `text_iba` | str(60) | | |
| `verified` | bool | | |

## 21 · `audio_cache` *(optimised tier only)*

| Field | Type | ? | Notes |
|---|---|---|---|
| `hash` | str(64) | | **PK** — `sha256(template_id + slots + lang + seed)` |
| `template_id` | str(30) | | FK |
| `language` | `Language` | | |
| `slots_json` | JSON | | Rendered values |
| `audio_path` | str(255) | | File on volume |
| `duration_ms` | int | | |
| `seed` | int | | **Reproducibility** |
| `generated_at` | datetime | | |

---

## 22 · `weather_observations` / `weather_forecasts`

**Observations** — PK `(station_id, observed_date)`: `rainfall_mm`, `source`, `is_cached_fallback` (demo insurance).

**Forecasts** — PK `(station_id, forecast_date, issued_at)`: `rainfall_mm`, `probability`. `issued_at` in the key preserves forecast history.

---

## 23 · `calendar_sync_grants` 🔄 v2

| Field | Type | ? | Notes |
|---|---|---|---|
| `grant_id` | str(26) | | **PK** |
| `farm_id` | str(26) | | FK |
| `provider` | `CalendarProvider` | | `google_calendar` for v2 |
| `granted_at` | datetime | | |
| `revoked_at` | datetime | ? | Check before every future write |

## 24 · `council_debates` 🔄 v2

| Field | Type | ? | Notes |
|---|---|---|---|
| `debate_id` | str(26) | | **PK** |
| `run_id` | str(26) | | FK → `agent_runs` |
| `block_ids_considered` | JSON | | Overrun set |
| `transcript` | JSON | | Each sub-agent's argument — demo evidence |
| `ranked_output` | JSON | | array of `{block_id, rank, rationale_ms}` — deliberately dose-less |
| `created_at` | datetime | | |

---

## Phone-side (Expo SQLite outbox) 🔄 v2 — was `sqflite` in v1, same purpose

**Not a full mirror.** Only what's needed for offline capture.

| Table | Purpose |
|---|---|
| `outbox_observations` | image path, block_id, captured_at, sync_status |
| `outbox_walk_samples` | buffered GPS/baro trace during the walk |
| `cached_farm_state` | read-only snapshot: blocks + current states |

---

## Privacy & retention

| Concern | Handling |
|---|---|
| PII | `users.phone`, `blocks.external_owner_*`, `alerts.recipient_*` — encrypt at rest |
| Neighbour data | Farmer-entered only. **Never scraped or inferred** |
| External blocks | **Risk band only.** No diagnosis, photo, or treatment history |
| Alerts | Never dispatched without `approved_by_farmer = true` |
| Calendar sync | Never dispatched without a `calendar_sync_grants` row with no `revoked_at` |
| **Land boundaries** | **Never recorded.** Only `elevation_rank` ordering + proportional canvas spacing (v2) — neither is a georeferenced map |


---

## 🔄 v2 additions -- 2026-09-24

### `farm_restore_codes` (new table)

| Column | Type | Notes |
|---|---|---|
| `farm_id` | ULID, PK, FK `farms` | One code per farm; the shared demo farm never gets one |
| `code` | `String(16)`, unique | `XXX-XXX-XXX` from an unambiguous alphabet (no 0/O/1/I/L). Rotatable (`POST /farms/{id}/restore-code/rotate`) |
| `created_at` | timestamp | |

Why: there are no accounts -- a phone's saved `farm_id` is its only link to a farm. `POST /restore {code}` re-attaches a new or reset phone; Google Calendar ownership follows because it is keyed on `farm_id`.

### Timestamps -- one clock

All timestamp columns use `KuchingDateTime` (`app/models/base.py`): aware inputs are converted to Asia/Kuching, naive inputs are taken as Kuching, reads are always aware Kuching. Before this, SQLite dropped the zone, so phone-sent UTC (`toISOString()`) and server `now_kuching()` values sat 8 h apart in the same tables. Local rows written before the fix were corrected (backup `backend/huluhilir.db.bak-2026-09-24-tz`); Cloud SQL (Postgres `timestamptz`) always stored the right instant.
