# L1_MODEL_ROADMAP.md — MobileNetV3-Small Training

> **Layer:** L1 · CNN Diagnosis · **Owner:** Nathan
> Locked decisions live in `docs/PROJECT_SPEC.md` §3 L1. This file is the *how*.
> Non-negotiables in `.claude/skills/pepperdex-rules/SKILL.md` §9.
>
> ⚠️ **v2 note:** training methodology, classes, splits, and evaluation below are **unchanged** — this file's core content was already correct. Only two things shifted: **`.onnx` is now the confirmed sole primary inference path** (Gemini Vision, briefly used in v1 as a bug workaround, is removed — see `PLAN.md` §3), and **`.tflite` on-device deployment is optional/deferred**, not co-equal. Where this file still says `tflite_flutter` (a Flutter package), the v2 equivalent is `react-native-fast-tflite` — relevant only if the deferred on-device tier is pursued.

---

## 0 · What this model is for

The classifier **does not diagnose**. It **screens** an image and hands a class plus a confidence to the agent, which then reasons with rainfall, terrain and the rules table.

| It does | It does not |
|---|---|
| Flag an image as consistent with foot rot | Confirm a diagnosis |
| Emit a confidence the agent can act on | Decide treatment |
| Timestamp an outbreak for the spread model | Locate the lesion (no bounding boxes) |

**Unit of analysis is the block, not the plant.** One confident image per block is enough. This is why classification beats detection here and why per-leaf instance matching is unnecessary.

### 0.1 · Why classification, not counting — presence over prevalence

For a contagious, water-borne pathogen, **one confirmed case is the operative signal, not a ratio.** This is already how the rest of the system behaves: a single confirmed `collar_lesion` escalates a block to Harmed regardless of how many other leaves nearby are healthy, and that single confirmation is what `compute_spread` projects downhill. A count such as "2 of 10 leaves infected" would not change the block's state, would not change what the spread model projects, and would not change the agent's recommendation — nothing downstream consumes a prevalence ratio.

**This is why object detection with per-leaf counting was considered and set aside**, not merely because it costs more to build:

- **Nothing downstream would use the count.** The block-state machine, the spread model and the agent all react to *presence*, not *quantity*. Building a signal nothing consumes is wasted model risk.
- **Static, elevated cameras would help detection more than a handheld phone would** — but that requires hardware, and "no hardware purchase" is a commitment already made. Even elevated coverage does not resolve overlapping, occluded leaves in dense canopy.
- **No annotated dataset exists for this at all.** Classification already has no open *Piper nigrum* dataset; a detection dataset needing per-leaf bounding boxes across a farm's canopy is a harder ask still, on a shorter timeline.

**The counter-question worth answering directly: farmers can already see their own plants — why classify at all?** Because the classifier is not competing with the farmer's eyes. It converts an intuitive observation into a timestamped, confidence-scored, terrain-aware signal the rest of the system can act on — something the Advisor can later cite (*"all blocks were healthy 6 days ago, only 8 mm of rain since"*), something with a confidence score the agent can defer to physical inspection when uncertain, and something that tells a farmer their *downhill neighbour* is at risk in four days, which no amount of looking at their own plant would reveal. The model gives the agent eyes on the catchment, timed against the next rain — not better eyes on one plant.

---

## 1 · Classes — six, split by body part, plus a rejection class

| # | Label (code) | Malay UI | Visual signature | Agent implication |
|---|---|---|---|---|
| 0 | `healthy_leaf` | SIHAT (DAUN) | Uniform green leaf, intact margins | Confirms leaf checked — no action |
| 1 | `healthy_collar` | SIHAT (PANGKAL) | Normal stem base, no lesion | Confirms collar checked — no action |
| 2 | `foliar_yellowing` | DAUN MENGUNING | Chlorosis, interveinal or marginal | Ambiguous → context decides |
| 3 | `collar_lesion` | LESI PANGKAL | Dark water-soaked lesion at stem base | **Harmed — urgent** |
| 4 | `defoliation_wilt` | GUGUR DAUN / LAYU | Wilted, drooping, bare nodes at branch scale | Advanced → triage |
| 5 | `unrelated` | TIADA KAITAN | Not a plant subject — soil, hand, sky, blur | Retake prompt, not recorded as a check |

