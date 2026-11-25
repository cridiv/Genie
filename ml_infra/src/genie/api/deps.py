"""Dependency injection for FastAPI stateless ML endpoints."""
from genie.storage.vector_store import SQLiteVectorStore, VectorStore

# Persistent SQLite + NumPy cosine similarity vector store (no Qdrant required)
_vector_store_instance = SQLiteVectorStore("./data/vectors.db")


def get_vector_store() -> VectorStore:
    return _vector_store_instance
