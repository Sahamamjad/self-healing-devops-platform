# Test results

Recorded on 2026-10-21 on macOS (darwin arm64), Python 3.12.3, in this repository. Skipped and not-run checks are not counted as passes.

## Application tests

Command:

```bash
.venv/bin/pytest --cov=self_healing_platform --cov-report=term-missing -q
```

Result: **PASS** — 43 passed, 2 skipped, coverage 86% of `self_healing_platform`.

The two skips are `tests/config/test_static_contracts.py`: `test_helm_lint` and `test_terraform_validate`, because `helm` and `terraform` were not on `PATH`.

With the downloaded binaries on `PATH`:

```bash
PATH=".tools:$PATH" .venv/bin/pytest tests/config -q
```

Result: **PASS** — 8 passed. That run includes Helm lint and `terraform validate`.

`logging.py` and `main.py` are not imported by pytest (0% in the coverage table). The Compose and local Uvicorn processes do load them; see the runtime section.

## Lint and security tools that ran here

| Check | Command | Result |
|---|---|---|
| Ruff lint | `.venv/bin/ruff check src tests` | PASS |
| Ruff format | `.venv/bin/ruff format --check src tests` | PASS |
| Bandit | `.venv/bin/bandit -r src -c pyproject.toml -q` | PASS. `host=0.0.0.0` is marked `# nosec B104` because the container must listen on all interfaces; published ports are explicit |
| pip-audit | `.venv/bin/pip-audit` | PASS for third-party packages: "No known vulnerabilities found". The local project name is not on PyPI and was reported as not audited. That is not a clean bill for unpublished code |

Trivy: **NOT RUN**. The binary is not installed. The security workflow is written to fail on critical and high findings. No scan result is claimed.

## Migrations, restart, and demo

`alembic upgrade head` against `sqlite+pysqlite:///./data/app.sqlite` applied revision `0001`.

Local Uvicorn then served `/`, `/health/live`, `/health/ready`, `/api/v1/status`, and `/metrics`. `scripts/smoke_test.py` printed PASS for each of those and for demo failure HTTP 404.

An analysed incident `a9e4c68f-1328-4c55-b3a1-fc726c75d540` (`elevated_5xx`, source `local-smoke`) was fetched again with HTTP 200 after the process was stopped and started. Persistence across a process restart: **PASS**.

Demo script against a second database (`data/demo.sqlite`) with demo mode explicitly enabled:

| Step | Result |
|---|---|
| `POST /api/v1/demo/failure` without token | 401 |
| Enable `http_503` with `X-Demo-Token` | 200, incident created |
| `/health/live`, `/health/ready` during the simulation | 200 |
| `/api/v1/status` during the simulation | 503 |
| Analyse 25/100 5xx | `elevated_5xx`, `Proposed`, `classified` |
| Analyse empty evidence | `insufficient_evidence`, `Needs investigation` |
| Dry-run remediate | `dry_run=true`, `modifies_infrastructure=false`, status still 503 |
| Approved non-dry-run clear | `executed_simulated`, `simulated=true`, `modifies_infrastructure=false` |
| `kubectl delete pod` action | 403 |
| `/api/v1/status` and `/health/ready` after clear | 200 |
| Demo incident lifecycle | `Verified`, 1 audit |

## Docker and Compose

`docker compose config --quiet`: **PASS** (Docker daemon was running after Docker Desktop was opened).

`docker compose up --build -d`: **PASS**. Image `self-healing-devops-platform:local` built. `volume-init` exited, app became healthy, Prometheus and Grafana started.

`docker compose exec -T app id`: `uid=10001(appuser)`.

`scripts/smoke_test.py` against the container: **PASS**, including demo failure 404.

Prometheus `GET /api/v1/targets` after the first scrape: job `self-healing-app`, URL `http://app:8000/metrics`, health `up`, empty `lastError`.

`up{job="self-healing-app"}` returned value `1`. `http_requests_total` returned series labelled with `method`, `route`, and `status` (one observed series was `GET /health/live` status `200`).

Container restart: incident `0bf668db-b35e-4e58-a425-8d8c42ea2c26` (source `compose`, `elevated_5xx`) was still returned after `docker compose restart app` once readiness was 200. **PASS**.

Grafana `GET /api/health`: HTTP 200, version `13.2.4`, database `ok`.

`GET /api/datasources`: Prometheus, uid `prometheus`, url `http://prometheus:9090`.

`GET /api/search` included dashboard `Self-healing platform overview` uid `self-healing-overview`.

`GET /api/datasources/uid/prometheus/health`: HTTP 200, message `Successfully queried the Prometheus API.`

No dashboard screenshot was taken.

The stack was left running: app `:8000`, Prometheus `:9090`, Grafana `:3000`. Stop it with `docker compose down`. `docker compose down -v` also deletes the volumes.

## Prometheus tooling

Prometheus **3.15.1** `promtool` from the official darwin-arm64 release archive:

- `promtool check rules deploy/monitoring/prometheus/rules.yml`: **PASS** (3 rules).
- `promtool check config` on copies of the Compose and Kubernetes configs whose `rule_files` entry pointed at the local rules file: **PASS**.

The committed configs keep `rule_files: /etc/prometheus/rules.yml` because that is the path inside the Compose container. Checking those files unchanged on the laptop fails for that path reason. The running Prometheus container loaded its config; the target became `up`.

## Helm and Kubernetes

Helm **v3.22.1**:

- `helm lint deploy/helm/self-healing-platform`: **PASS** (info only: icon is recommended).
- `helm lint` with `values-local.yaml`: **PASS**.
- `helm template demo deploy/helm/self-healing-platform`: **PASS** (201 lines). Rendered output contained `replicas: 1`, `runAsNonRoot: true`, `containerPort: 8000`, `/health/live`, and `/health/ready`.
- `helm template ... --set replicaCount=2`: **PASS** as a rejection. Helm exited with the SQLite replica guard message.

Kubernetes API: **NOT RUN**. `kubectl` has no current context; `localhost:8080` was refused. No rollout, probe, or PVC behaviour was observed on a cluster. YAML rendering is not a deployment.

## Argo CD

The Application manifest is valid YAML and references chart path `deploy/helm/self-healing-platform`. `repoURL` still contains `REPLACE_OWNER`. Reconciliation: **NOT RUN**.

## Terraform

Terraform **v1.17.0**, provider `hashicorp/aws` **5.100.0** (constraint `~> 5.80`):

- `terraform fmt -recursive`: reformatted `variables.tf`, then `fmt -check` was clean as part of the same run.
- `terraform init -backend=false`: **PASS**.
- `terraform validate`: **PASS** (`Success! The configuration is valid.`).

`terraform plan`: **NOT RUN** (no AWS credentials used).

`terraform apply` and `terraform destroy`: **NOT RUN**. No resources were created.

## GitHub Actions

Workflows were not executed on GitHub (no remote). Action SHAs were checked against upstream release tags on 2026-10-21 and recorded in `docs/IMPLEMENTATION_PLAN.md`. Local execution of those workflows: **NOT RUN**.

## Still unverified

- A Kubernetes rollout, Service connectivity, and PVC behaviour on a real cluster.
- Argo CD sync and health.
- AWS plan, apply, and any cost or endpoint behaviour.
- Trivy filesystem, image, secret, and misconfiguration results.
- Image digests and a GHCR publish.
- Grafana panels with a human looking at them. The API confirms the dashboard and datasource were provisioned and that Grafana could query Prometheus.
- Windows / PowerShell commands. They are documented and were not executed.