**Why healthy is split by body part, not merged.** `capture_target` — the farmer's declared intent (leaf / collar / whole-vine) — is a button pressed *before* the photo, not verified ground truth. A farmer can tap "collar" and photograph a leaf by mistake. If `healthy` were one merged class, that mistake would silently return "healthy" and the collar would never actually have been examined — the single most dangerous gap in the whole diagnosis flow, since the collar is where foot rot is earliest and most decisive. Splitting `healthy_leaf` from `healthy_collar` turns the model's own prediction into an independent cross-check on what body part was actually photographed:

```
capture_target="collar"  +  predicted_class ∈ {healthy_leaf, foliar_yellowing}
    → MISMATCH: photo looks like a leaf, not a collar
    → "This looks like a leaf. Please retake, aiming at the base of the stem."
    → not recorded as a valid collar check

capture_target="collar"  +  predicted_class ∈ {healthy_collar, collar_lesion}
    → consistent → valid check, recorded
```

**Why `unrelated` exists, and why it needs real data, not zero examples.** A softmax classifier cannot output a class it has never seen — "no training data" is not a lighter version of this class, it structurally never fires. A small real set (soil, a hand, sky, farm clutter, blurry near-misses) is enough: the goal is not fine understanding of "not a plant," only enough contrast that the model stops confidently mislabelling obvious junk as a health class. This is complementary to, not a replacement for, the `confidence < 0.60` threshold in §6.3 — `unrelated` catches *obvious* non-subjects with a specific message; the confidence threshold catches *ambiguous* real photos.

**Why there is no `healthy_canopy` or a seventh class for it.** `defoliation_wilt` was considered at a wide, whole-vine framing, which would need a matched healthy-canopy negative and a genuinely impractical capture distance on a working plantation row. Instead, `defoliation_wilt` is captured at a **medium** distance (§3.2) — close enough to be practical, far enough to show bare nodes and leaf density. At that distance the domain gap to the other classes is smaller, and the residual gap is absorbed by the confidence threshold rather than needing a dedicated class. This is a deliberate, accepted trade-off, not an oversight.

**Ordering matters for the confusion matrix.** Expect `foliar_yellowing` ↔ `healthy_leaf` confusion (early chlorosis is subtle) and `foliar_yellowing` ↔ `defoliation_wilt` (progression is continuous). Report these honestly rather than tuning them away.

---

## 2 · Dataset size and split

### Target counts

| Class | Minimum viable | Comfortable | Notes |
|---|---|---|---|
| `healthy_leaf` | 100 | 200 | No infected farm needed — start today |
| `healthy_collar` | 100 | 200 | No infected farm needed; **same framing as `collar_lesion`, disease-free** |
| `foliar_yellowing` | 120 | 250 | Non-specific; also collectible from nutrient-deficient vines |
| `collar_lesion` | 120 | 250 | **Hardest and most important** — needs an active infection |
| `defoliation_wilt` | 100 | 200 | Advanced cases; medium framing (§3.2), visually distinct |
| `unrelated` | 60 | 120 | Soil, hand, sky, blur — casual capture, no field visit required |
| **Total** | **~600** | **~1,220** | Before augmentation |

**Do not chase a big number.** Well-labelled originals with honest per-class recall beat thousands of scraped images of uncertain provenance. Published black pepper work reached high accuracy on ~2,800 originals; the same architecture works at this scale with more conservative claims.

**Use the existing `capture_target` field to tag collection, not just app use.** `observations.capture_target` (`leaf` / `collar` / `whole_vine`, in `docs/DATA_MODEL.md` §9) should be set on every training image at capture time, so per-domain balance can be checked before training — not discovered after.

### Split — stratified 70 / 15 / 15

```
train   70%   ~420 imgs   → augmented to ~2,900
val     15%   ~90  imgs   → NO augmentation
test    15%   ~90  imgs   → NO augmentation, touched once
```

### 🔴 The two rules that make the numbers real

