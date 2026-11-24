"""Integrations with external GENIE services (including GENIE AI Product Intelligence)."""
from .genie_ai_client import GenieAIClient, sync_genie_ai_dossiers_to_index

__all__ = ["GenieAIClient", "sync_genie_ai_dossiers_to_index"]
