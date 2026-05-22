"""Checkpoint configuration."""

from __future__ import annotations

import atexit
import asyncio
import logging
import os
from typing import Any

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import MemorySaver

LOGGER = logging.getLogger(__name__)

_CHECKPOINTER: Any | None = None
_CHECKPOINTER_CTX: Any | None = None


class AsyncCheckpointerAdapter(BaseCheckpointSaver):
    """Expose async checkpoint APIs by delegating to a sync saver in a thread."""

    def __init__(self, saver: Any) -> None:
        super().__init__(serde=getattr(saver, "serde", None))
        self._saver = saver

    def __getattr__(self, name: str) -> Any:
        return getattr(self._saver, name)

    def get_tuple(self, config: Any) -> Any:
        return self._saver.get_tuple(config)

    def put(self, config: Any, checkpoint: Any, metadata: Any, new_versions: Any) -> Any:
        return self._saver.put(config, checkpoint, metadata, new_versions)

    def put_writes(self, config: Any, writes: Any, task_id: str, task_path: str = "") -> Any:
        return self._saver.put_writes(config, writes, task_id, task_path)

    async def aget_tuple(self, config: Any) -> Any:
        return await asyncio.to_thread(self._saver.get_tuple, config)

    async def aput(self, config: Any, checkpoint: Any, metadata: Any, new_versions: Any) -> Any:
        return await asyncio.to_thread(
            self._saver.put, config, checkpoint, metadata, new_versions
        )

    async def aput_writes(
        self,
        config: Any,
        writes: Any,
        task_id: str,
        task_path: str = "",
    ) -> Any:
        return await asyncio.to_thread(
            self._saver.put_writes, config, writes, task_id, task_path
        )

    async def adelete_thread(self, thread_id: str) -> None:
        await asyncio.to_thread(self._saver.delete_thread, thread_id)

    async def adelete_for_runs(self, thread_id: str, run_ids: Any) -> None:
        await asyncio.to_thread(self._saver.delete_for_runs, thread_id, run_ids)

    async def acopy_thread(self, thread_id: str) -> str:
        return await asyncio.to_thread(self._saver.copy_thread, thread_id)

    async def aprune(self, config: Any) -> None:
        await asyncio.to_thread(self._saver.prune, config)


def _postgres_uri() -> str:
    return (
        os.getenv("LANGGRAPH_CHECKPOINTER_POSTGRES_URI")
        or os.getenv("POSTGRES_URI")
        or os.getenv("DATABASE_URL")
        or ""
    ).strip()


def _teardown_checkpointer() -> None:
    global _CHECKPOINTER_CTX
    if _CHECKPOINTER_CTX is None:
        return
    try:
        _CHECKPOINTER_CTX.__exit__(None, None, None)
    except Exception:  # noqa: BLE001
        LOGGER.exception("Failed to close Postgres checkpointer context.")
    finally:
        _CHECKPOINTER_CTX = None


def _postgres_checkpointer() -> Any:
    global _CHECKPOINTER_CTX
    from langgraph.checkpoint.postgres import PostgresSaver

    uri = _postgres_uri()
    if not uri:
        raise RuntimeError("Postgres URI is not configured.")
    context = PostgresSaver.from_conn_string(uri)
    saver = context.__enter__()
    # Creates required tables on first run; safe to call repeatedly.
    saver.setup()
    _CHECKPOINTER_CTX = context
    return AsyncCheckpointerAdapter(saver)


def get_checkpointer() -> Any:
    """Return a singleton checkpointer.

    Prefers Postgres for durable, multi-process checkpointing when configured.
    Falls back to in-memory saver for local/dev usage without a database.
    """
    global _CHECKPOINTER
    if _CHECKPOINTER is not None:
        return _CHECKPOINTER
    try:
        _CHECKPOINTER = _postgres_checkpointer()
        atexit.register(_teardown_checkpointer)
        LOGGER.info("Using Postgres checkpointer backend.")
    except Exception as exc:  # noqa: BLE001
        _CHECKPOINTER = MemorySaver()
        LOGGER.warning(
            "Falling back to in-memory checkpointer: %s. "
            "Set LANGGRAPH_CHECKPOINTER_POSTGRES_URI or DATABASE_URL to enable durable checkpoints.",
            exc,
        )
    return _CHECKPOINTER