**Rule 1 — Split BEFORE augmenting.** If an augmented copy of a training image lands in val or test, accuracy becomes meaningless. This is the single most common way hackathon models produce fake 99% scores.

**Rule 2 — Split by SOURCE, not by file.** Multiple photographs of the *same vine* must all land in the same split. Otherwise the model memorises that plant and you measure recall of a specific vine, not of a disease.

```python
# group images by source_id (vine/plant identifier) before splitting
from sklearn.model_selection import GroupShuffleSplit
gss = GroupShuffleSplit(n_splits=1, test_size=0.30, random_state=42)
train_idx, temp_idx = next(gss.split(X, y, groups=source_ids))
```

**Capture protocol:** name files `{class}_{source_id}_{n}.jpg` — e.g. `collar_lesion_farmJulau03_vine07_2.jpg`. The `source_id` is what the grouped split keys on.

---

## 3 · Data preparation

### 3.1 Sourcing

| Source | Status | Use |
|---|---|---|
| **Own Sarawak capture** | Primary | Fine-tuning, all six classes |
| Sreethu et al. (Kerala) | On request — email sent | Pretrain if granted |
| Chen/Bong/Lee (UNIMAS, Sarawak-grown) | On request — email sent | **Best fit if granted** |
| PlantVillage | Public | Generic leaf-lesion pretraining only (bell pepper ≠ *Piper nigrum*) |
| Chili / potato Phytophthora sets | Public | **Do not fine-tune on these** — different host, different morphology |

**Two-stage strategy:** pretrain on public leaf-disease imagery for generic lesion features → fine-tune on the Sarawak set → **report accuracy at both stages.** Building the local set is itself a contribution; no open *Piper nigrum* dataset exists.

### 3.2 Capture protocol — framing differs by class, this is not uniform

Foot rot's decisive sign is at the **collar and stem base**, but every public dataset is leaf-only. **Concentrate local capture there.**

**One dominant subject per image, matching what a farmer naturally photographs.** Capture the *whole* leaf or the *whole* collar region — not a tight macro crop of just the symptomatic texture. A model trained on cropped fragments and deployed against whole-leaf farmer photos suffers a train/inference mismatch, which is the most common reason a model scores well in Colab and fails on the phone.

**`defoliation_wilt` is shot medium, not wide.** Defoliation and wilting are branch-scale symptoms — sparse foliage, drooping habit, bare nodes — invisible in a single-leaf or single-collar close-up. A full wide, whole-vine shot was considered and set aside as impractical on a working plantation row; medium distance keeps the symptom legible while staying practical to capture (§1).

| Class | Subject | Framing |
|---|---|---|
| `healthy_leaf` | One whole leaf, or a small consistent cluster | Close — subject fills ≥ 50% of frame |
| `healthy_collar` | A normal, uninfected collar / stem-base | Close-medium — **identical framing to `collar_lesion` below**, disease-free |
| `foliar_yellowing` | One whole leaf | Close — subject fills ≥ 50% of frame |
| `collar_lesion` | The collar / stem-base region | Close-medium — lesion visible with enough surrounding stem and soil for context |
| `defoliation_wilt` | A branch section | Medium — foliage density and drooping habit must be legible |
| `unrelated` | Soil, hand, sky, farm clutter, blur | No protocol — casual capture, any framing |

**Why `healthy_collar` matters more than it looks.** Without it, `collar_lesion` would be the only class the model has ever seen in the collar domain — a farmer's normal, healthy stem-base photo would have no matching reference and risks a false-positive foot rot alert simply because of which body part was photographed, not what condition it's in. See §1 for the full reasoning. Frame this class identically to `collar_lesion` — same distance, same angle range, same background variety — so the *only* difference between the two classes is presence or absence of the lesion, not photography style.

| Parameter | Spec |
|---|---|
| Distance | 20–40 cm for close classes; ~0.8–1.2 m for `defoliation_wilt` (medium) |
| Lighting | Daylight, avoid harsh direct sun and deep shade |
| Background | Natural — do **not** stage on white card; the app sees real farms |
| Angle | Vary deliberately: straight-on, 30°, 45° |
| Per subject | 3–5 shots, varied angle and distance |
| Device | The actual demo phone, plus one other if available |
| Frame content | One label's worth of evidence only — never mix a healthy leaf and a yellowing leaf in the same frame |

