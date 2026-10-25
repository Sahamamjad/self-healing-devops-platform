"""Secret redaction and untrusted-input handling."""

from __future__ import annotations

import re
from typing import Any

_SECRET_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"(?i)authorization\s*[:=]\s*bearer\s+\S+"),
    re.compile(r"(?i)\bbearer\s+\S+"),
    re.compile(r"(?i)\b(api[_-]?key|token|secret|password|passwd)\s*[:=]\s*\S+"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"(?i)-----BEGIN [A-Z ]*PRIVATE KEY-----"),
)

_INSTRUCTION_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"(?i)ignore (all )?(previous|prior) instructions"),
    re.compile(r"(?i)you are now"),
    re.compile(r"(?i)system prompt"),
)


def redact_text(value: str) -> str:
    redacted = value
    for pattern in _SECRET_PATTERNS:
        redacted = pattern.sub("[REDACTED]", redacted)
    return redacted


def strip_embedded_instructions(value: str) -> str:
    cleaned = value
    for pattern in _INSTRUCTION_PATTERNS:
        cleaned = pattern.sub("[UNTRUSTED_INSTRUCTION_REMOVED]", cleaned)
    return cleaned


def sanitize_untrusted_text(value: str | None) -> str | None:
    if value is None:
        return None
    return redact_text(strip_embedded_instructions(value))


def redact_mapping(data: Any) -> Any:
    if isinstance(data, str):
        return sanitize_untrusted_text(data)
    if isinstance(data, list):
        return [redact_mapping(item) for item in data]
    if isinstance(data, dict):
        return {str(key): redact_mapping(value) for key, value in data.items()}
    return data
