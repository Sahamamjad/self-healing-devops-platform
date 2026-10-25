# Implementation plan

**Updated:** 2026-10-21  
**Workspace:** the git repository whose directory name ends with a space (`self healing `). A sibling directory without the trailing space holds an older copy and is not this repository.

## Environment observed

| Tool | Status on 2026-10-21 |
|---|---|
| Python | 3.12.3 used for the venv. Default `python3` is 3.13.5 |
| Docker CLI | 29.5.2 |
| Docker Compose CLI | v5.1.3 |
| Docker daemon | Stopped at first inspection. Docker.app is installed |
| kubectl | Client v1.34.1. No current context. `localhost:8080` refused |
| Helm | Not on PATH from Homebrew (`terraform` formula is also absent). Official Helm **v3.22.1** binary was downloaded to `.tools/` (gitignored) and used for lint |
| Terraform | Official **v1.17.0** binary in `.tools/`. `terraform validate` succeeded with AWS provider **5.100.0** |
| promtool | Prometheus **v3.15.1** darwin-arm64 archive. `check rules` and `check config` succeeded |
| AWS CLI | Not installed. No apply |
| kind / minikube / k3d | Not installed |

## Versions checked against upstream on 2026-10-21

Python constraints in `pyproject.toml` use ranges whose lower bounds are versions that existed on PyPI that day:

| Package | Constraint | Resolved in the local venv |
|---|---|---|
| fastapi | `>=0.159.1,<0.160` | 0.159.1 |
| pydantic | `>=2.14.1,<2.15` | 2.14.1 |
| pydantic-settings | `>=2.16.1,<2.17` | 2.16.1 |
| uvicorn | `>=0.54.0,<0.55` | 0.54.0 |
| sqlalchemy | `>=2.0.40,<2.2` | 2.1.6 |
| alembic | `>=1.20.0,<1.21` | 1.20.0 |
| prometheus-client | `>=0.26.0,<0.27` | 0.26.0 |
| httpx | `>=0.28.1,<0.29` | 0.28.1 |
| pytest | `>=9.1.1,<10` | 9.1.1 |
| pytest-cov | `>=7.1.0,<8` | 7.1.0 |
| ruff | `==0.17.1` | 0.17.1 |
| bandit | `>=1.9.4,<1.10` | 1.9.4 |
| pip-audit | `>=2.10.1,<3` | 2.10.1 |
| pyyaml | `>=6.0.3,<7` | 6.0.3 |
| httpx2 | `>=2.16.0,<2.17` | 2.16.0 |

Images confirmed on Docker Hub that day: `python:3.12-slim-bookworm`, `prom/prometheus:v3.15.1`, `grafana/grafana:13.2.4`, `busybox:1.37.0`. Digests were not recorded.

GitHub Action SHAs were resolved from each repository's latest release tag, then checked against the tag object's commit:

| Action | Tag | Commit |
|---|---|---|
| actions/checkout | v7.0.1 | `3d3c42e5aac5ba805825da76410c181273ba90b1` |
| actions/setup-python | v7.0.0 | `5fda3b95a4ea91299a34e894583c3862153e4b97` |
| actions/upload-artifact | v7.0.2 | `cf430e030ddbb5b0abf93d22962f4752f3646cd9` |
| docker/setup-buildx-action | v4.4.1 | `f87e5991a6d7451dcb8d9637bfbc97413f497069` |
| docker/build-push-action | v7.4.0 | `c3c9e263c25d99ce0380d002d59b67737d91b0dc` |
| docker/login-action | v4.6.0 | `dbcb813823bdd20940b903addbd779551569679f` |
| aquasecurity/trivy-action | v0.36.0 | `ed142fd0673e97e23eac54620cfb913e5ce36c25` |
| hashicorp/setup-terraform | v4.0.1 | `dfe3c3f87815947d99a8997f908cb6525fc44e9e` |
| azure/setup-helm | v5.0.1 | `9bc31f4ebc9c6b171d7bfbaa5d006ae7abdb4310` |

CI pins Helm CLI `v3.22.1` (current Helm 3 stable; Helm 4.3.1 also exists and was not used). CI pins Terraform `1.17.0`. EKS variable default `1.34` was listed under Amazon EKS standard support on the AWS Kubernetes versions page that day. Re-check before any apply.

## Integration contracts

Unchanged from the product requirements and implemented as follows.

- Listen on port 8000. Metrics at `GET /metrics`. API under `/api/v1`.
- `GET /health/live` has no dependency. `GET /health/ready` checks SQLite and migrated tables.
- Configuration is environment variables. No secret is required for the basic app.
- Compose service `app` is scraped at `app:8000`. Kubernetes Service port and target port are 8000, port name `http`.
- One replica while SQLite is on one volume.
- Argo CD chart path is `deploy/helm/self-healing-platform`. Sync is manual. Repository URL must replace `REPLACE_OWNER`.
- Release tags are commit SHAs, plus a `v*` git tag when the workflow runs on a tag. Not `latest`.

## Phase status

| Phase | Result |
|---|---|
| 1 Plan | This document |
| 2–3 Application, analysis, remediation, tests | Implemented and pytest-green locally |
| 4 Docker Compose | Image tags and Compose file written. Runtime result is in `docs/TEST_RESULTS.md` |
| 5 CI and security | Workflows written. `pip-audit` and `bandit` run locally. Trivy not installed here |
| 6 Helm | `helm lint` and `helm template` passed with Helm 3.22.1. Cluster deploy not run |
| 7 Observability | `promtool` accepted rules and both scrape configs. Live scrape depends on Compose |
| 8 Argo CD | Manifest validated as YAML. Reconciliation not run |
| 9 Terraform | `fmt`, `init -backend=false`, and `validate` passed. No plan or apply |
| 10–11 Verification and docs | Local API, migration, restart persistence, and the demo script were executed |

## Deliberately not done

- `terraform apply` or `destroy`
- Publishing an image
- Claiming a cluster rollout, Argo CD sync, or Grafana screenshot that was not produced
