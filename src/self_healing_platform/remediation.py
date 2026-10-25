"""Policy-controlled remediation. Simulated by default. Never runs shell commands."""

from __future__ import annotations

from typing import Any

from self_healing_platform.demo import DemoFailureController
from self_healing_platform.lifecycle import (
    InvalidTransitionError,
    LifecycleStatus,
    transition,
)

ALLOWLISTED_ACTIONS = frozenset(
    {
        "simulate_clear_demo_failure",
        "simulate_restart_application",
        "none",
    }
)

UNSAFE_ACTIONS = frozenset(
    {
        "delete_namespace",
        "delete_cluster",
        "kubectl",
        "shell",
        "exec",
        "rm",
        "scale_production",
    }
)


class RemediationRejectedError(ValueError):
    def __init__(self, message: str, code: str = "remediation_rejected") -> None:
        super().__init__(message)
        self.code = code


def validate_action(action: str) -> str:
    normalized = action.strip()
    lowered = normalized.lower()
    if lowered in UNSAFE_ACTIONS or any(part in lowered for part in ("/", ";", "|", "`", "$(")):
        raise RemediationRejectedError("Unsafe or non-allowlisted remediation action rejected")
    if normalized not in ALLOWLISTED_ACTIONS:
        raise RemediationRejectedError(f"Action '{normalized}' is not on the allowlist")
    if normalized == "none":
        raise RemediationRejectedError("Action 'none' cannot be executed")
    return normalized


def prepare_lifecycle(current: str, approved: bool) -> str:
    status = LifecycleStatus(current)
    if status == LifecycleStatus.PROPOSED and approved:
        status = transition(status, LifecycleStatus.APPROVED)
    return status.value


def execute_simulated(
    action: str,
    *,
    dry_run: bool,
    dry_run_only: bool,
    remediation_enabled: bool,
    kubernetes_remediation_enabled: bool,
    demo: DemoFailureController,
) -> dict[str, Any]:
    if kubernetes_remediation_enabled:
        raise RemediationRejectedError(
            "Kubernetes remediation adapter is compiled out of the default demo. "
            "Cluster mutations are not performed."
        )
    if not remediation_enabled and not dry_run:
        raise RemediationRejectedError(
            "Live remediation is disabled. Re-run with dry_run=true or enable REMEDIATION_ENABLED."
        )
    if dry_run_only:
        dry_run = True

    detail: dict[str, Any] = {
        "simulated": True,
        "modifies_infrastructure": False,
        "kubernetes_adapter": "disabled",
        "action": action,
        "dry_run": dry_run,
        "note": (
            "This demonstration records an audit event only. It does not restart pods, "
            "edit Kubernetes objects, or run shell commands. Kubernetes restarting a "
            "crashed container and Argo CD reconciling Git state are separate mechanisms."
        ),
    }

    if dry_run:
        detail["result_meaning"] = "dry-run: no process state changed"
        return detail

    if action == "simulate_clear_demo_failure":
        demo.deactivate()
        detail["demo_failure_cleared"] = True
    elif action == "simulate_restart_application":
        detail["restart"] = "recorded_only"
    return detail


def next_status_after_execution(current: str, *, dry_run: bool, success: bool) -> str:
    status = LifecycleStatus(current)
    if dry_run:
        return status.value
    if status != LifecycleStatus.APPROVED:
        raise InvalidTransitionError(
            f"Execution requires Approved status, current is {status.value}"
        )
    executed = transition(status, LifecycleStatus.EXECUTED)
    if success:
        return transition(executed, LifecycleStatus.VERIFIED).value
    return transition(executed, LifecycleStatus.FAILED).value
