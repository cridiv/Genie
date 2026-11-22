"""Explainability engine compiling structured audit reasons into consumer feedback."""
from typing import List

from genie.schemas.verdict import VerdictState


class ExplainabilityEngine:
    """Compiles verified evidence into clear, legally compliant consumer explanations."""

    @classmethod
    def assemble_explanation(
        cls,
        verdict: VerdictState,
        product_name: str | None,
        version_label: str | None,
        is_legacy: bool,
        reasons: List[str],
    ) -> str:
        prod_title = product_name or "scanned product"

        if verdict == VerdictState.CONSISTENT_WITH_GENUINE:
            if is_legacy:
                return (
                    f"Consistent with legitimate genuine packaging for {prod_title} "
                    f"({version_label}). This is a previous genuine packaging design that remains valid "
                    f"within the permitted transition window. Evidence: {'; '.join(reasons[:2])}."
                )
            return (
                f"Consistent with genuine {prod_title}. Packaging, regulatory credentials, "
                f"and barcode specifications match official verified references. Evidence: {'; '.join(reasons[:2])}."
            )

        if verdict == VerdictState.SUSPICIOUS:
            primary_reason = reasons[0] if reasons else "Multiple structural packaging discrepancies detected"
            return (
                f"Suspicious product detected for {prod_title}. We recommend not consuming this item. "
                f"Reason: {primary_reason}. Please report this scan to NAFDAC enforcement."
            )

        # Cannot verify
        guidance = reasons[0] if reasons else "Insufficient image clarity or unindexed packaging"
        return (
            f"Cannot verify {prod_title} at this time. {guidance}. "
            f"Please ensure packaging is well-lit, glare-free, and re-scan the primary face."
        )
