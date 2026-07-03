"""Outlook Mail MCP server entry point."""

from __future__ import annotations

import asyncio
import logging

from app.config import get_settings
from app.server import run_stdio_server


def configure_logging() -> None:
    settings = get_settings()
    logging.basicConfig(
        level=getattr(logging, settings.outlook_mcp_log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )


def main() -> None:
    configure_logging()
    asyncio.run(run_stdio_server())


if __name__ == "__main__":
    main()
