# self-healing-devops-platform

Local-first platform for evidence-based incident analysis and safe, auditable remediation demonstrations.

The application is a FastAPI service with a deterministic analysis engine, SQLite persistence, Prometheus metrics, and a dry-run remediation lifecycle. Docker Compose can run the app with Prometheus and Grafana. Kubernetes, Helm, Argo CD, and Terraform are included as deployment definitions. Cloud resources are not created by the test suite.

## Features

- Health, status, metrics, and a bounded demo workload.
- Rule-based analysis for 5xx rate, latency, readiness failures, CrashLoopBackOff, OOMKilled, failed rollouts, image pull failures, configuration drift, and high CPU or memory when measurements are supplied.
- Persisted incidents and remediation audit records.
- Demo failure mode that is off by default and rejected in production.
- Simulated remediation only. It does not run shell commands or change a cluster.
- Optional HTTPS AI summaries that cannot execute actions. No API key is required to start.
- CI, security, and release workflow definitions with actions pinned to verified commit SHAs.

## Architecture

```mermaid
flowchart LR
  operator[Operator] --> api[FastAPI :8000]
  api --> db[(SQLite)]
  api --> metrics[/metrics]
  metrics --> prom[Prometheus]
  prom --> graf[Grafana]
  api --> engine[Deterministic analysis]
  engine --> api
  git[Git + Helm chart] --> argo[Argo CD manual sync]
  argo --> k8s[Kubernetes single replica]
  tf[Terraform AWS] -. optional, not applied .-> eks[EKS]
```

Kubernetes restarting a crashed container, Argo CD reconciling Git, and this application recommending a fix are three different mechanisms. This service only recommends and, when explicitly approved, records a simulated action.

## Requirements

Verified on this workstation on 2026-10-21:

- macOS, Python 3.12.3 (`python3.12`), pip.
- The local demo does **not** need AWS credentials, an LLM key, a Kubernetes cluster, or a published image.

Also used when present: Docker 29.5.x, Helm 3.22.1, Terraform 1.17.0, Prometheus 3.15.1 `promtool`. Windows was not executed here. PowerShell equivalents are below for the local Python path only.

## Quick start

The folder name ends with a space, so a normal `cd` from your home directory will miss it. Use this path, including the space inside the quotes:

```bash
cd "/Users/sahamamjad/PROJECTS/self healing "
./scripts/start.sh
```

`scripts/start.sh` uses `.venv/bin/python`, so the Anaconda `(base)` prompt does not matter. Do not run `alembic` or `python -m self_healing_platform` from `~`.

The API listens on `http://127.0.0.1:8000`. Interactive docs are at `/docs` unless `APP_ENV=production`.

First-time setup, only if `.venv` does not exist yet:

```bash
cd "/Users/sahamamjad/PROJECTS/self healing "
python3.12 -m venv .venv
.venv/bin/pip install -e ".[dev]"
./scripts/start.sh
```

PowerShell:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
alembic upgrade head
python -m self_healing_platform
```

Makefile targets (macOS/Linux): `make install`, `make test`, `make lint`, `make migrate`, `make run`, `make compose-up`, `make compose-down`, `make smoke`, `make verify`.

## Environment

Copy `.env.example` to `.env` if you want overrides. No secret is required to start.

| Variable | Default | Role |
|---|---|---|
| `APP_ENV` | `development` | `development`, `demo`, or `production` |
| `DATABASE_URL` | `sqlite+pysqlite:///./data/app.sqlite` | SQLAlchemy URL. Container path is `sqlite+pysqlite:////data/app.sqlite` |
| `DEMO_FAILURE_ENABLED` | `false` | Also requires `APP_ENV` of `development` or `demo` |
| `DEMO_AUTH_TOKEN` | empty | Required header `X-Demo-Token` when demo failure is enabled |
| `REMEDIATION_DRY_RUN_ONLY` | `true` | Forces dry-run even if the client asks to execute |
| `REMEDIATION_ENABLED` | `false` | Required, with dry-run off, for the simulated execute path |
| `REMEDIATION_AUTH_TOKEN` | empty | If set, require `X-Remediation-Token` |
| `KUBERNETES_REMEDIATION_ENABLED` | `false` | If true, remediation is rejected. No cluster adapter is implemented |
| `AI_SUMMARIES_ENABLED` | `false` | Optional. `AI_API_URL` must be `https` |
| `GRAFANA_ADMIN_PASSWORD` | `local-demo-change-me` in Compose | Local placeholder only |

`APP_ENV=production` hides demo failure routes even if the flag is true, and disables `/docs`.

## Tests