**Label at capture time, in the field, with someone who knows the disease.** Retroactive labelling from memory is where silent noise enters. Where uncertain, record it as `unknown` and exclude rather than guess.

### 3.3 Preprocessing pipeline

```
raw photo
  → EXIF-orient correction        (phones rotate; models don't know)
  → centre-crop to square
  → resize 224×224 bilinear
  → RGB, float32
  → normalise with ImageNet stats
        mean = [0.485, 0.456, 0.406]
        std  = [0.229, 0.224, 0.225]
```

**This exact pipeline must be reimplemented in Flutter.** Preprocessing mismatch between training and inference is the top cause of "works in Colab, fails on phone." Write the constants down once and reference them in both places.

### 3.4 Augmentation — train split only

| Transform | Range | Why |
|---|---|---|
| Rotation | ±25° | Farmers hold phones at arbitrary angles |
| Horizontal flip | p=0.5 | No inherent left/right meaning |
| Brightness | ±20% | Canopy shade vs open sun |
| Contrast | ±15% | Overcast vs bright |
| Zoom / random crop | ±15% | Inconsistent standoff distance |
| Slight blur | σ ≤ 1.0, p=0.2 | Handshake, autofocus miss |

**Do NOT use:** vertical flip (gravity is meaningful — collar is at the *bottom*), heavy colour jitter (hue *is* the signal for yellowing), cutout/erasing (may remove the lesion entirely).

**Target ~7× expansion** on train only → ~2,400 images.

---

## 4 · Modelling pipeline

### 4.1 Dependencies

```bash
pip install torch torchvision           # training
pip install onnx onnxruntime            # export + backend inference
pip install onnx2tf tensorflow          # tflite conversion path
pip install scikit-learn matplotlib seaborn pandas pillow
```

> **Path note.** PyTorch → ONNX → TFLite via `onnx2tf` is reliable but has version sensitivities. If it fights you, train in **TensorFlow/Keras** instead — `MobileNetV3Small` is built in and exports to TFLite in two lines. Decide this in prep (EXP-8), not on build day.

### 4.2 Architecture

```python
import torchvision.models as models
import torch.nn as nn

model = models.mobilenet_v3_small(weights='IMAGENET1K_V1')

# Stage A — freeze backbone, train head only
for p in model.parameters():
    p.requires_grad = False

model.classifier[3] = nn.Linear(1024, 6)      # 6 classes
```

### 4.3 Two-stage training

| Stage | Frozen | LR | Epochs | Purpose |
|---|---|---|---|---|
| **A · Head** | All backbone | 1e-3 | 10–15 | Learn the new decision boundary fast |
| **B · Fine-tune** | All but last block | 1e-4 | 10–20 | Adapt features to pepper morphology |

```python
# Stage B — unfreeze the final inverted-residual block
for p in model.features[-3:].parameters():
    p.requires_grad = True
```

### 4.4 Hyperparameters

| Setting | Value | Rationale |
|---|---|---|
| Optimiser | AdamW, `weight_decay=1e-4` | Stable on small data |
| Loss | CrossEntropy + **class weights** | Corrects `collar_lesion` scarcity |
| Batch size | 32 | Fits T4 comfortably |
| Scheduler | `ReduceLROnPlateau`, patience 3, factor 0.5 | Monitors **val recall on `collar_lesion`** |
| Early stopping | patience 7 | Monitors the same metric, **not** val loss |
| Seed | 42, all libraries | Reproducibility |
| Target wall-clock | **< 20 min on Colab T4** | Must be re-runnable live if organisers require on-site training |

```python
# class weights — inverse frequency, normalised
weights = torch.tensor([n_total/(6*n_c) for n_c in class_counts], dtype=torch.float32)
criterion = nn.CrossEntropyLoss(weight=weights.to(device))
```

