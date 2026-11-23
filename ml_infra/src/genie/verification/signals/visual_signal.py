"""Visual similarity and anomaly signal computation."""
from typing import Optional

from genie.verification.signals import SignalResult


class VisualSignalEvaluator:
    def evaluate(
        self,
        retrieval_cosine_sim: float,
        alignment_inlier_ratio: float,
        patch_anomaly_score: float,
    ) -> SignalResult:
        # Combined visual confidence
        visual_score = (
            0.4 * retrieval_cosine_sim
            + 0.3 * alignment_inlier_ratio
            + 0.3 * (1.0 - patch_anomaly_score)
        )
        visual_score = min(max(visual_score, 0.0), 1.0)

        reasons = []
        if patch_anomaly_score > 0.70:
            reasons.append(f"Significant visual packaging anomaly detected (anomaly score: {patch_anomaly_score:.2f}).")
        else:
            reasons.append(f"Visual packaging features align with reference packaging (score: {visual_score:.2f}).")

        return SignalResult(
            score=visual_score,
            confidence=0.85,
            reasons=reasons,
            evidence={
                "cosine_similarity": retrieval_cosine_sim,
                "inlier_ratio": alignment_inlier_ratio,
                "anomaly_score": patch_anomaly_score,
            },
        )
