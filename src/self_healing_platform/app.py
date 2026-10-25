"""FastAPI application factory."""

from __future__ import annotations

import asyncio
import hmac
import logging
import time
import uuid
from collections.abc import Callable
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, PlainTextResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from starlette.middleware.base import BaseHTTPMiddleware

from self_healing_platform import __app_name__, __version__
from self_healing_platform.ai import maybe_summarize
from self_healing_platform.analysis import analyze_evidence
from self_healing_platform.config import Settings
from self_healing_platform.db import (
    DatabaseNotReadyError,
    check_database,
    create_db_engine,
    create_session_factory,
)
from self_healing_platform.demo import DemoFailureController
from self_healing_platform.lifecycle import InvalidTransitionError, LifecycleStatus
from self_healing_platform.metrics import CONTENT_TYPE, AppMetrics
from self_healing_platform.models import Incident, RemediationAudit
from self_healing_platform.remediation import (
    RemediationRejectedError,
    execute_simulated,
    next_status_after_execution,
    prepare_lifecycle,
    validate_action,
)
from self_healing_platform.schemas import (
    AnalyzeIncidentRequest,
    DemoFailureRequest,
    DemoFailureResponse,
    DemoWorkResponse,
    ErrorBody,
    ErrorResponse,
    IncidentListResponse,
    IncidentResponse,
    LiveResponse,
    ReadyResponse,
    RemediateRequest,
    RemediationAuditResponse,
    RootResponse,
    StatusResponse,
)

logger = logging.getLogger("self_healing_platform")

PROTECTED_HEALTH = ("/health/live", "/health/ready")


def _token_ok(expected: str, provided: str | None) -> bool:
    if not expected:
        return False
    if provided is None:
        return False
    return hmac.compare_digest(expected.encode("utf-8"), provided.encode("utf-8"))


def _error(status: int, code: str, message: str, request_id: str) -> JSONResponse:
    payload = ErrorResponse(error=ErrorBody(code=code, message=message, request_id=request_id))
    return JSONResponse(status_code=status, content=payload.model_dump())


def _normalize_route(request: Request) -> str:
    route = request.scope.get("route")
    if route is not None and getattr(route, "path", None):
        return str(route.path)
    return "unmatched"


