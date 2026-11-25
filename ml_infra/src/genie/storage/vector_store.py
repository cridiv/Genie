"""Vector store interface, in-memory implementation, and SQLite + NumPy cosine similarity store."""
from dataclasses import dataclass
import json
from pathlib import Path
import sqlite3
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

    async def count(self) -> int:
        ...


class InMemoryVectorStore:
    """In-memory cosine similarity vector store supporting metadata list and exact filtering."""

    def __init__(self):
        self._entries: List[Dict[str, Any]] = []

    async def upsert(self, id: str, vector: List[float], metadata: Dict[str, Any]) -> None:
        v = np.array(vector, dtype=np.float32)
        norm = np.linalg.norm(v)
        normalized_v = v / (norm + 1e-9)

        # Update if exists
        for entry in self._entries:
            if entry["id"] == id:
                entry["vector"] = normalized_v
                entry["metadata"] = metadata
                return

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
                match = True
                for k, v in filter_metadata.items():
                    entry_val = entry["metadata"].get(k)
                    if isinstance(entry_val, list):
                        if v not in entry_val:
                            match = False
                            break
                    else:
                        if entry_val != v:
                            match = False
                            break
                if not match:
                    continue

            score = float(np.dot(qv, entry["vector"]))
            results.append(
                VectorSearchResult(
                    id=entry["id"],
                    score=score,
                    metadata=entry["metadata"],
                )
            )

        results.sort(key=lambda r: r.score, reverse=True)
        return results[:top_k]

    async def count(self) -> int:
        return len(self._entries)


class SQLiteVectorStore:
    """Lightweight persistent vector store backed by SQLite + NumPy cosine similarity (no Qdrant required)."""

    def __init__(self, db_path: str | Path = "./data/vectors.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(str(self.db_path))

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute("PRAGMA synchronous=NORMAL;")
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS reference_vectors (
                    id TEXT PRIMARY KEY,
                    vector BLOB NOT NULL,
                    metadata TEXT NOT NULL
                )
                """
            )

    @staticmethod
    def _matches_filter(metadata: Dict[str, Any], filter_metadata: Optional[Dict[str, Any]]) -> bool:
        if not filter_metadata:
            return True
        for k, v in filter_metadata.items():
            entry_val = metadata.get(k)
            if isinstance(entry_val, list):
                if v not in entry_val:
                    return False
            elif entry_val != v:
                return False
        return True

    async def upsert(self, id: str, vector: List[float], metadata: Dict[str, Any]) -> None:
        v = np.array(vector, dtype=np.float32)
        norm = np.linalg.norm(v)
        normalized_v = (v / (norm + 1e-9)).astype(np.float32)
        meta_json = json.dumps(metadata)

        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO reference_vectors (id, vector, metadata)
                VALUES (?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    vector = excluded.vector,
                    metadata = excluded.metadata
                """,
                (id, normalized_v.tobytes(), meta_json),
            )

    async def search(
        self,
        query_vector: List[float],
        top_k: int = 5,
        filter_metadata: Optional[Dict[str, Any]] = None,
    ) -> List[VectorSearchResult]:
        with self._connect() as conn:
            rows = conn.execute("SELECT id, vector, metadata FROM reference_vectors").fetchall()

        if not rows:
            return []

        qv = np.array(query_vector, dtype=np.float32)
        qv = qv / (np.linalg.norm(qv) + 1e-9)

        results: List[VectorSearchResult] = []
        for row_id, vec_blob, meta_json in rows:
            meta = json.loads(meta_json)
            if not self._matches_filter(meta, filter_metadata):
                continue
            vec = np.frombuffer(vec_blob, dtype=np.float32)
            score = float(np.dot(qv, vec))
            results.append(VectorSearchResult(id=row_id, score=score, metadata=meta))

        results.sort(key=lambda r: r.score, reverse=True)
        return results[:top_k]

    async def count(self) -> int:
        with self._connect() as conn:
            row = conn.execute("SELECT COUNT(*) FROM reference_vectors").fetchone()
            return int(row[0]) if row else 0
