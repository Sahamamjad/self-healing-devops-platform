"""python -m self_healing_platform"""

from __future__ import annotations

import uvicorn

from self_healing_platform.config import get_settings


def run() -> None:
    settings = get_settings()
    uvicorn.run(
        "self_healing_platform.main:app",
        host=settings.host,
        port=settings.port,
        factory=False,
    )


if __name__ == "__main__":
    run()
