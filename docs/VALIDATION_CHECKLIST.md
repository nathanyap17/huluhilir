# VALIDATION_CHECKLIST.md

> **Experiments run in `../sandbox/EXPERIMENTS.md`**, deliberately outside this repo.
> This file tracks *status and consequences* — the runnable code lives there.
> Update this after each sandbox session.

---

## Status board

| EXP | Item | Owner | Status | Consequence if failed |
|---|---|---|---|---|
| **1** | Pre-build ruling from organisers | Zoe | ✅ PASS | Pre-trained weights & pre-recorded audio allowed on-site |
| **2** | MMS Iban TTS exists + intelligible | Nathan | ✅ PASS | Both Iban + BM work (~0.3–0.5s); native speaker review pending |
| **3** | Ollama reachable from phone over hotspot | Nathan | ⏳ BLOCKED | **No fallback — must be solved** (test when phone available) |
| **4** | Barometer availability + drift | Nathan | ⏳ BLOCKED | MINIMAL tier only; don't promise OPTIMISED live |
| **5** | LLM tool-calling reliability ≥8/10 | Nathan | ✅ PASS | qwen2.5:14b (10/10) + gemma4:e2b (5/5); gemma2:9b eliminated (0/10) |
| **6** | GPS accuracy under canopy | Nathan | ⏳ BLOCKED | Wider block spacing in demo farm |
| **7** | CNN trains <20 min, 6 classes | Nathan | ✅ PASS | MobileNetV3-Small trained: Macro F1 0.934, collar recall 95.2%, unrelated recall 92.3% |
| **8** | `.tflite` + `.onnx` export agree | Nathan | ✅ PASS | `huluhilir_l1.onnx` ready in `classifier/best-model/`, ONNX parity verified (100% match) |
| **9** | Weather APIs + cached fallback | Abraham | ⚠️ PARTIAL | data.gov.my works, cached JSON saved; Sarawak CKAN DNS unreachable |
| **10** | SRTM DEM sanity | Nathan | ✅ PASS | 10.0m elevation for Kuching — plausible |
| **11** | scrcpy mirroring stable | Nathan | ⏳ BLOCKED | scrcpy v4.1 installed; phone needed to test |
| **12** | ~25 Iban templates + audio clips | Abraham | ⏳ BLOCKED | BM-only prompts (needs native Iban speaker) |
| **13** | GCP deploy pipeline proven in sandbox | Nathan | ✅ ACCOUNT READY | Project `sfws-aicc-workspace-1` (personal account, not the org-restricted team project) billing-active, region asia-southeast1, all required APIs enabled, Firebase attached. Vertex AI chosen over Gemini API key. Actual Cloud Run deploy (`./deploy-cloud.sh`) still pending — no app to deploy until Block C exists. See `docs/BUILD_LOG.md` § Cloud Gate. |
| **14** | `capture_target` vs predicted body part mismatch fires correctly | Nathan | ⏳ PENDING | Six-class split gives no safety benefit — flag as limitation (test with model/photos) |

---

## Blocking items — resolve before build day

**EXP-1, 2, 3, 4, 5** are blocking. Of these:

- **EXP-1 is resolved.** Organisers confirmed pre-trained model checkpoints and pre-recorded audio may be brought on-site. Live training in Block A is not required; pre-recorded audio assets are fully usable.
- **EXP-2 is unblocked for synthesis.** Both Iban and BM models exist and synthesize in ~0.3–0.5s. Native speaker confirmation remains pending.
- **EXP-3 has no fallback.** If the phone cannot reach the laptop over your own hotspot, the entire demo fails. Solve this first when phone is available.
- **EXP-5 is resolved.** `gemma2:9b` failed completely (0/10, no tool-calling capability). `qwen2.5:14b` (10/10) and `gemma4:e2b` (5/5) are locked in as primary/backup.

---

## Environment readiness

Tracked in `../WORKSPACE_SETUP.md`. Summary:

| Item | Status |
|---|---|
| `flutter doctor -v` all green | ✅ 3.41.2 stable |
| **Gradle cache warmed** (throwaway `flutter create` + `build apk`) | ⚠️ Needs physical phone |
| Docker base images pre-pulled | ✅ Docker v29.1.3 daemon running and responsive |
| Ollama models pulled | ✅ `qwen2.5:14b`, `gemma2:9b`, `gemma4:e2b`, `qwen2.5:1.5b` |
| HuggingFace models pre-downloaded | ✅ `facebook/mms-tts-iba`, `facebook/mms-tts-zlm` |
| Windows firewall: 8000, 8001, 11434 | ⚠️ Needs admin elevation |
| `adb devices` sees the phone | ⚠️ No phone connected |
| APK signing keystore created | ☐ |
| GCP project + billing + APIs enabled *(cloud stretch)* | ⚠️ Pending account setup |
| `gcloud` and `firebase` CLIs authenticated *(cloud stretch)* | ⚠️ `gcloud` (SDK 574.0.0) & `firebase` (v15.28.1 via npx) installed; login pending |
| Gemini API key issued and stored in `.env` *(cloud stretch)* | ☐ |

