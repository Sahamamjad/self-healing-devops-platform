# Demo script

Run this from the repository root after `make install` (or `pip install -e ".[dev]"`). Use a token that exists only on your machine. The values below are local placeholders.

## Start

```bash
source .venv/bin/activate
alembic upgrade head
python -m self_healing_platform
```

In a second terminal:

```bash
curl -sS http://127.0.0.1:8000/
curl -sS http://127.0.0.1:8000/health/live
curl -sS http://127.0.0.1:8000/health/ready
curl -sS http://127.0.0.1:8000/api/v1/status
curl -sS http://127.0.0.1:8000/metrics | head
```

Demo failure is absent:

```bash
curl -sS -o /dev/null -w "%{http_code}\n" \
  -X POST http://127.0.0.1:8000/api/v1/demo/failure \
  -H 'Content-Type: application/json' \
  -d '{"mode":"http_500"}'
```

Expect `404`.

## Workload

```bash
curl -sS "http://127.0.0.1:8000/api/v1/demo/work?iterations=20&delay_ms=5"
```

`iterations` above 1000 or `delay_ms` above 100 returns 422.

## Failure simulation

Stop the first process. Start it again with demo mode enabled:

```bash
APP_ENV=demo \
DEMO_FAILURE_ENABLED=true \
DEMO_AUTH_TOKEN=local-demo-token \
REMEDIATION_ENABLED=true \
REMEDIATION_DRY_RUN_ONLY=false \
REMEDIATION_AUTH_TOKEN=local-remediate-token \
python -m self_healing_platform
```

Missing or wrong token:

```bash
curl -sS -o /dev/null -w "%{http_code}\n" \
  -X POST http://127.0.0.1:8000/api/v1/demo/failure \
  -H 'Content-Type: application/json' \
  -d '{"mode":"http_500","duration_seconds":30,"max_requests":5}'
```

Expect `401`.

Enable a bounded 503 simulation:

```bash
curl -sS -X POST http://127.0.0.1:8000/api/v1/demo/failure \
  -H 'Content-Type: application/json' \
  -H 'X-Demo-Token: local-demo-token' \
  -d '{"mode":"http_503","duration_seconds":30,"max_requests":5}'
```

The JSON includes an `incident_id`. Probes stay up:

```bash
curl -sS -o /dev/null -w "live %{http_code}\n" http://127.0.0.1:8000/health/live
curl -sS -o /dev/null -w "ready %{http_code}\n" http://127.0.0.1:8000/health/ready
curl -sS -o /dev/null -w "status %{http_code}\n" http://127.0.0.1:8000/api/v1/status
```

Expect live and ready `200`, and status `503` while the simulation still has remaining requests. `/metrics` is not failed by the simulator.

This state is inside one process. Another replica would not see it.

## Incident analysis

```bash
curl -sS -X POST http://127.0.0.1:8000/api/v1/incidents/analyze \
  -H 'Content-Type: application/json' \
  -d '{
    "source": "demo",
    "affected_component": "self-healing-platform",
    "symptoms": ["error ratio increased"],
    "evidence": {"http_5xx_count": 25, "http_request_count": 100}
  }'
```

Expect `classification` `elevated_5xx`, `analysis_outcome` `classified`, and `lifecycle_status` `Proposed`. The explanation says the match is not a confirmed root cause.

Too little evidence:

```bash
curl -sS -X POST http://127.0.0.1:8000/api/v1/incidents/analyze \
  -H 'Content-Type: application/json' \
  -d '{"source":"demo","affected_component":"app","symptoms":[],"evidence":{}}'
```

Expect `insufficient_evidence` and `Needs investigation`.

## Safe remediation

Dry-run against the 5xx incident id from the analyse call. Replace `INCIDENT_ID`.

```bash
curl -sS -X POST "http://127.0.0.1:8000/api/v1/incidents/INCIDENT_ID/remediate" \
  -H 'Content-Type: application/json' \
  -H 'X-Remediation-Token: local-remediate-token' \
  -d '{"action":"simulate_clear_demo_failure","approved":true,"dry_run":true,"actor":"operator"}'
```

Expect `dry_run: true` and `modifies_infrastructure: false`. The incident moves to `Approved`. The demo flag is still on.

Clear the simulation for real, using the incident id returned when the demo was enabled:

```bash
curl -sS -X POST "http://127.0.0.1:8000/api/v1/incidents/DEMO_INCIDENT_ID/remediate" \
  -H 'Content-Type: application/json' \
  -H 'X-Remediation-Token: local-remediate-token' \
  -d '{"action":"simulate_clear_demo_failure","approved":true,"dry_run":false,"actor":"operator"}'
```

Expect `dry_run: false`, `simulated: true`, `modifies_infrastructure: false`, and lifecycle `Verified`.

Rejected actions:

```bash
curl -sS -o /dev/null -w "%{http_code}\n" \
  -X POST "http://127.0.0.1:8000/api/v1/incidents/INCIDENT_ID/remediate" \
  -H 'Content-Type: application/json' \
  -H 'X-Remediation-Token: local-remediate-token' \
  -d '{"action":"kubectl delete pod","approved":true,"dry_run":true}'
```

Expect `403`.

## Recovery check

```bash
curl -sS -o /dev/null -w "status %{http_code}\n" http://127.0.0.1:8000/api/v1/status
curl -sS -o /dev/null -w "ready %{http_code}\n" http://127.0.0.1:8000/health/ready
curl -sS http://127.0.0.1:8000/api/v1/incidents/DEMO_INCIDENT_ID
```

Expect status and ready `200`. The audit list on the incident shows the action, actor, and verification status. Nothing outside this process was restarted or deleted.

Stop the server with Ctrl-C. Start it again with the default environment and `GET` the same incident id. The row is still there. The in-memory demo flag is not.
