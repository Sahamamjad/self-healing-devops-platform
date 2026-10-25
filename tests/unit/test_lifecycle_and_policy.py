import pytest

from self_healing_platform.demo import DemoFailureController
from self_healing_platform.lifecycle import InvalidTransitionError, LifecycleStatus, transition
from self_healing_platform.remediation import (
    RemediationRejectedError,
    execute_simulated,
    validate_action,
)


def test_valid_and_invalid_transitions() -> None:
    assert (
        transition(LifecycleStatus.DETECTED, LifecycleStatus.ANALYSED) == LifecycleStatus.ANALYSED
    )
    assert (
        transition(LifecycleStatus.PROPOSED, LifecycleStatus.APPROVED) == LifecycleStatus.APPROVED
    )
    with pytest.raises(InvalidTransitionError):
        transition(LifecycleStatus.DETECTED, LifecycleStatus.EXECUTED)
    with pytest.raises(InvalidTransitionError):
        transition(LifecycleStatus.VERIFIED, LifecycleStatus.APPROVED)


def test_allowlist_and_unsafe_actions() -> None:
    assert validate_action("simulate_clear_demo_failure") == "simulate_clear_demo_failure"
    with pytest.raises(RemediationRejectedError):
        validate_action("delete_namespace")
    with pytest.raises(RemediationRejectedError):
        validate_action("kubectl get pods; rm -rf /")
    with pytest.raises(RemediationRejectedError):
        validate_action("not_a_real_action")
    with pytest.raises(RemediationRejectedError):
        validate_action("none")


def test_simulated_execution_does_not_claim_cluster_change() -> None:
    demo = DemoFailureController()
    demo.activate("http_500", 10, 5, "inc-1")
    detail = execute_simulated(
        "simulate_clear_demo_failure",
        dry_run=True,
        dry_run_only=True,
        remediation_enabled=False,
        kubernetes_remediation_enabled=False,
        demo=demo,
    )
    assert detail["modifies_infrastructure"] is False
    assert detail["dry_run"] is True
    assert demo.status()["enabled"] is True


def test_live_simulated_clear_and_k8s_adapter_blocked() -> None:
    demo = DemoFailureController()
    demo.activate("http_500", 10, 5, "inc-1")
    execute_simulated(
        "simulate_clear_demo_failure",
        dry_run=False,
        dry_run_only=False,
        remediation_enabled=True,
        kubernetes_remediation_enabled=False,
        demo=demo,
    )
    assert demo.status()["enabled"] is False
    with pytest.raises(RemediationRejectedError):
        execute_simulated(
            "simulate_restart_application",
            dry_run=True,
            dry_run_only=True,
            remediation_enabled=True,
            kubernetes_remediation_enabled=True,
            demo=demo,
        )
