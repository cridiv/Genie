"""Calibrated multi-signal fusion combining hard invalidation rules and Platt-scaled weights."""
import math
from typing import Dict, List, Tuple

from genie.schemas.verdict import SignalBreakdown, VerdictState
from genie.verification.signals import SignalResult


class CalibratedFusionEngine:
    """Combines modular signals into a calibrated 3-state verdict."""

    def __init__(
        self,
        genuine_threshold: float = 0.88,
        suspicious_threshold: float = 0.38,
    ):
        self.genuine_threshold = genuine_threshold
        self.suspicious_threshold = suspicious_threshold

        # Default weights
        self.weights = {
            "barcode": 0.20,
            "nafdac": 0.30,
            "batch": 0.20,
            "visual": 0.20,
            "history": 0.10,
        }

    def fuse(
        self,
        signals: Dict[str, SignalResult],
        category: str = "pharmaceuticals_antimalarials",
    ) -> Tuple[VerdictState, float, SignalBreakdown, List[str]]:
        reasons: List[str] = []
        breakdown = SignalBreakdown()

        # Step 1: Check Hard Invalidation Rules
        for name, sig in signals.items():
            if sig.hard_invalidation:
                inv_msg = sig.invalidation_reason or f"Hard invalidation triggered by {name} signal."
                reasons.append(inv_msg)
                return (
                    VerdictState.SUSPICIOUS,
                    0.99,
                    breakdown,
                    reasons,
                )

        # Step 2: Weighted Calibrated Combination
        total_weight = 0.0
        weighted_score = 0.0

        for name, sig in signals.items():
            w = self.weights.get(name, 0.1)
            # Re-scale weight by signal confidence
            effective_w = w * sig.confidence
            weighted_score += sig.score * effective_w
            total_weight += effective_w
            reasons.extend(sig.reasons)

            # Populate breakdown
            if name == "barcode":
                breakdown.barcode_score = sig.score
            elif name == "nafdac":
                breakdown.nafdac_score = sig.score
            elif name == "batch":
                breakdown.batch_consistency_score = sig.score
            elif name == "visual":
                breakdown.visual_similarity_score = sig.score
            elif name == "history":
                breakdown.history_match_score = sig.score

        breakdown.reasons = reasons

        if total_weight < 0.25:
            # Insufficient signal data
            return (
                VerdictState.CANNOT_VERIFY,
                0.30,
                breakdown,
                ["Insufficient verifiable signals detected from uploaded scan."],
            )

        calibrated_score = weighted_score / total_weight

        # Step 3: Verdict Determination
        if calibrated_score >= self.genuine_threshold:
            verdict = VerdictState.CONSISTENT_WITH_GENUINE
            confidence = calibrated_score
        elif calibrated_score <= self.suspicious_threshold:
            verdict = VerdictState.SUSPICIOUS
            confidence = 1.0 - calibrated_score
        else:
            verdict = VerdictState.CANNOT_VERIFY
            confidence = calibrated_score

        return verdict, confidence, breakdown, reasons
