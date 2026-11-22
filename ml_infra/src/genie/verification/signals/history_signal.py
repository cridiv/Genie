"""Historical packaging version match signal."""
from typing import Optional

from genie.verification.signals import SignalResult


class HistorySignalEvaluator:
    def evaluate(
        self,
        is_legacy_match: bool,
        version_label: Optional[str],
        transition_active: bool = True,
    ) -> SignalResult:
        if not is_legacy_match:
            return SignalResult(
                score=1.0,
                confidence=0.9,
                reasons=["Matches current active packaging design."],
            )

        if transition_active:
            return SignalResult(
                score=0.95,
                confidence=0.9,
                reasons=[f"Consistent with legitimate legacy packaging design: {version_label} (within transition window)."],
                evidence={"legacy_version": version_label, "transition_valid": True},
            )

        return SignalResult(
            score=0.40,
            confidence=0.75,
            reasons=[f"Matches superseded packaging ({version_label}) beyond permitted shelf-life transition window."],
        )
