"""Checkpoint configuration."""

from langgraph.checkpoint.memory import MemorySaver


def get_checkpointer() -> MemorySaver:
    return MemorySaver()