> ⚠️ **Warming the Gradle cache is the highest-value prep item.** A first Flutter Android build can cost 30–60 minutes of your 24 hours.

---

## Assets ready for build day

| Asset | Owner | Status |
|---|---|---|
| `.tflite` + `.onnx` CNN weights + metrics | Nathan | ✅ `huluhilir_l1.onnx` ready in `classifier/best-model/` (Macro F1 0.934, Recall 95.2%) |
| `healthy_leaf` and `healthy_collar` collected as independent classes, not derived from one bucket (`docs/L1_MODEL_ROADMAP.md` §1) | Nathan | ✅ Incorporated in 6-class model dataset |
| `templates.json` (~25, native-verified) | Abraham | ☐ |
| Pre-recorded `.wav` clip set | Abraham | ⚠️ 6 samples cached in `sandbox/` |
| `rules.json` from MPB/DOA with citations | Abraham | ☐ |
| `weather_cache.json` fallback | Abraham | ✅ Saved (`sandbox/cached_weather_kuching.json`) |
| Demo farm walk trace (GPS/baro trace) | Nathan | ☐ |

---

## Decisions resolved & still open

| # | Question | Decision / Default |
|---|---|---|
| 1 | Riverpod vs Bloc | Whichever Nathan knows |
| 2 | Demo farm: recorded real walk vs synthetic | **Recorded real walk** — proves the loop |
| 3 | On-device TFLite vs backend ONNX for demo | **Backend ONNX** unless TFLite proves stable early |
| 4 | Speech: pre-recorded vs MMS live | **MMS live** viable (EXP-2 passed); pre-recorded fallback; native speaker review pending |
| 5 | Read-only web dashboard for judges | Skip unless ahead of schedule |
| 6 | Cloud deployment on build day | **Attempt only if the 17:00 gate is met.** Local + public GitHub repo is a complete submission |
| 7 | Local LLM model choice | **`qwen2.5:14b`** (primary) / **`gemma4:e2b`** (backup) — `gemma2:9b` eliminated (EXP-5) |

---

## Scope decisions

Features considered and explicitly set aside, with the reasoning — so they don't quietly resurface as "didn't we already plan this?"

| Feature | Status | Why |
|---|---|---|
| Object detection + per-leaf counting (L1) | **Set aside** | No downstream consumer of a prevalence count — block state, spread model and agent all react to *presence* of a class, not quantity. Requires hardware (elevated static cameras) to be workable at all, doesn't resolve leaf occlusion even then, and no annotated dataset exists. See `docs/L1_MODEL_ROADMAP.md` §1. |
| Farmer manually ranks leaf types by relative quantity | **Set aside** | Depends on the same prevalence signal nothing downstream consumes, and reintroduces a farmer judgment call the rest of the system is designed to remove. Superseded by multi-sample capture with worst-class-wins aggregation, which needs no ranking. See `docs/L1_MODEL_ROADMAP.md` §7.4. |
| Multi-sample capture (2–4 photos/block, worst-class-wins) | **Adopted — optional** | Additive to single-photo capture, not a replacement. Same model, same endpoint, no new training data. See `docs/L1_MODEL_ROADMAP.md` §7.4 and `docs/PROJECT_SPEC.md` §6. |

---

## Log

Record decisions that changed the plan. The **decision** matters more than the result.

| Date | EXP | Outcome | Change to plan |
|---|---|---|---|
| 2026-08-20 | EXP-1 | ✅ ALLOWED | Organisers confirmed pre-trained checkpoints and audio assets allowed on-site. Live training in Block A not required. |
| 2026-08-19 | EXP-2 | ✅ PASS | Both Iban & BM MMS models exist, download, and synthesize audio (~0.3–0.5s). Native speaker verdict pending. |
| 2026-08-19 | EXP-5 | ✅ PASS (partial) | `gemma2:9b` has no tool support (0/10). `qwen2.5:14b` (10/10) and `gemma4:e2b` (5/5) work reliably. **Locked model to `qwen2.5:14b` / `gemma4:e2b`.** |
| 2026-08-21 | EXP-7 | ✅ PASS | MobileNetV3-Small 6-class trained: Macro F1 0.934, collar recall 95.2%, unrelated recall 92.3%. Exceeds targets. |
| 2026-08-21 | EXP-8 | ✅ PASS | Model exported to ONNX (`huluhilir_l1.onnx`), 100% agreement with PyTorch baseline. |
| 2026-08-19 | EXP-9 | ⚠️ PARTIAL | `data.gov.my` returns 7-day Kuching forecast. Sarawak CKAN DNS unreachable. **Cached JSON fallback saved to `sandbox/cached_weather_kuching.json`.** |
| 2026-08-19 | EXP-10 | ✅ PASS | SRTM API returns 10.0m elevation for Kuching — plausible. DEM cross-check viable. |
| 2026-08-19 | EXP-13 | ⏳ PENDING | `gcloud` CLI verified installed on host. Full pipeline test pending 17:00 gate on build day. |
