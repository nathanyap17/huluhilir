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

_PROMPT = """You grade ONE photograph from a Sarawak black pepper (Piper nigrum) farm,
for Phytophthora foot rot screening. Real field photos are messy: soil, hands,
support posts, other plants and poor light are normal and do NOT by themselves
make a photo ungradeable.

Return ONLY this JSON object. No prose, no markdown fence:
{"class": "<exact label>", "confidence": <0.0-1.0>, "reason": "<max 12 words>"}

## The six classes

| label | domain / body part | visual signature |
|---|---|---|
| healthy_leaf     | Leaf domain   | Uniform green leaf, intact margins |
| healthy_collar   | Collar domain | Normal stem base, no lesion |
| foliar_yellowing | Leaf domain   | Chlorosis, interveinal or marginal |
| collar_lesion    | Collar domain | Dark water-soaked lesion at stem base |
| defoliation_wilt | Whole branch  | Wilted, drooping, bare nodes |
| unrelated        | Non-plant     | Soil, hand, sky, blur, farm clutter |

## How to decide

STEP 1 — Is there ANY assessable pepper tissue in the frame?
If pepper leaf or stem tissue is visible at all and you can judge its
condition, you MUST pick one of the five plant classes. Background soil, a
hand holding the stem, a support post, mud, other plants or imperfect focus
are all normal and do not make the photo unrelated.
Choose "unrelated" ONLY when there is no assessable pepper tissue at all:
a photo of bare ground, sky, a building, an animal, a screenshot, a flat
colour field, or a frame so blurred or dark that nothing can be judged.

STEP 2 — Which body part is being assessed?
- Broad glossy leaves with parallel veins dominate  -> LEAF domain.
- The thick stem base meeting the soil dominates    -> COLLAR domain.
- A whole branch or vine whose story is drooping or
  bare foliage                                      -> defoliation_wilt.

STEP 3 — Grade within that domain.

LEAF domain
  healthy_leaf     — the leaf is GREEN. Deep green, mid green, olive, or pale
                     green new growth all count. Dust, small spots, insect
                     holes, a torn edge, water droplets, shadow and warm or
                     dim light are all still healthy_leaf.
                     >> DEFAULT for any leaf that reads as predominantly
                     >> green. Never escalate on lighting or white balance.
  foliar_yellowing — the tissue has genuinely LOST green pigment: yellow or
                     bleached areas between veins or along margins, veins
                     staying greener. Must be a property of the leaf, not a
                     warm-toned photograph of a green leaf.
                     >> If torn between the two and the leaf still reads
                     >> green, answer healthy_leaf.

COLLAR domain
  healthy_collar   — stem base intact: even bark, no dark sunken patch, no
                     ooze, no girdling. Wet soil around it is fine.
  collar_lesion    — a dark brown or black, water-soaked or sunken lesion ON
                     the stem tissue, often spreading around it. Earliest
                     treatable sign of foot rot and the most important class
                     to get right.
                     >> The lesion must be on PLANT TISSUE. Dark wet soil,
                     >> mud splash, shadow at the base, or a dark support
                     >> post is NOT a lesion.

WHOLE BRANCH
  defoliation_wilt — limp, drooping or curled foliage, browning, leaves
                     already shed leaving bare nodes. A plant that is dying.
                     >> Requires visible loss of turgor or leaf loss. Green
                     >> foliage with normal turgor is NEVER this class,
                     >> however many leaves are in frame or however distant
                     >> the shot.

## Confidence
Your honest certainty. 0.85+ only when unmistakable; 0.5-0.7 when plausible;
below 0.4 when largely guessing. A low confidence is more useful to a farmer
than a confident wrong answer.

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