class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        request.state.request_id = request_id
        start = time.perf_counter()
        app_metrics: AppMetrics = request.app.state.metrics
        demo: DemoFailureController = request.app.state.demo
        settings: Settings = request.app.state.settings

        content_length = request.headers.get("content-length")
        if content_length is not None:
            try:
                size = int(content_length)
            except ValueError:
                size = settings.max_request_bytes + 1
            if size > settings.max_request_bytes:
                response = _error(
                    413,
                    "payload_too_large",
                    "Request body exceeds the configured limit",
                    request_id,
                )
                response.headers["X-Request-ID"] = request_id
                app_metrics.observe_request(
                    request.method, "unmatched", 413, time.perf_counter() - start
                )
                return response

        failure_mode = demo.consume_for_path(request.url.path)
        if failure_mode == "http_500":
            response: Response = JSONResponse(
                status_code=500,
                content={
                    "error": {
                        "code": "demo_failure",
                        "message": "Simulated HTTP 500 (demo mode)",
                        "request_id": request_id,
                    }
                },
            )
        elif failure_mode == "http_503":
            response = JSONResponse(
                status_code=503,
                content={
                    "error": {
                        "code": "demo_failure",
                        "message": "Simulated HTTP 503 (demo mode)",
                        "request_id": request_id,
                    }
                },
            )
        else:
            if failure_mode == "inject_latency":
                await asyncio.sleep(0.25)
            try:
                response = await call_next(request)
            except Exception:
                logger.exception("Unhandled error", extra={"request_id": request_id})
                response = _error(500, "internal_error", "Internal server error", request_id)

        duration = time.perf_counter() - start
        app_metrics.observe_request(
            request.method,
            _normalize_route(request),
            response.status_code,
            duration,
        )
        response.headers["X-Request-ID"] = request_id
        response.headers["X-App-Env"] = settings.app_env
        logger.info(
            "request completed",
            extra={
                "request_id": request_id,
                "method": request.method,
                "route": _normalize_route(request),
                "status_code": response.status_code,
            },
        )
        return response


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    engine = create_db_engine(settings)
    session_factory = create_session_factory(engine)
    metrics = AppMetrics()
    demo = DemoFailureController()
    started = time.monotonic()

    application = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description="Evidence-based incident analysis and safe remediation demonstration.",
        docs_url="/docs" if not settings.is_production else None,
        redoc_url=None,
    )
    application.state.settings = settings
    application.state.engine = engine
    application.state.session_factory = session_factory
    application.state.metrics = metrics
    application.state.demo = demo
    application.state.started_at = started

    application.add_middleware(RequestContextMiddleware)

    def get_session() -> Any:
        session = session_factory()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    @application.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
        request_id = getattr(request.state, "request_id", "unknown")
        detail = exc.detail if isinstance(exc.detail, str) else "request_failed"
        return _error(exc.status_code, "http_error", detail, request_id)

    @application.exception_handler(RequestValidationError)
    async def validation_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
        request_id = getattr(request.state, "request_id", "unknown")
        return _error(422, "validation_error", "Request validation failed", request_id)

    @application.get("/", response_model=RootResponse)
    def root() -> RootResponse:
        return RootResponse(
            name=__app_name__,
            version=__version__,
            description="Local-first self-healing DevOps demonstration platform.",
        )

    @application.get("/health/live", response_model=LiveResponse)
    def live() -> LiveResponse:
        return LiveResponse(status="live")

    @application.get("/health/ready", response_model=ReadyResponse)
    def ready(request: Request) -> ReadyResponse:
        try:
            check_database(request.app.state.engine)
        except DatabaseNotReadyError as exc:
            logger.warning(
                "Readiness check failed",
                extra={"request_id": getattr(request.state, "request_id", None)},
            )
            return JSONResponse(  # type: ignore[return-value]
                status_code=503,
                content=ReadyResponse(
                    status="not_ready",
                    database="unavailable",
                    reason=exc.reason,
                ).model_dump(),
            )
        return ReadyResponse(status="ready", database="ok")

    @application.get("/api/v1/status", response_model=StatusResponse)
    def status() -> StatusResponse:
        backend = "sqlite" if settings.database_url.startswith("sqlite") else "other"
        return StatusResponse(
            service=settings.app_name,
            version=settings.app_version,
            environment=settings.app_env,
            uptime_seconds=round(time.monotonic() - started, 3),
            demo_failure_enabled=settings.demo_routes_allowed,
            remediation_dry_run_only=settings.remediation_dry_run_only,
            ai_summaries_enabled=settings.ai_summaries_enabled,
            database_backend=backend,
        )

    @application.get("/metrics")
    def prometheus_metrics() -> Response:
        return PlainTextResponse(metrics.render().decode("utf-8"), media_type=CONTENT_TYPE)

    @application.get("/api/v1/demo/work", response_model=DemoWorkResponse)
    def demo_work(
        iterations: int = Query(default=10, ge=1, le=1000),
        delay_ms: int = Query(default=5, ge=0, le=100),
    ) -> DemoWorkResponse:
        t0 = time.perf_counter()
        acc = 0
        for i in range(iterations):
            acc += i
            if delay_ms:
                time.sleep(delay_ms / 1000)
        elapsed = (time.perf_counter() - t0) * 1000
        logger.debug("demo work acc=%s", acc)
        return DemoWorkResponse(
            iterations=iterations, delay_ms=delay_ms, elapsed_ms=round(elapsed, 3)
        )

    @application.post("/api/v1/demo/failure", response_model=DemoFailureResponse)
    def start_demo_failure(
        payload: DemoFailureRequest,
        request: Request,
        session: Session = Depends(get_session),
    ) -> DemoFailureResponse:
        if settings.is_production or not settings.demo_failure_enabled:
            raise HTTPException(status_code=404, detail="Not found")
        if not settings.demo_routes_allowed:
            raise HTTPException(status_code=404, detail="Not found")
        token = request.headers.get("X-Demo-Token")
        if not _token_ok(settings.demo_auth_token, token):
            raise HTTPException(status_code=401, detail="Invalid demo authorization token")
        duration = min(payload.duration_seconds, settings.demo_max_duration_seconds)
        max_requests = min(payload.max_requests, settings.demo_max_failing_requests)

        analysis = analyze_evidence(
            payload_to_evidence(payload.mode),
            symptoms=[f"demo:{payload.mode}"],
        )
        incident = persist_analysis(
            session,
            source="demo_failure",
            affected_component="self-healing-platform",
            symptoms=[f"Controlled demo failure mode={payload.mode}"],
            analysis=analysis,
        )
        state = demo.activate(payload.mode, duration, max_requests, incident.id)
        metrics.demo_failure_events_total.labels(mode=payload.mode).inc()
        return DemoFailureResponse(
            enabled=bool(state["enabled"]),
            mode=payload.mode,
            remaining_seconds=float(state["remaining_seconds"]),
            remaining_requests=int(state["remaining_requests"]),
            incident_id=incident.id,
            message=(
                "Demo failure is process-local. Multiple replicas do not share this in-memory "
                "state; only incident rows in SQLite are shared when a single replica is used."
            ),
        )

    @application.get("/api/v1/demo/failure", response_model=DemoFailureResponse)
    def demo_failure_status() -> DemoFailureResponse:
        if settings.is_production or not settings.demo_failure_enabled:
            raise HTTPException(status_code=404, detail="Not found")
        state = demo.status()
        return DemoFailureResponse(
            enabled=bool(state["enabled"]),
            mode=state["mode"],  # type: ignore[arg-type]
            remaining_seconds=float(state["remaining_seconds"]),
            remaining_requests=int(state["remaining_requests"]),
            incident_id=state["incident_id"]
            if state["incident_id"] is None
            else str(state["incident_id"]),
            message="Current process-local demo failure state.",
        )

    @application.get("/api/v1/incidents", response_model=IncidentListResponse)
    def list_incidents(
        session: Session = Depends(get_session),
        limit: int = Query(default=20, ge=1, le=100),
        offset: int = Query(default=0, ge=0, le=100_000),
        severity: str | None = Query(default=None),
        lifecycle_status: str | None = Query(default=None),
        classification: str | None = Query(default=None),
    ) -> IncidentListResponse:
        stmt = select(Incident)
        count_stmt = select(func.count()).select_from(Incident)
        if severity:
            if severity not in {"low", "medium", "high", "critical"}:
                raise HTTPException(status_code=422, detail="Invalid severity filter")
            stmt = stmt.where(Incident.severity == severity)
            count_stmt = count_stmt.where(Incident.severity == severity)
        if lifecycle_status:
            allowed_status = {item.value for item in LifecycleStatus}
            if lifecycle_status not in allowed_status:
                raise HTTPException(status_code=422, detail="Invalid lifecycle_status filter")
            stmt = stmt.where(Incident.lifecycle_status == lifecycle_status)
            count_stmt = count_stmt.where(Incident.lifecycle_status == lifecycle_status)
        if classification:
            stmt = stmt.where(Incident.classification == classification)
            count_stmt = count_stmt.where(Incident.classification == classification)
        total = session.execute(count_stmt).scalar_one()
        rows = (
            session.execute(stmt.order_by(Incident.created_at.desc()).limit(limit).offset(offset))
            .scalars()
            .all()
        )
        return IncidentListResponse(
            items=[_incident_to_response(row) for row in rows],
            total=total,
            limit=limit,
            offset=offset,
        )

    @application.get("/api/v1/incidents/{incident_id}", response_model=IncidentResponse)
    def get_incident(incident_id: str, session: Session = Depends(get_session)) -> IncidentResponse:
        incident = session.get(Incident, incident_id)
        if incident is None:
            raise HTTPException(status_code=404, detail="Incident not found")
        return _incident_to_response(incident)

    @application.post("/api/v1/incidents/analyze", response_model=IncidentResponse)
    def analyze(
        payload: AnalyzeIncidentRequest,
        session: Session = Depends(get_session),
    ) -> IncidentResponse:
        t0 = time.perf_counter()
        result = analyze_evidence(payload.evidence, payload.symptoms)
        duration = time.perf_counter() - t0
        metrics.incident_analysis_duration_seconds.observe(duration)
        metrics.incident_analysis_total.labels(outcome=result.analysis_outcome).inc()
        summary = maybe_summarize(
            settings,
            {
                "source": payload.source,
                "affected_component": payload.affected_component,
                "symptoms": payload.symptoms,
                "classification": result.classification,
                "explanation": result.explanation,
                "evidence": result.sanitized_evidence,
            },
        )
        incident = persist_analysis(
            session,
            source=payload.source,
            affected_component=payload.affected_component,
            symptoms=payload.symptoms,
            analysis=result,
            ai_summary=summary,
        )
        return _incident_to_response(incident)

    @application.post(
        "/api/v1/incidents/{incident_id}/remediate", response_model=RemediationAuditResponse
    )
    def remediate(
        incident_id: str,
        payload: RemediateRequest,
        request: Request,
        session: Session = Depends(get_session),
    ) -> RemediationAuditResponse:
        if settings.remediation_auth_token:
            token = request.headers.get("X-Remediation-Token")
            if not _token_ok(settings.remediation_auth_token, token):
                raise HTTPException(status_code=401, detail="Invalid remediation token")
        incident = session.get(Incident, incident_id)
        if incident is None:
            raise HTTPException(status_code=404, detail="Incident not found")
        try:
            action = validate_action(payload.action)
            current = prepare_lifecycle(incident.lifecycle_status, payload.approved)
            will_dry_run = payload.dry_run or settings.remediation_dry_run_only
            if not will_dry_run and current != LifecycleStatus.APPROVED.value:
                raise InvalidTransitionError(
                    f"Execution requires Approved status, current is {current}"
                )
            incident.lifecycle_status = current
            detail = execute_simulated(
                action,
                dry_run=payload.dry_run,
                dry_run_only=settings.remediation_dry_run_only,
                remediation_enabled=settings.remediation_enabled,
                kubernetes_remediation_enabled=settings.kubernetes_remediation_enabled,
                demo=demo,
            )
            new_status = next_status_after_execution(
                current, dry_run=detail["dry_run"], success=True
            )
            incident.lifecycle_status = new_status
            audit = RemediationAudit(
                incident_id=incident.id,
                requested_action=action,
                result="dry_run" if detail["dry_run"] else "executed_simulated",
                dry_run=bool(detail["dry_run"]),
                verification_status="recorded" if detail["dry_run"] else "verified_simulated",
                actor=payload.actor,
                detail=detail,
            )
            session.add(audit)
            session.flush()
            return RemediationAuditResponse.model_validate(audit)
        except RemediationRejectedError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        except InvalidTransitionError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    return application