```bash
pytest --cov=self_healing_platform --cov-report=term-missing
ruff check src tests
ruff format --check src tests
bandit -r src -c pyproject.toml
```

See `docs/TEST_RESULTS.md` for commands actually run and what was not run.

## Monitoring

Compose Prometheus scrapes `app:8000/metrics`. Grafana is provisioned with datasource UID `prometheus` and the overview dashboard. Alert rules are in `deploy/monitoring/prometheus/rules.yml` and are documented in `docs/OPERATIONS.md`.

```bash
docker compose up --build -d
```

App `http://127.0.0.1:8000`, Prometheus `http://127.0.0.1:9090`, Grafana `http://127.0.0.1:3000`. Anonymous viewers can open dashboards. The admin password above is a local placeholder.

The Kubernetes scrape file is separate and looks for Service `self-healing-platform` in namespace `self-healing`, port name `http`. Do not point that file at the Compose hostname `app`.

## Failure simulation

Off by default. To enable it for one local process:

```bash
APP_ENV=demo DEMO_FAILURE_ENABLED=true DEMO_AUTH_TOKEN=local-demo-token \
  python -m self_healing_platform
```

Use the token only in the header, and see `docs/DEMO_SCRIPT.md`. The failure state is in memory. A second replica would not share it. SQLite incident rows are shared only when every replica uses the same database file, which this project does not support. Run one replica.

Liveness, readiness, `/metrics`, the demo control route, and remediation calls are not failed by the simulator, so a simulated outage can still be cleared and scraped.

## Incident analysis

`POST /api/v1/incidents/analyze` with bounded JSON evidence. A rule match is a hypothesis with confidence and limitations, not a confirmed root cause. Missing or weak evidence returns `insufficient_evidence`. Logs are untrusted: embedded instructions are stripped and secrets are redacted before storage or any optional AI call.

## Kubernetes

Raw manifests: `deploy/kubernetes/`. Helm chart: `deploy/helm/self-healing-platform`.

```bash
helm lint deploy/helm/self-healing-platform
helm template demo deploy/helm/self-healing-platform
```

Default values render one non-root replica, a PVC, probes, and a NetworkPolicy. The chart refuses `replicaCount > 1` while SQLite persistence is enabled. NetworkPolicy is enforced only on CNIs that implement it (Calico or Cilium, not every kindnet install).

`values-local.yaml` uses image tag `local` and `pullPolicy: Never` for a cluster that already has a locally loaded image. That tag is for a workstation load, not a release. Release and GitOps tags must be a commit SHA (`sha-<commit>`) or a version, never `latest`.

There is no PodDisruptionBudget or HorizontalPodAutoscaler. One SQLite replica cannot be evicted or scaled safely.

## GitOps

`deploy/argocd/application.yaml` points at chart path `deploy/helm/self-healing-platform` and uses manual sync. `repoURL` contains `REPLACE_OWNER` because this workspace has no Git remote. Replace it with the real repository before registering the app. Automated sync, prune, and self-heal are explained in `docs/ARCHITECTURE.md`. The example file is not applied by default.

## Optional AWS

`terraform/aws/` describes a VPC, private worker subnets, one NAT gateway, an EKS cluster with a private API endpoint, a small managed node group, KMS encryption for Kubernetes secrets, control-plane logs, and reject-only VPC flow logs. It is not applied by any script.

```bash
cd terraform/aws
terraform fmt -check -recursive
terraform init -backend=false
terraform validate
```

`terraform plan` needs AWS credentials and still creates nothing. `terraform apply` and `terraform destroy` spend money and delete resources. Do not run them unless you intend to pay for EKS, NAT, a public IPv4 address, EC2, EBS, and CloudWatch. See `docs/ARCHITECTURE.md`.

## Security

Non-root container user `10001`, read-only root filesystem on Kubernetes, dropped capabilities, and no shell execution from incident payloads. Details and the threat model are in `docs/SECURITY.md`.

## Troubleshooting and cleanup

`docs/TROUBLESHOOTING.md`.

```bash
# stop the Python process with Ctrl-C
docker compose down
rm -rf data .venv
```

Compose `down` keeps named volumes. `docker compose down -v` deletes SQLite, Prometheus, and Grafana data.

## Known limitations

- SQLite on one volume is not highly available and is not safe with more than one application replica.
- Remediation is a simulation. Kubernetes mutation is intentionally unimplemented.
- A rule match is not a confirmed root cause.
- Optional AI text is untrusted and has no execution authority.
- Image tags are version pins, not registry digests. Digests were not recorded because they require a pull.
- Argo CD reconciliation, a live cluster rollout, and AWS apply were not treated as done unless `docs/TEST_RESULTS.md` says they passed.
