"""Vector store interface and in-memory fallback implementation."""
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Protocol
import numpy as np


@dataclass
class VectorSearchResult:
    id: str
    score: float
    metadata: Dict[str, Any]


class VectorStore(Protocol):
    async def search(
        self,
        query_vector: List[float],
        top_k: int = 5,
        filter_metadata: Optional[Dict[str, Any]] = None,
    ) -> List[VectorSearchResult]:
        ...

    async def upsert(
        self,
        id: str,
        vector: List[float],
        metadata: Dict[str, Any],
    ) -> None:
        ...


class InMemoryVectorStore:
    """In-memory cosine similarity vector store for local testing."""

    def __init__(self):
        self._entries: List[Dict[str, Any]] = []

    async def upsert(self, id: str, vector: List[float], metadata: Dict[str, Any]) -> None:
        v = np.array(vector, dtype=np.float32)
        norm = np.linalg.norm(v)
        normalized_v = v / (norm + 1e-9)
        self._entries.append({
            "id": id,
            "vector": normalized_v,
            "metadata": metadata,
        })

    async def search(
        self,
        query_vector: List[float],
        top_k: int = 5,
        filter_metadata: Optional[Dict[str, Any]] = None,
    ) -> List[VectorSearchResult]:
        if not self._entries:
            return []

        qv = np.array(query_vector, dtype=np.float32)
        qv = qv / (np.linalg.norm(qv) + 1e-9)

        results = []
        for entry in self._entries:
            if filter_metadata:
                skip = False
                for k, v in filter_metadata.items():
                    if entry["metadata"].get(k) != v:
                        skip = True
                        break
                if skip:
                    continue

            score = float(np.dot(qv, entry["vector"]))
            results.append(VectorSearchResult(
                id=entry["id"],
                score=score,
                metadata=entry["metadata"],
            ))

        results.sort(key=lambda r: r.score, reverse=True)
        return results[:top_k]
