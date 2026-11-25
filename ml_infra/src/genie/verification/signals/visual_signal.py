"""Visual similarity and anomaly signal computation."""
from typing import List, Optional

from genie.verification.signals import SignalResult


class VisualSignalEvaluator:
    def evaluate(
        self,
        retrieval_cosine_sim: float,
        alignment_inlier_ratio: float,
        patch_anomaly_score: float,
        color_score: Optional[float] = None,
        layout_score: Optional[float] = None,
        inconsistencies: Optional[List[str]] = None,
        reference_available: bool = True,
        texture_score: Optional[float] = None,
        texture_mismatch: bool = False,
    ) -> SignalResult:
        if not reference_available:
            reasons = (
                list(inconsistencies)
                if inconsistencies
                else ["No canonical reference pack image available in database for visual comparison."]
            )
            return SignalResult(
                score=0.50,
                confidence=0.10,
                reasons=reasons,
                evidence={
                    "cosine_similarity": retrieval_cosine_sim,
                    "reference_available": False,
                },
            )

        if texture_mismatch:
            t_val = texture_score if texture_score is not None else 0.0
            inv_msg = f"Package surface texture differs from canonical reference packaging (texture score: {t_val:.2f})."
            reasons = list(inconsistencies) if inconsistencies else [inv_msg]
            if inv_msg not in reasons:
                reasons.insert(0, inv_msg)
            return SignalResult(
                score=min(t_val, 0.20),
                confidence=0.95,
                hard_invalidation=True,
                invalidation_reason=inv_msg,
                reasons=reasons,
                evidence={
                    "cosine_similarity": retrieval_cosine_sim,
                    "inlier_ratio": alignment_inlier_ratio,
                    "anomaly_score": patch_anomaly_score,
                    "color_score": color_score,
                    "layout_score": layout_score,
                    "texture_score": texture_score,
                    "texture_mismatch": True,
                },
            )

        if color_score is not None and layout_score is not None:
            t_component = texture_score if texture_score is not None else 0.85
            visual_score = (
                0.15 * retrieval_cosine_sim
                + 0.15 * alignment_inlier_ratio
                + 0.25 * color_score
                + 0.20 * layout_score
                + 0.15 * t_component
                + 0.10 * (1.0 - patch_anomaly_score)
            )
            confidence = 0.92
        else:
            visual_score = (
                0.4 * retrieval_cosine_sim
                + 0.3 * alignment_inlier_ratio
                + 0.3 * (1.0 - patch_anomaly_score)
            )
            confidence = 0.85

        visual_score = min(max(visual_score, 0.0), 1.0)

        reasons = list(inconsistencies) if inconsistencies else []
        if patch_anomaly_score > 0.70:
            reasons.append(f"Significant visual packaging anomaly detected (anomaly score: {patch_anomaly_score:.2f}).")
        elif not reasons:
            reasons.append(f"Visual packaging features align with reference packaging (score: {visual_score:.2f}).")

        evidence = {
            "cosine_similarity": retrieval_cosine_sim,
            "inlier_ratio": alignment_inlier_ratio,
            "anomaly_score": patch_anomaly_score,
        }
        if color_score is not None:
            evidence["color_score"] = color_score
        if layout_score is not None:
            evidence["layout_score"] = layout_score
        if texture_score is not None:
            evidence["texture_score"] = texture_score

        return SignalResult(
            score=visual_score,
            confidence=confidence,
            reasons=reasons,
            evidence=evidence,
        )