**Checkpoint on `collar_lesion` recall, not on accuracy or val loss.** Accuracy is dominated by the easy classes; the model you want is the one that misses the fewest early foot-rot cases.

---

## 5 · Export

Produce **both** formats from the same trained weights. Cost is negligible and it keeps the deployment choice open.

```python
# ---- ONNX (backend inference, MINIMAL path) ----
dummy = torch.randn(1, 3, 224, 224)
torch.onnx.export(model, dummy, "huluhilir_l1.onnx",
                  input_names=["input"], output_names=["logits"],
                  opset_version=13,
                  dynamic_axes={"input": {0: "batch"}, "logits": {0: "batch"}})

# ---- TFLite (on-device, OPTIMISED path) ----
# onnx2tf -i huluhilir_l1.onnx -o tf_model
# then: TFLiteConverter.from_saved_model(...) with DEFAULT optimizations
```

### Export targets

| Artifact | Size target | Used by |
|---|---|---|
| `huluhilir_l1.onnx` | < 12 MB | `api` container, `diagnose_leaf` |
| `huluhilir_l1.tflite` | < 6 MB (fp16) | *(deferred)* React Native, `react-native-fast-tflite` — was `tflite_flutter` in v1 |
| `labels.txt` | 6 lines, fixed order | Both — **order must match training** |
| `preprocess.json` | mean, std, size | Both — prevents drift |

**Quantisation:** use **fp16** for TFLite. INT8 requires a representative dataset and can shift the decision boundary on subtle classes like `foliar_yellowing` — not worth the risk at this scale.

### 🔴 Export parity check — mandatory

```python
# same image through all three must agree
assert np.allclose(pytorch_out, onnx_out,   atol=1e-4)
assert np.allclose(onnx_out,    tflite_out, atol=1e-2)   # looser: fp16
```

If predictions disagree, the bug is almost always **preprocessing**, not the model.

---

## 6 · Evaluation

### 6.1 Metrics — report all, in this order

| # | Metric | Why it ranks here |
|---|---|---|
| 1 | **Per-class recall** | **Headline.** A missed foot rot costs a vine; a false alarm costs one inspection walk |
| 2 | **`collar_lesion` recall specifically** | The earliest actionable sign — the model's actual job |
| 3 | Confusion matrix | Shows *which* classes confuse; expect `foliar_yellowing` ↔ `healthy` |
| 4 | Per-class precision & F1 | Handles class imbalance honestly |
| 5 | Overall accuracy | Report **last** — least informative alone |
| 6 | Confidence distribution | Justifies the 0.60 threshold empirically |

```python
from sklearn.metrics import classification_report, confusion_matrix
print(classification_report(y_true, y_pred, target_names=CLASSES, digits=3))
```

### 6.2 Acceptance thresholds

| Metric | Minimum | Good |
|---|---|---|
| `collar_lesion` recall | **≥ 0.75** | ≥ 0.85 |
| `healthy_collar` recall | **≥ 0.75** | ≥ 0.85 |
| `healthy_leaf` recall | ≥ 0.80 | ≥ 0.90 |
| `unrelated` recall | ≥ 0.80 | ≥ 0.90 |
| Macro F1 | ≥ 0.70 | ≥ 0.80 |
| Test-set size | ≥ 80 images | ≥ 130 |

**`healthy_collar` gets the same threshold as `collar_lesion`, not the looser leaf threshold.** These two classes are cross-checks on each other in the same domain (§1) — if the model can't reliably tell a normal stem base from a lesioned one, the whole point of splitting `healthy` by body part is undermined.

**Below minimum → do not ship silently.** Either gather more data, merge `foliar_yellowing` into a coarser class, or state the limitation explicitly in the demo. An honest 0.72 with a stated caveat is defensible; an unstated 0.72 presented as reliable is not.

### 6.3 Confidence threshold

```python
if confidence < 0.60:
    return {"below_threshold": True,
            "advice": "Sila periksa pangkal pokok secara fizikal."}
```

Validate the 0.60 cut empirically: plot confidence against correctness on the test set and pick the point where precision stabilises. **Never assert a diagnosis below threshold** — the app advises physical inspection instead.

