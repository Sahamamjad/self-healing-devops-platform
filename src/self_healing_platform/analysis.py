"""Deterministic rule-based incident analysis. No external services required."""

from __future__ import annotations

from dataclasses import dataclass

from self_healing_platform.lifecycle import LifecycleStatus
from self_healing_platform.schemas import (
    AnalysisResult,
    IncidentEvidence,
    ProposedRemediation,
)
from self_healing_platform.security import redact_mapping, sanitize_untrusted_text


@dataclass(frozen=True)
class RuleMatch:
    rule_id: str
    classification: str
    severity: str
    cause: str
    explanation: str
    checks: tuple[str, ...]
    action: str
    verification: tuple[str, ...]
    limitations: str


def _ratio(count: int | None, total: int | None) -> float | None:
    if count is None or total is None or total <= 0:
        return None
    return count / total


def evaluate_rules(evidence: IncidentEvidence) -> list[RuleMatch]:
    matches: list[RuleMatch] = []
    events = {event.reason.lower(): event for event in evidence.kubernetes_events}
    event_blob = " ".join(
        f"{event.reason} {event.message}" for event in evidence.kubernetes_events
    ).lower()
    logs = (evidence.logs_excerpt or "").lower()

    error_ratio = _ratio(evidence.http_5xx_count, evidence.http_request_count)
    if (
        error_ratio is not None
        and evidence.http_request_count
        and evidence.http_request_count >= 20
    ):
        if error_ratio >= 0.05:
            matches.append(
                RuleMatch(
                    rule_id="http_5xx_rate",
                    classification="elevated_5xx",
                    severity="high" if error_ratio >= 0.2 else "medium",
                    cause="Application or dependency returning HTTP 5xx responses",
                    explanation=(
                        f"Observed 5xx ratio {error_ratio:.2%} over {evidence.http_request_count} requests. "
                        "This is a symptom match, not a confirmed root cause."
                    ),
                    checks=(
                        "Inspect application logs around the elevated 5xx window",
                        "Confirm dependency health without executing untrusted commands",
                        "Compare /health/ready with /metrics error counters",
                    ),
                    action="simulate_clear_demo_failure",
                    verification=(
                        "5xx ratio returns below 5% over an equivalent window",
                        "Readiness remains HTTP 200",
                    ),
                    limitations="Requires request counts; ratios on tiny samples are ignored.",
                )
            )

    if evidence.latency_p99_seconds is not None and evidence.latency_p99_seconds >= 1.0:
        matches.append(
            RuleMatch(
                rule_id="latency_p99",
                classification="elevated_latency",
                severity="medium" if evidence.latency_p99_seconds < 3 else "high",
                cause="Increased request latency",
                explanation=(
                    f"Reported p99 latency {evidence.latency_p99_seconds:.3f}s exceeds 1.0s threshold."
                ),
                checks=("Review saturation metrics if provided", "Check for injected demo latency"),
                action="simulate_clear_demo_failure",
                verification=("p99 latency below 1s on a comparable sample",),
                limitations="Latency without a sample size is treated as operator-supplied evidence.",
            )
        )

    if evidence.readiness_consecutive_failures is not None:
        if evidence.readiness_consecutive_failures >= 3:
            matches.append(
                RuleMatch(
                    rule_id="readiness_failures",
                    classification="readiness_failure",
                    severity="high",
                    cause="Failed readiness probes",
                    explanation=(
                        f"{evidence.readiness_consecutive_failures} consecutive readiness failures reported."
                    ),
                    checks=(
                        "Confirm the probe path is /health/ready",
                        "Check database connectivity",
                    ),
                    action="simulate_restart_application",
                    verification=("Readiness returns HTTP 200",),
                    limitations="Does not distinguish probe misconfiguration from true dependency failure.",
                )
            )

    if "crashloopbackoff" in event_blob or "crashloopbackoff" in logs:
        matches.append(
            RuleMatch(
                rule_id="crash_loop",
                classification="crash_loop",
                severity="critical",
                cause="Kubernetes CrashLoopBackOff",
                explanation="Kubernetes event or log text matches CrashLoopBackOff.",
                checks=("Read container last-state reason", "Inspect recent deployment revision"),
                action="simulate_restart_application",
                verification=("Pod reports Running and Ready",),
                limitations="Event text is untrusted; a matching string is not proof of cluster state.",
            )
        )

    if "oomkilled" in event_blob or "oomkilled" in logs or events.get("oomkilled"):
        matches.append(
            RuleMatch(
                rule_id="oom_killed",
                classification="oom_killed",
                severity="high",
                cause="Container OOMKilled",
                explanation="Evidence indicates an out-of-memory kill.",
                checks=(
                    "Compare memory limit to working set",
                    "Look for leaks or unbounded caches",
                ),
                action="simulate_restart_application",
                verification=("No further OOMKilled events in the verification window",),
                limitations="Cannot confirm cgroup memory without cluster metrics.",
            )
        )

    if evidence.rollout_failed or "progressdeadlineexceeded" in event_blob:
        matches.append(
            RuleMatch(
                rule_id="failed_rollout",
                classification="failed_rollout",
                severity="high",
                cause="Failed Kubernetes rollout",
                explanation="Rollout failure flag or ProgressDeadlineExceeded evidence was supplied.",
                checks=("Compare desired vs available replicas", "Inspect ReplicaSet events"),
                action="simulate_restart_application",
                verification=("Rollout reports successful completion",),
                limitations="Does not roll back a live cluster.",
            )
        )

    if (
        evidence.image_pull_failed
        or "errimagepull" in event_blob
        or "imagepullbackoff" in event_blob
    ):
        matches.append(
            RuleMatch(
                rule_id="image_pull",
                classification="image_pull_failure",
                severity="high",
                cause="Image pull failure",
                explanation="Image pull failure was reported in flags or Kubernetes events.",
                checks=(
                    "Confirm image tag exists",
                    "Confirm no private registry is required for local demo",
                ),
                action="simulate_restart_application",
                verification=("Container image pulls successfully",),
                limitations="Cannot access registries from this analysis engine.",
            )
        )

    if (
        evidence.config_expected_hash
        and evidence.config_observed_hash
        and evidence.config_expected_hash != evidence.config_observed_hash
    ):
        matches.append(
            RuleMatch(
                rule_id="config_drift",
                classification="config_drift",
                severity="medium",
                cause="Configuration drift between expected and observed hashes",
                explanation="Expected and observed configuration hashes differ.",
                checks=("Diff declared GitOps state against live ConfigMap", "Do not auto-prune"),
                action="simulate_clear_demo_failure",
                verification=("Hashes match after an approved GitOps sync",),
                limitations="Hash mismatch does not identify which key drifted.",
            )
        )

    high_cpu = evidence.cpu_utilization is not None and evidence.cpu_utilization >= 0.85
    high_mem = evidence.memory_utilization is not None and evidence.memory_utilization >= 0.90
    if high_cpu or high_mem:
        matches.append(
            RuleMatch(
                rule_id="resource_utilization",
                classification="high_resource_utilization",
                severity="medium",
                cause="High CPU or memory utilization",
                explanation="Operator-supplied utilization exceeded configured thresholds (CPU 85%, memory 90%).",
                checks=("Confirm measurement source and window", "Rule out demo injected latency"),
                action="simulate_restart_application",
                verification=("Utilization remains below threshold on a subsequent sample",),
                limitations="Utilization without a documented source is low-confidence.",
            )
        )

    return matches


