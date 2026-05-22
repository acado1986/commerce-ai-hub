"""Compatibility entrypoint for the delivery hub CLI."""

from __future__ import annotations

import asyncio

from agent.cli_agent.service import run_cli


def main_sync() -> None:
    """Run the interactive delivery hub CLI."""
    asyncio.run(run_cli())


if __name__ == "__main__":
    main_sync()
