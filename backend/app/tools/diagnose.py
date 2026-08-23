"""`diagnose_leaf` — ONNX MobileNetV3-Small inference. docs/PROJECT_SPEC.md §3 L1.

Loads the pre-trained checkpoint from classifier/best-model/ (EXP-1: allowed
on-site, no live training needed). Classification only, six classes, no
bounding boxes. `confidence < 0.60` -> advise physical inspection, never
assert a diagnosis (huluhilir-rules skill §9).
"""
import time
from functools import lru_cache
from pathlib import Path

import numpy as np
import onnxruntime as ort
from PIL import Image

from app.config import settings
from app.schemas.diagnosis import DiagnoseLeafResult
from app.schemas.enums import CaptureTarget, DiseaseClass

LEAF_DOMAIN = {DiseaseClass.healthy_leaf.value, DiseaseClass.foliar_yellowing.value}
COLLAR_DOMAIN = {DiseaseClass.healthy_collar.value, DiseaseClass.collar_lesion.value}


@lru_cache(maxsize=1)
def _session() -> ort.InferenceSession:
    return ort.InferenceSession(settings.cnn_model_path, providers=["CPUExecutionProvider"])


@lru_cache(maxsize=1)
def _labels() -> list[str]:
    return Path(settings.cnn_labels_path).read_text(encoding="utf-8").split()


@lru_cache(maxsize=1)
def _preprocess_config() -> dict:
    import json
    return json.loads(Path(settings.cnn_preprocess_path).read_text(encoding="utf-8"))


def _preprocess(image_path: str) -> np.ndarray:
    cfg = _preprocess_config()
    size = tuple(cfg["input_size"])
    mean = np.array(cfg["mean"], dtype=np.float32).reshape(3, 1, 1)
    std = np.array(cfg["std"], dtype=np.float32).reshape(3, 1, 1)

    img = Image.open(image_path).convert("RGB").resize(size)
    arr = np.asarray(img, dtype=np.float32).transpose(2, 0, 1) / 255.0
    arr = (arr - mean) / std
    return arr[np.newaxis, ...]


def _softmax(logits: np.ndarray) -> np.ndarray:
    exp = np.exp(logits - logits.max())
    return exp / exp.sum()


def check_capture_mismatch(capture_target: CaptureTarget, predicted: str) -> str | None:
    """EXP-14: verifies the six-class split actually catches a wrongly-aimed
    photo, rather than silently recording it as a valid check."""
    if predicted == DiseaseClass.unrelated.value:
        return "RETAKE: not a plant subject"
    if capture_target == CaptureTarget.collar and predicted in LEAF_DOMAIN:
        return "RETAKE: looks like a leaf, aim at the stem base"
    if capture_target == CaptureTarget.leaf and predicted in COLLAR_DOMAIN:
        return "RETAKE: looks like a stem base, aim at a leaf"
    return None


def diagnose_leaf(observation_id: str, image_uri: str, capture_target: CaptureTarget) -> DiagnoseLeafResult:
    start = time.perf_counter()
    session = _session()
    labels = _labels()

    input_tensor = _preprocess(image_uri)
    input_name = session.get_inputs()[0].name
    logits = session.run(None, {input_name: input_tensor})[0][0]
    scores = _softmax(logits)

    ranked = sorted(zip(labels, scores.tolist()), key=lambda p: p[1], reverse=True)
    predicted_class, confidence = ranked[0]
    second_class = ranked[1][0] if len(ranked) > 1 else None
    inference_ms = int((time.perf_counter() - start) * 1000)

    return DiagnoseLeafResult(
        observation_id=observation_id,
        predicted_class=predicted_class,
        confidence=round(confidence, 4),
        all_scores={label: round(score, 4) for label, score in ranked},
        second_class=second_class,
        below_threshold=confidence < settings.confidence_threshold,
        model_version=settings.cnn_model_version,
        inference_ms=inference_ms,
        mismatch_flag=check_capture_mismatch(capture_target, predicted_class),
    )
