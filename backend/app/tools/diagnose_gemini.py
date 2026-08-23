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

_PROMPT = """You grade ONE photograph from a Sarawak black pepper (Piper nigrum) farm
for Phytophthora foot rot screening.

Return ONLY this JSON object. No prose, no markdown fence:
{"class": "<exact label>", "confidence": <0.0-1.0>, "reason": "<max 12 words>"}

Field photos are messy. Background soil, a hand steadying the stem, a support
post, mud splash, other plants and imperfect focus are NORMAL and do not by
themselves make a photo ungradeable.

================================================================
0 · healthy_leaf   (SIHAT (DAUN))
----------------------------------------------------------------
Colour   uniform mid-to-dark green, hue ~70-150 deg, saturation >35%,
         value >30%; no patch deviating more than ~15% in hue from the
         leaf mean.
Texture  smooth continuous lamina, visible parallel/reticulate venation,
         no necrotic speckling above ~2 mm.
Boundary margin intact: no tearing, curling or crisping.
Scale    whole leaf visible, occupying more than ~40% of the frame.
Discriminate  vs foliar_yellowing -- NO chlorotic (pale/yellow) region
         reaching 10% of leaf area.

================================================================
1 · healthy_collar   (SIHAT (PANGKAL))
----------------------------------------------------------------
Colour   bark/stem tone consistent top-to-bottom (natural brown or grey,
         value 20-50%); no localised dark patch larger than ~1 cm.
Texture  dry, uniform bark; no gumming, cracking or glossy sheen.
Boundary no lesion edge and no discoloration halo at the soil line.
Location base of stem within ~15 cm of soil, symmetric around the
         circumference.
Discriminate  vs collar_lesion -- ABSENCE of any localised water-soaked or
         blackened patch in the collar zone.

================================================================
2 · foliar_yellowing   (DAUN MENGUNING)
----------------------------------------------------------------
Colour   chlorotic patches, hue shifted toward yellow (~40-65 deg),
         saturation often reduced against the healthy baseline. Either
         interveinal (yellow between green veins) or marginal (a yellow
         band running inward from the leaf edge).
Texture  lamina otherwise intact -- no lesion, no wilting droop.
Boundary diffuse, a gradient between chlorotic and green tissue, NOT a
         sharp necrotic edge.
Scale    at least ~10% of leaf area affected to trigger this class.
Discriminate  vs healthy_leaf -- chlorotic area reaches 10%.
              vs defoliation_wilt -- the leaf is flat and turgid, not
              drooping or detaching.

================================================================
3 · collar_lesion   (LESI PANGKAL)   ** HIGHEST PRIORITY **
----------------------------------------------------------------
Colour   dark brown-to-black patch, value <25%, low saturation, often a
         wet or glossy sheen (water-soaked); may show a reddish-brown halo
         at the advancing margin.
Texture  irregular surface -- cracking, gumming/exudate, or tissue sunken
         relative to the surrounding bark.
Boundary sharp, irregular blob shape. NOT a uniform colour band, which
         would be ordinary bark shading.
Location localised at the stem base, within ~15 cm of the soil line. This
         location constraint is itself diagnostic.
Scale    any qualifying patch of ~1 cm or more in the collar zone.
Discriminate  vs healthy_collar -- presence of a dark/wet patch at the base.
              vs foliar_yellowing -- the location is stem base, not lamina.
ESCALATE on any positive signal, even at low confidence. Report the low
confidence honestly rather than downgrading the class: a missed collar
lesion is the most costly error this classifier can make.
BUT the patch must be on PLANT TISSUE. Dark wet soil, mud splash, shadow
at the stem base, or a dark support post is NOT a lesion.

================================================================
4 · defoliation_wilt   (GUGUR DAUN / LAYU)
----------------------------------------------------------------
Colour   desiccated or browning foliage (value and saturation both drop --
         a "dead" tone), or bare nodes showing woody stem with no leaf
         attached.
Texture  drooping/sagging posture, loss of turgor; petiole angle sags
         below horizontal.
Boundary a whole-leaf or whole-branch effect, not a localised patch.
Scale    multiple leaves or nodes on a branch affected at once, not a
         single leaf.
Discriminate  vs foliar_yellowing -- posture is drooping/detaching, not
              flat-and-discoloured.
              vs collar_lesion -- the effect is canopy-wide, not confined
              to the stem base.
Green foliage with normal turgor is NEVER this class, however many leaves
are in frame and however distant the shot.

================================================================
5 · unrelated   (TIADA KAITAN)   -- the reject / abstain class
----------------------------------------------------------------
Content  no plant tissue dominant in frame: soil, human hand or skin tone,
         sky, ground clutter, motion blur, or an extreme close-up with no
         identifiable leaf or stem structure.
Trigger  if identifiable leaf or stem structure occupies less than ~30% of
         the frame, answer here rather than forcing a disease label.
This routes to a retake prompt instead of a diagnosis. Choosing it when
warranted is CORRECT -- but do not reach for it when gradeable pepper
tissue is present just because the photo is imperfect.

================================================================
DECIDE IN THIS ORDER
1. Is identifiable pepper leaf or stem tissue at least ~30% of the frame?
   No -> unrelated. Stop.
2. Is there a dark, water-soaked, localised patch within ~15 cm of the
   soil line, on plant tissue? Yes -> collar_lesion. Stop.
3. Which body part dominates the frame?
   Leaves        -> healthy_leaf or foliar_yellowing (by the 10% rule).
   Stem base     -> healthy_collar.
   Whole branch, drooping or shedding -> defoliation_wilt.

CONFIDENCE
Honest certainty. 0.85+ only when unmistakable, 0.5-0.7 when plausible,
below 0.4 when largely guessing. A low confidence is more useful to a
farmer than a confident wrong answer.

NEVER name a treatment, chemical, dose, or timing. You classify only."""


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
