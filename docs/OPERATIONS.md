# Operations

## Logs

Logs are JSON on stdout: timestamp, level, logger, message, and `request_id` when a request is in progress. Uvicorn's own access log is left at its default. Application request lines include method, route template, and status.

Do not log `DEMO_AUTH_TOKEN`, `REMEDIATION_AUTH_TOKEN`, or `AI_API_TOKEN`.

## Health checks

| Endpoint | Depends on | Success |
|---|---|---|
| `GET /health/live` | Process only | HTTP 200 `{"status":"live"}` |
| `GET /health/ready` | Database connection and migrated tables | HTTP 200, or HTTP 503 with `database_unavailable` or `schema_missing` |

Container `HEALTHCHECK` and Compose healthcheck call `/health/live` with Python's standard library. Kubernetes startup and liveness use `/health/live`. Readiness uses `/health/ready`.

If readiness says `schema_missing`, run `alembic upgrade head`. The container entrypoint does that before Uvicorn starts.

## Metrics

Scrape `GET /metrics` on port 8000. Label cardinality is limited to method, route template, status, analysis outcome, and demo mode.

`application_uptime_seconds` is updated when metrics are rendered or a request is observed.

## Alerts

Rules file: `deploy/monitoring/prometheus/rules.yml`. Group: `self-healing-platform`. `promtool check rules` on Prometheus 3.15.1 accepted these three rules. They use metrics this process exports, plus Prometheus `up`.

### ServiceUnavailable

- Expression: `up{job="self-healing-app"} == 0`
- For: 2m
- Threshold: target down
- Rationale: the scrape job defined in both Prometheus configs is `self-healing-app`. A failed scrape sets `up` to 0. A target that was never configured does not alert, because the series is absent.
- Runbook: confirm the app process, then `GET /health/live` and `GET /metrics`. In Compose, the Prometheus target is `app:8000`. In Kubernetes, confirm Service `self-healing-platform` and endpoints. This alert does not prove why the process stopped.

### ElevatedErrorRatio

- Expression: `sum(rate(http_requests_total{status=~"5.."}[5m])) / clamp_min(sum(rate(http_requests_total[5m])), 0.001) > 0.10`
- For: 5m
- Threshold: 5xx ratio above 10%
- Rationale: `clamp_min` keeps an idle service (rate near zero) from dividing by zero or paging on an empty window. The ratio is a symptom. Demo failure mode can trip it on purpose.
- Runbook: compare `/api/v1/status` and recent incident rows. If a demo is on, call the remediate dry-run or the simulated clear in `docs/DEMO_SCRIPT.md`. If it is not a demo, read application logs for the same `request_id` values. Do not treat the ratio as a root cause.

### HighRequestLatency

- Expression: `histogram_quantile(0.99, sum(rate(http_request_duration_seconds_bucket[5m])) by (le)) > 1`
- For: 10m
- Threshold: estimated p99 above 1 second
- Rationale: the histogram is `http_request_duration_seconds`. An empty window yields NaN, and NaN is not greater than 1, so an idle service does not fire this rule.
- Runbook: check whether demo latency injection is enabled (`mode=inject_latency` only affects `/api/v1/demo/work`). Compare `application_uptime_seconds` and the process logs. A slow dependency is a hypothesis until evidence says otherwise.

## Incident investigation

1. `GET /health/ready` and `GET /api/v1/status`.
2. `GET /api/v1/incidents?limit=20` and open one id.
3. Read `matched_rules`, `uncertainty_notes`, `candidate_causes`, and `verification_criteria`.
4. If `analysis_outcome` is `insufficient_evidence` or `conflicting_evidence`, collect the missing fields and analyse again. Do not pick a cause because a keyword matched.

## Recovery verification

After a simulated clear:

- `GET /api/v1/demo/failure` shows `enabled: false` when demo routes are on.
- A normal route such as `GET /api/v1/status` returns 200.
- The incident `lifecycle_status` is `Verified` only when a non-dry-run simulated action was approved and recorded.
- `GET /health/ready` stays 200 if SQLite is still reachable.
- Prometheus `up{job="self-healing-app"}` returns to 1 after the next scrape. This repository does not claim a recovery-time number. The scrape interval in the provided configs is 15s, and alerts wait 2 to 10 minutes on top of that.