### 6.4 Robustness spot-checks

Beyond the test set, verify against realistic field failure modes:

- [ ] Motion-blurred image → low confidence, not confident-wrong
- [ ] Deep shade → still classifies
- [ ] Wrong subject (soil, hand, sky) → classifies `unrelated`, not a health class
- [ ] Different phone camera → consistent prediction
- [ ] Same vine, three angles → same class
- [ ] **Healthy, uninfected collar → classifies `healthy_collar`, not `collar_lesion`** (see §1)
- [ ] **`capture_target="collar"` + photo is actually a leaf → mismatch detected, retake prompted, not recorded as a valid check** (see §1)

The **wrong-subject** case matters most: a farmer will photograph the ground by accident, and a model that returns `collar_lesion` at 0.94 on a photo of dirt destroys trust immediately. The **healthy-collar** case is the second-most important for the same reason in reverse: a normal stem base misclassified as diseased is a false alarm that costs a farmer an unnecessary spray or an anxious inspection. The **capture-target mismatch** check is what the six-class split was built to catch — verify it actually fires before trusting the split to protect against a wrongly-aimed photo.

### 6.5 What to record for the pitch

```
Dataset:     n originals, n augmented, split by source
Stage A:     val acc / val collar recall
Stage B:     val acc / val collar recall
Test:        per-class recall, macro F1, confusion matrix
Latency:     ONNX ___ ms · TFLite on-device ___ ms
Model size:  ONNX ___ MB · TFLite ___ MB
```

**Say this on stage:** *"We optimise for recall on collar lesion, because a false negative costs a vine and a false positive costs one inspection walk."*

---

## 7 · Mobile integration

### 7.1 Two paths — decide by EXP-8

| | **MINIMAL** — backend ONNX | **OPTIMISED** — on-device TFLite |
|---|---|---|
| Where | `api` container, ONNX Runtime **(confirmed sole primary)** | *(deferred)* Phone, `react-native-fast-tflite` |
| Integration cost | Low — one endpoint, Python only | Medium — plugin, asset bundling, tensor shapes |
| Latency | ~200–400 ms incl. upload | ~50–100 ms |
| Debuggable at 3 a.m. | **Easy** — Python logs | Harder — Dart-side errors |
| Demo claim | Weak | **"Diagnosis runs entirely on the phone"** |

**Build MINIMAL first.** Stand up `/tools/diagnose_leaf` regardless — it is ~20 lines and becomes the fallback if TFLite fights you at hour 14.

### 7.2 Flutter integration

```yaml
dependencies:
  react-native-fast-tflite   # was tflite_flutter (Flutter) — only if the deferred on-device tier is pursued
  image: ^4.1.7
```

```
assets/model/
  huluhilir_l1.tflite
  labels.txt
  preprocess.json
```

```dart
// Preprocessing MUST mirror §3.3 exactly
img.Image resized = img.copyResize(cropped, width: 224, height: 224);
// normalise: (pixel/255.0 - mean[c]) / std[c]
```

**Input tensor:** `[1, 224, 224, 3]` float32 · **Output:** `[1, 6]` logits → softmax → argmax.

> ⚠️ **Channel order.** PyTorch uses NCHW; TFLite expects NHWC. `onnx2tf` handles the transpose, but **verify with the parity check in §5** — a silent channel mismatch produces confident nonsense rather than an error.

### 7.3 Contract to the agent

```python
class DiagnoseResponse(BaseModel):
    predicted_class: DiseaseClass
    confidence: float
    all_scores: dict[str, float]      # full softmax — feeds confusion analysis
    second_class: DiseaseClass | None
    below_threshold: bool             # confidence < 0.60
    model_version: str                # REQUIRED — auditability
    inference_ms: int
```

Persists to `observations` + `diagnoses` (see `docs/DATA_MODEL.md` §9–10). `model_version` is mandatory: without it, a later result cannot be traced to the weights that produced it.

### 7.4 · Optional enhancement — multi-sample capture per block

