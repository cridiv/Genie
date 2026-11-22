"""Unit tests for Calibrated Signal Fusion."""
from genie.schemas.verdict import VerdictState
from genie.verification.fusion import CalibratedFusionEngine
from genie.verification.signals import SignalResult


def test_fusion_hard_rule_rejection():
    engine = CalibratedFusionEngine()
    signals = {
        "barcode": SignalResult(
            score=0.0,
            confidence=1.0,
            hard_invalidation=True,
            invalidation_reason="Invalid GTIN check digit",
        ),
        "visual": SignalResult(score=0.95, confidence=0.9),
    }

    verdict, conf, breakdown, reasons = engine.fuse(signals)
    assert verdict == VerdictState.SUSPICIOUS
    assert "Invalid GTIN check digit" in reasons[0]


def test_fusion_genuine_verdict():
    engine = CalibratedFusionEngine(genuine_threshold=0.85)
    signals = {
        "barcode": SignalResult(score=0.95, confidence=0.9),
        "nafdac": SignalResult(score=0.95, confidence=0.95),
        "batch": SignalResult(score=0.90, confidence=0.85),
        "visual": SignalResult(score=0.92, confidence=0.85),
    }

    verdict, conf, breakdown, reasons = engine.fuse(signals)
    assert verdict == VerdictState.CONSISTENT_WITH_GENUINE
    assert conf >= 0.85


def test_fusion_insufficient_signals():
    engine = CalibratedFusionEngine()
    # Missing all major signals, very low total confidence
    signals = {
        "barcode": SignalResult(score=0.5, confidence=0.1),
    }

    verdict, conf, breakdown, reasons = engine.fuse(signals)
    assert verdict == VerdictState.CANNOT_VERIFY
