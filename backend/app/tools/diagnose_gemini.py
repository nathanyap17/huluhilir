"""Vision-model classifier — an alternative L1 backend to the ONNX CNN.

**Why this exists.** The trained MobileNetV3-Small reaches macro F1 0.934 on
its own held-out test set, but probing the exported model with flat colour
fields showed it confidently wrong on inputs it should reject outright
(solid black -> `healthy_leaf` 0.78), and every plausible preprocessing
variant reproduced that. It was trained on ~530 originals, largely generated
rather than photographed, and it does not generalise to real field photos.
See docs/BUILD_LOG.md.

**What this does NOT change.** The six-class contract is unchanged, and the
classifier still only ever produces a *class*. Dose, product and timing come
from the rules table and nowhere else (huluhilir-rules §2) — swapping the
vision backend cannot reach them, because this module has no access to them.

**On reporting accuracy.** The 0.934 figure belongs to the CNN, measured on
the CNN's test set. It says nothing about this backend, which has not been
evaluated on that set. Whichever backend is deployed, the number quoted
should be the number measured for *that* backend — see
`scripts/eval_classifier.py` for producing one.
"""
from __future__ import annotations

import base64
import json
import logging
import re
import time
from pathlib import Path

from app.config import settings

logger = logging.getLogger(__name__)
from app.schemas.diagnosis import DiagnoseLeafResult
from app.schemas.enums import CaptureTarget, DiseaseClass

# The contract. A vision model will happily invent a seventh category, so the
# response is validated against this rather than trusted.
CLASSES = [c.value for c in DiseaseClass if c.value != "unknown"]

_PROMPT = """You are grading ONE photograph from a Sarawak black pepper (Piper nigrum)
farm, for Phytophthora foot rot screening.

Return ONLY this JSON object. No prose, no markdown fence:
{"class": "<exact label>", "confidence": <0.0-1.0>, "reason": "<max 12 words>"}

## Decide in this order

STEP 1 — Is this an assessable pepper plant part?
If the frame is soil, sky, a hand, a tool, a building, a flat colour field, a
screenshot, an animal, a different crop, or too blurred/dark to judge, the
answer is "unrelated". Stop there. Answering "unrelated" is a CORRECT and
useful outcome, not a failure -- never reach for a plant class to seem helpful.

STEP 2 — Which part of the plant fills most of the frame?
- Mostly LEAVES (broad, glossy, heart-shaped, prominent parallel veins)
  -> choose between healthy_leaf and foliar_yellowing.
- Mostly the STEM BASE / COLLAR (thick woody stem meeting soil, often against
  a support post) -> choose between healthy_collar and collar_lesion.
- A whole vine or branch where the STORY is drooping/dying foliage
  -> defoliation_wilt.

STEP 3 — Within that part, grade severity.

## The six labels

healthy_leaf
  A pepper leaf that is GREEN. Any ordinary green counts: deep green, mid
  green, yellow-green new growth, olive, or green under warm/dim light.
  Minor blemishes, dust, insect nibbles, a torn edge, water droplets and
  shadows are all still healthy_leaf.
  >> This is the DEFAULT for any leaf that is predominantly green. Do not
  >> escalate to a disease class because of lighting, shadow, camera white
  >> balance, or a couple of small spots.

foliar_yellowing
  Genuine chlorosis: leaf tissue that has actually LOST green pigment and
  turned yellow, pale, or bleached — typically between the veins or along the
  margins, while the veins themselves stay greener. The yellowing must be a
  clear feature of the leaf itself, not a warm-toned photograph of a green
  leaf, and not simply a young pale-green shoot.
  >> If you are hesitating between healthy_leaf and foliar_yellowing, and the
  >> leaf still reads as basically green, answer healthy_leaf.

healthy_collar
  The stem base / collar of a vine, intact: uniform bark, no dark sunken
  patch, no oozing, no girdling. Surrounding wet soil or mud is fine.

collar_lesion
  A dark brown/black, water-soaked or sunken lesion ON the stem base itself,
  often spreading around it. This is the earliest treatable sign of foot rot
  and the single most important class to get right.
  >> The lesion must be on the PLANT TISSUE. Dark wet SOIL, mud splash, shadow
  >> at the stem base, or a dark support post is NOT a lesion.

defoliation_wilt
  Advanced decline of a whole vine or branch: leaves limp, drooping, curled,
  browning or already shed, bare nodes and exposed stems. The impression is a
  plant that is dying or dead.
  >> Requires visible WILTING or LEAF LOSS. A healthy green vine photographed
  >> from a distance is NOT defoliation_wilt. Green foliage with normal turgor
  >> is never this class, however many leaves are in frame.

unrelated
  Not an assessable pepper plant part (see STEP 1).

## Confidence
Your honest certainty. Use 0.85+ only when the class is unmistakable, 0.5-0.7
when plausible but not certain, below 0.4 when you are largely guessing. A
low confidence is more useful to a farmer than a confident wrong answer.

## Never
Never name a treatment, chemical, dose, or timing. You classify only."""