**One image per block remains the minimum and the default (§0).** This section describes an additive enhancement, not a replacement: if a farmer submits more than one photo for a block in a single cycle, the block's state should reflect the worst class seen, not just the last photo taken. This gives the *feel* of broader coverage per block without any change to the model, the training pipeline, or the annotation format above.

```
Block capture (optional): farmer takes 2–4 photos — different leaves or
vines within the same block — instead of exactly one.

Each photo → the SAME diagnose_leaf call, run independently.
No new model. No new endpoint. No new training data.

Aggregation, worst-class-wins:
    if ANY photo → collar_lesion            → block state = Harmed
    elif ANY photo → defoliation_wilt       → block state = Harmed
    elif ANY photo → foliar_yellowing       → flag for review
    elif ALL non-unrelated photos → healthy_* → block state = Protected
    (unrelated photos: excluded from the count, farmer re-prompted to retake)

Reported to the farmer as, e.g.:
    "3 of 4 sampled leaves healthy; 1 shows foliar yellowing."
```

**Why worst-class-wins, not majority or average.** This follows directly from §1 — presence, not prevalence, drives every downstream decision. A single confirmed `collar_lesion` among four photos should escalate the block exactly as it would if it were the only photo taken; averaging or requiring a majority would silently suppress an early, decisive signal. `unrelated` photos are excluded rather than counted as evidence either way — a photo of the ground says nothing about the plant's health.

**Scope note.** This is a capture-flow and aggregation change only — `CaptureChecker` in `docs/PROJECT_SPEC.md` §6 accepts more than one image per block per cycle, and the state derivation applies the rule above. It does not change the class set (§1) or the training pipeline (§2–§6).

**Considered and set aside:** an earlier proposal asked the farmer to manually rank leaf types by relative quantity before saving. This was dropped — it depends on a prevalence signal that, per §1, nothing downstream consumes, and it reintroduces exactly the kind of farmer judgment call the rest of this system is designed to remove. See `docs/VALIDATION_CHECKLIST.md` § Scope decisions.

---

## 8 · Prep checklist

| # | Task | Blocks | ☐ |
|---|---|---|---|
| 1 | Confirm pre-build ruling (EXP-1) — may weights be brought on-site? | Everything | ☐ |
| 2 | Decide PyTorch vs Keras path (EXP-8) | Export toolchain | ☐ |
| 3 | Collect ≥ 100 `healthy_leaf` images | No infected farm needed — start today | ☐ |
| 3a | Collect ≥ 100 `healthy_collar` images (§1) — same framing as `collar_lesion`, disease-free | No infected farm needed | ☐ |
| 3b | Collect ≥ 60 `unrelated` images (§1) — soil, hand, sky, blur | No field visit needed — can shoot casually | ☐ |
| 4 | Secure access to an infected farm for `collar_lesion` | Hardest class | ☐ |
| 5 | Field-label with someone who knows the disease | Label integrity | ☐ |
| 6 | Implement grouped split by `source_id` | Metric validity | ☐ |
| 7 | Train, hit acceptance thresholds (§6.2) | — | ☐ |
| 8 | Export both formats; **parity check passes** | Deployment choice | ☐ |
| 9 | Measure on-device latency + size | Path decision | ☐ |
| 10 | Robustness spot-checks (§6.4) | Demo trust | ☐ |
| 11 | Record metrics table for the pitch | Presentation | ☐ |

> **If the organiser ruling is "on-site only":** the two-stage fine-tune runs in ~15 min on a T4, so schedule it in **Block A** and run it in parallel with repo setup. Images and labels are data assets, not code — gather them regardless.

---

## 9 · Honest framing

| Don't say | Say |
|---|---|
| "diagnoses foot rot" | "screens for symptoms consistent with foot rot" |
| "99% accurate" | "per-class recall of X on a held-out test set of N images" |
| "trained on thousands of images" | "N originals, augmented to M, split by source vine" |
| "detects the disease" | "flags the block for inspection and timestamps the outbreak" |

**The classifier was never the novelty.** The terrain graph and the agent arbitration are. A modest, honestly-reported model that feeds a good decision layer is a stronger position than an overclaimed one — and it is the position the proposal already commits to.