def persist_analysis(
    session: Session,
    *,
    source: str,
    affected_component: str,
    symptoms: list[str],
    analysis: Any,
    ai_summary: dict[str, Any] | None = None,
) -> Incident:
    incident = Incident(
        source=source,
        affected_component=affected_component,
        symptoms=symptoms,
        severity=analysis.severity,
        explanation=analysis.explanation,
        evidence=analysis.sanitized_evidence,
        candidate_causes=analysis.candidate_causes,
        confidence=analysis.confidence,
        uncertainty_notes=analysis.uncertainty_notes,
        recommended_checks=analysis.recommended_checks,
        proposed_remediation=analysis.proposed_remediation.model_dump(),
        verification_criteria=analysis.verification_criteria,
        lifecycle_status=analysis.lifecycle_status.value,
        analysis_outcome=analysis.analysis_outcome,
        matched_rules=analysis.matched_rules,
        classification=analysis.classification,
        ai_summary=ai_summary,
    )
    session.add(incident)
    session.flush()
    return incident


def _incident_to_response(incident: Incident) -> IncidentResponse:
    return IncidentResponse(
        id=incident.id,
        created_at=incident.created_at,
        updated_at=incident.updated_at,
        source=incident.source,
        affected_component=incident.affected_component,
        symptoms=list(incident.symptoms or []),
        severity=incident.severity,  # type: ignore[arg-type]
        explanation=incident.explanation,
        evidence=dict(incident.evidence or {}),
        candidate_causes=list(incident.candidate_causes or []),
        confidence=incident.confidence,  # type: ignore[arg-type]
        uncertainty_notes=incident.uncertainty_notes,
        recommended_checks=list(incident.recommended_checks or []),
        proposed_remediation=dict(incident.proposed_remediation or {}),
        verification_criteria=list(incident.verification_criteria or []),
        lifecycle_status=LifecycleStatus(incident.lifecycle_status),
        analysis_outcome=incident.analysis_outcome,  # type: ignore[arg-type]
        matched_rules=list(incident.matched_rules or []),
        classification=incident.classification,
        ai_summary=incident.ai_summary,
        audits=[RemediationAuditResponse.model_validate(item) for item in incident.audits],
    )


def payload_to_evidence(mode: str) -> Any:
    from self_healing_platform.schemas import IncidentEvidence

    if mode == "inject_latency":
        return IncidentEvidence(latency_p99_seconds=1.5, http_request_count=50, http_5xx_count=0)
    return IncidentEvidence(http_5xx_count=30, http_request_count=100)
