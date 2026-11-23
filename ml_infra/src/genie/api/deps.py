"""Dependency injection for FastAPI endpoints."""
from typing import AsyncGenerator
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from genie.db.session import async_session_factory
from genie.storage.vector_store import InMemoryVectorStore, VectorStore

# In-memory vector store singleton for local runtime
_vector_store_instance = InMemoryVectorStore()


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with async_session_factory() as session:
        yield session


def get_vector_store() -> VectorStore:
    return _vector_store_instance
