"""Unit tests for Image Quality Gating."""
import numpy as np
from genie.vision.quality import ImageQualityGate


def test_quality_gate_passes_clean_image(clean_synthetic_pack_image):
    gate = ImageQualityGate()
    result = gate.evaluate(clean_synthetic_pack_image)
    assert result.passed is True
    assert result.blur_score > gate.min_blur_score
    assert len(result.guidance_codes) == 0


def test_quality_gate_rejects_blurry_image(blurry_pack_image):
    gate = ImageQualityGate()
    result = gate.evaluate(blurry_pack_image)
    assert result.passed is False
    assert "HOLD_STEADY_BLURRY" in result.guidance_codes