_SEVERITY_RANK = {"low": 1, "medium": 2, "high": 3, "critical": 4}


def _primary_match(matches: list[RuleMatch]) -> RuleMatch:
    return max(matches, key=lambda match: _SEVERITY_RANK[match.severity])


def analyze_evidence(evidence: IncidentEvidence, symptoms: list[str]) -> AnalysisResult:
    sanitized = redact_mapping(evidence.model_dump())
    if sanitized.get("logs_excerpt"):
        sanitized["logs_excerpt"] = sanitize_untrusted_text(str(sanitized["logs_excerpt"]))

    matches = evaluate_rules(evidence)
    unique_classes = {match.classification for match in matches}

    if not matches:
        return AnalysisResult(
            classification="insufficient_evidence",
            severity="low",
            explanation=(
                "No analysis rule matched. Either evidence is below thresholds or required "
                "fields were omitted. This is not a confirmation that the system is healthy."
            ),
            candidate_causes=[],
            confidence="none",
            uncertainty_notes="Insufficient evidence for classification.",
            recommended_checks=[
                "Provide request counts with 5xx counts (minimum 20 requests for ratio rules)",
                "Include Kubernetes event reasons if claiming cluster symptoms",
                "Attach readiness failure counts if probes are failing",
            ],
            proposed_remediation=ProposedRemediation(
                action="none",
                simulated=True,
                rationale="No safe allowlisted action is justified without a matching rule.",
                allowlisted=False,
            ),
            verification_criteria=["Collect additional evidence and re-analyse"],
            analysis_outcome="insufficient_evidence",
            matched_rules=[],
            lifecycle_status=LifecycleStatus.NEEDS_INVESTIGATION,
            sanitized_evidence=sanitized,
        )

    outcome = "conflicting_evidence" if len(unique_classes) > 2 else "classified"
    primary = _primary_match(matches)
    if outcome == "conflicting_evidence":
        confidence: str = "low"
        uncertainty = (
            "Multiple distinct symptom classes matched. Treat candidate causes as hypotheses, "
            "not a confirmed root cause. " + "; ".join(match.limitations for match in matches)
        )
        lifecycle = LifecycleStatus.NEEDS_INVESTIGATION
        severity = "high"
    else:
        confidence = "medium" if len(matches) == 1 else "low"
        uncertainty = "A rule match is not a confirmed root cause. " + " ".join(
            match.limitations for match in matches
        )
        lifecycle = LifecycleStatus.PROPOSED
        severity = primary.severity
        for match in matches:
            if match.severity == "critical":
                severity = "critical"
                break

    action = primary.action
    return AnalysisResult(
        classification=primary.classification if len(unique_classes) == 1 else "multiple_symptoms",
        severity=severity,  # type: ignore[arg-type]
        explanation=" ".join(match.explanation for match in matches)
        + (" Symptoms: " + "; ".join(symptoms) if symptoms else ""),
        candidate_causes=[match.cause for match in matches],
        confidence=confidence,  # type: ignore[arg-type]
        uncertainty_notes=uncertainty,
        recommended_checks=[check for match in matches for check in match.checks],
        proposed_remediation=ProposedRemediation(
            action=action,
            simulated=True,
            rationale="Allowlisted simulated action for the highest-priority matching rule.",
            allowlisted=True,
        ),
        verification_criteria=[item for match in matches for item in match.verification],
        analysis_outcome=outcome,  # type: ignore[arg-type]
        matched_rules=[match.rule_id for match in matches],
        lifecycle_status=lifecycle,
        sanitized_evidence=sanitized,
    )
