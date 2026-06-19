import logging
import sys

from app.config import get_settings


def configure_logging() -> None:
    settings = get_settings()
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format=(
            "%(asctime)s level=%(levelname)s service=data-engineering "
            "logger=%(name)s message=%(message)s"
        ),
        stream=sys.stdout,
    )