def _media_path(image_uri: str) -> Path:
    """Accepts either a filesystem path or a served /media/<name> URI."""
    if image_uri.startswith("/media/"):
        return Path(settings.media_root) / image_uri.split("/media/", 1)[1]
    return Path(image_uri)


def _extract_json(text: str) -> dict:
    match = re.search(r"\{.*\}", text, re.S)
    if not match:
        raise ValueError(f"no JSON object in model reply: {text[:160]}")
    return json.loads(match.group(0))


async def diagnose_leaf_gemini(
    observation_id: str, image_uri: str, capture_target: CaptureTarget
) -> DiagnoseLeafResult:
    import litellm

    start = time.perf_counter()
    # A dedicated vision model, separate from the agent's chat model: the two
    # are chosen for different jobs and there is no reason a change to one
    # should silently re-point the other.
    model = settings.vision_model or settings.litellm_model
    path = _media_path(image_uri)
    encoded = base64.b64encode(path.read_bytes()).decode()

    # Vertex project/location are passed EXPLICITLY rather than relying on
    # ambient env. The ADK path works because get_adk_model() sets
    # VERTEXAI_PROJECT/VERTEXAI_LOCATION into os.environ itself; this module
    # calls litellm directly and inherits no such setup, which is the most
    # likely reason the call was failing immediately rather than over the
    # network.
    vertex_kwargs = {}
    if model.startswith("vertex_ai/"):
        if settings.vertexai_project:
            vertex_kwargs["vertex_project"] = settings.vertexai_project
        vertex_kwargs["vertex_location"] = settings.vertexai_location

    response = await litellm.acompletion(
        model=model,
        messages=[{
            "role": "user",
            "content": [
                {"type": "text", "text": _PROMPT},
                {"type": "image_url",
                 "image_url": {"url": f"data:image/jpeg;base64,{encoded}"}},
            ],
        }],
        temperature=0,  # a classifier should not be creative
        # Gemini 2.5 emits internal reasoning tokens that are billed against
        # max_tokens BEFORE any visible content. At 160 the budget was spent
        # thinking and `content` came back empty, so every reply failed to
        # parse and every observation silently fell through to the CNN --
        # which looked like a working Gemini backend returning "unrelated".
        # The reply itself is ~40 tokens; the headroom is for the thinking.
        max_tokens=2048,
        **vertex_kwargs,
    )
    message = response.choices[0].message
    raw = (message.content or "").strip()
    inference_ms = int((time.perf_counter() - start) * 1000)

    # A parse failure and a genuine "unrelated" verdict must stay tellable
    # apart. Both end up as `unrelated`, so without logging, a backend that
    # silently failed to parse EVERY reply would look identical to one
    # working correctly on unclear photos -- and would quietly return
    # "unrelated" for real diseased leaves too.
    # An unparseable reply RAISES rather than degrading to `unrelated`.
    #
    # That distinction matters more than it looks: a silent fallback to
    # `unrelated` is indistinguishable from a correct "I cannot grade this"
    # verdict, so a backend that failed to parse every single reply would look
    # healthy on unclear photos while returning `unrelated` for genuinely
    # diseased leaves too. Raising hands the observation to the local CNN
    # instead (see routers/diagnosis.py), and `model_version` in the stored
    # row then says plainly which model actually decided.
    try:
        parsed = _extract_json(raw)
        predicted = str(parsed.get("class", "")).strip()
        confidence = float(parsed.get("confidence", 0.0))
    except (ValueError, json.JSONDecodeError, TypeError) as exc:
        raise ValueError(f"unparseable classifier reply: {raw[:200]!r}") from exc

    # An off-contract label IS a real verdict from a working parse, so it is
    # kept as "could not grade this" rather than coerced to the nearest
    # plausible class -- silently mapping an invented category onto a real one
    # would fabricate a diagnosis.
    if predicted not in CLASSES:
        predicted, confidence = DiseaseClass.unrelated.value, 0.0

    confidence = max(0.0, min(1.0, confidence))

    # This backend returns one label, not a distribution, so all_scores is the
    # honest degenerate form rather than invented per-class numbers. Anything
    # downstream that needs a runner-up must handle its absence.
    return DiagnoseLeafResult(
        observation_id=observation_id,
        predicted_class=predicted,
        confidence=round(confidence, 4),
        all_scores={predicted: round(confidence, 4)},
        second_class=None,
        below_threshold=confidence < settings.confidence_threshold,
        # diagnoses.model_version is String(20). The full LiteLLM id
        # ("vertex_ai/gemini-2.5-flash") overflows it, and Postgres rejects
        # the row outright where SQLite silently truncated -- so keep just the
        # model name and clamp. The full id is already recorded per agent run.
        model_version=model.rsplit("/", 1)[-1][:20],
        inference_ms=inference_ms,
        mismatch_flag=_mismatch(capture_target, predicted),
    )


def _mismatch(capture_target: CaptureTarget, predicted: str) -> str | None:
    from app.tools.diagnose import check_capture_mismatch

    return check_capture_mismatch(capture_target, predicted)
