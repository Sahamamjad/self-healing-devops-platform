"""Incident remediation lifecycle transitions."""

from __future__ import annotations

from enum import StrEnum


class LifecycleStatus(StrEnum):
    DETECTED = "Detected"
    ANALYSED = "Analysed"
    PROPOSED = "Proposed"
    APPROVED = "Approved"
    EXECUTED = "Executed"
    VERIFIED = "Verified"
    REJECTED = "Rejected"
    FAILED = "Failed"
    NEEDS_INVESTIGATION = "Needs investigation"


ALLOWED_TRANSITIONS: dict[LifecycleStatus, frozenset[LifecycleStatus]] = {
    LifecycleStatus.DETECTED: frozenset(
        {
            LifecycleStatus.ANALYSED,
            LifecycleStatus.NEEDS_INVESTIGATION,
            LifecycleStatus.REJECTED,
        }
    ),
    LifecycleStatus.ANALYSED: frozenset(
        {
            LifecycleStatus.PROPOSED,
            LifecycleStatus.NEEDS_INVESTIGATION,
            LifecycleStatus.REJECTED,
        }
    ),
    LifecycleStatus.PROPOSED: frozenset(
        {
            LifecycleStatus.APPROVED,
            LifecycleStatus.REJECTED,
            LifecycleStatus.NEEDS_INVESTIGATION,
        }
    ),
    LifecycleStatus.APPROVED: frozenset(
        {
            LifecycleStatus.EXECUTED,
            LifecycleStatus.REJECTED,
            LifecycleStatus.FAILED,
        }
    ),
    LifecycleStatus.EXECUTED: frozenset(
        {
            LifecycleStatus.VERIFIED,
            LifecycleStatus.FAILED,
            LifecycleStatus.NEEDS_INVESTIGATION,
        }
    ),
    LifecycleStatus.VERIFIED: frozenset(),
    LifecycleStatus.REJECTED: frozenset(),
    LifecycleStatus.FAILED: frozenset({LifecycleStatus.NEEDS_INVESTIGATION}),
    LifecycleStatus.NEEDS_INVESTIGATION: frozenset(
        {LifecycleStatus.ANALYSED, LifecycleStatus.REJECTED}
    ),
}


class InvalidTransitionError(ValueError):
    pass


def can_transition(current: LifecycleStatus, target: LifecycleStatus) -> bool:
    return target in ALLOWED_TRANSITIONS[current]


def transition(current: LifecycleStatus, target: LifecycleStatus) -> LifecycleStatus:
    if not can_transition(current, target):
        raise InvalidTransitionError(f"Cannot transition from {current.value} to {target.value}")
    return target
