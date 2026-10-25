"""ASGI entrypoint."""

from __future__ import annotations

from self_healing_platform.app import create_app
from self_healing_platform.config import get_settings
from self_healing_platform.logging import configure_logging

settings = get_settings()
configure_logging(settings.log_level)
app = create_app(settings)
