"""EXP-14: verify the six-class split's capture_target cross-check actually
fires, plus a smoke test that the real ONNX checkpoint loads and runs.
"""
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from app.config import settings
from app.schemas.enums import CaptureTarget, DiseaseClass
from app.tools.diagnose import check_capture_mismatch, diagnose_leaf


def test_collar_target_with_leaf_prediction_flags_retake():
    assert check_capture_mismatch(CaptureTarget.collar, DiseaseClass.foliar_yellowing.value) is not None


def test_leaf_target_with_collar_prediction_flags_retake():
    assert check_capture_mismatch(CaptureTarget.leaf, DiseaseClass.collar_lesion.value) is not None


def test_unrelated_always_flags_retake_regardless_of_target():
    assert check_capture_mismatch(CaptureTarget.collar, DiseaseClass.unrelated.value) is not None
    assert check_capture_mismatch(CaptureTarget.leaf, DiseaseClass.unrelated.value) is not None


def test_matching_target_and_class_passes():
    assert check_capture_mismatch(CaptureTarget.collar, DiseaseClass.healthy_collar.value) is None
    assert check_capture_mismatch(CaptureTarget.leaf, DiseaseClass.healthy_leaf.value) is None


@pytest.mark.skipif(
    not Path(settings.cnn_model_path).exists(),
    reason="ONNX checkpoint not present at settings.cnn_model_path",
)
def test_onnx_model_runs_on_a_synthetic_image(tmp_path):
    """Not an accuracy test -- confirms the exported checkpoint loads and
    produces a valid six-class softmax on a real inference pass."""
    img_path = tmp_path / "synthetic.jpg"
    Image.fromarray((np.random.rand(224, 224, 3) * 255).astype("uint8")).save(img_path)

    result = diagnose_leaf("obs_test", str(img_path), CaptureTarget.leaf)

    assert result.predicted_class in [c.value for c in DiseaseClass]
    assert 0.0 <= result.confidence <= 1.0
    assert len(result.all_scores) == 6
    assert abs(sum(result.all_scores.values()) - 1.0) < 0.01
    assert result.below_threshold == (result.confidence < settings.confidence_threshold)
