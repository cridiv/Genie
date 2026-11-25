"""Dependency injection for FastAPI stateless ML endpoints (singleton instances for 2GB VM)."""
from genie.storage.vector_store import SQLiteVectorStore, VectorStore
from genie.verification.pipeline import VerificationPipeline
from genie.vision.reference_index import ReferencePackIndexer

# Persistent SQLite + NumPy cosine similarity vector store (no Qdrant required)
_vector_store_instance = SQLiteVectorStore("./data/vectors.db")
_pipeline_instance: VerificationPipeline | None = None
_indexer_instance: ReferencePackIndexer | None = None


def get_vector_store() -> VectorStore:
    return _vector_store_instance


def get_pipeline() -> VerificationPipeline:
    global _pipeline_instance
    if _pipeline_instance is None:
        _pipeline_instance = VerificationPipeline(vector_store=_vector_store_instance)
    return _pipeline_instance


def get_indexer() -> ReferencePackIndexer:
    global _indexer_instance
    if _indexer_instance is None:
        _indexer_instance = ReferencePackIndexer(vector_store=_vector_store_instance)
    return _indexer_instance
