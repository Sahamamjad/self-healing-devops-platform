# Architecture

## Components

| Piece | Responsibility |
|---|---|
| `self_healing_platform` | HTTP API, configuration, logging, metrics |
| SQLAlchemy models + Alembic | Incident and remediation-audit persistence |
| Analysis engine | Deterministic rules. No network |
| Remediation policy | Allowlist, lifecycle checks, simulated actions |
| Optional AI helper | HTTPS summary only. No execution |
| Prometheus / Grafana | Scrape `/metrics`, dashboard, alert rules |
| Helm / raw manifests | One non-root replica and a SQLite volume |
| Argo CD Application | Manual sync of the Helm chart |
| Terraform `terraform/aws` | Optional VPC and EKS. Not applied by tests |

## Request flow

1. Middleware assigns `X-Request-ID`, rejects bodies over `MAX_REQUEST_BYTES`, and may apply an in-memory demo failure.
2. Routes validate input with Pydantic.
3. Incident analysis runs in-process, redacts evidence, and stores a row in one transaction.
4. `/metrics` records method, route template, and status. Raw URLs and request IDs are not labels.
5. Readiness runs `SELECT 1` and checks that `incidents` and `remediation_audits` exist. Liveness does not touch the database.

## Deployment flow

Local Python and Compose both use the same package. The container entrypoint runs `alembic upgrade head` and then execs Uvicorn so signals reach the server. Kubernetes `fsGroup: 10001` makes the SQLite volume writable by the non-root user. Compose uses a one-shot `busybox:1.37.0` init container to chown named volumes before the app (`10001`), Prometheus (`65534` / `nobody`), and Grafana (`472`) start.

Helm `fullname` is the chart name `self-healing-platform`, so the Service name matches `deploy/monitoring/prometheus/prometheus.kubernetes.yml`. Deploy one release in namespace `self-healing`. A second release in that namespace would collide.

Image tag `local` in `values-local.yaml` is only for `pullPolicy: Never` after a local `docker load`. Release workflow tags are `sha-<git-sha>` and, for a `v*` tag push, that version. They are not `latest`.

## Data persistence

`DATABASE_URL` is the backend switch. The tested implementation is SQLite through `sqlite+pysqlite`. Sessions are request-scoped, commit on success, and roll back on error. Schema changes go through Alembic in `migrations/`.

A future PostgreSQL URL such as `postgresql+psycopg://...` would need a driver and a new test run. That driver is not installed, and PostgreSQL is not claimed to work.

SQLite on one PVC with `strategy: Recreate` and `replicaCount: 1` keeps a single writer. It does not provide failover, concurrent writers, or multi-replica reads. The chart template fails if persistence is on and replicas are greater than 1.

Demo failure state is process memory. Restarting the process clears it. Incident rows remain in SQLite.

## Observability

Metrics:

| Name | Type | Labels |
|---|---|---|
| `http_requests_total` | counter | `method`, `route`, `status` |
| `http_request_duration_seconds` | histogram | `method`, `route` |
| `application_uptime_seconds` | gauge | none |
| `incident_analysis_total` | counter | `outcome` |
| `incident_analysis_duration_seconds` | histogram | none |
| `demo_failure_events_total` | counter | `mode` |

Compose scrape target: `app:8000`. Kubernetes scrape target: endpoints for Service `self-healing-platform` in namespace `self-healing`, port name `http`. Grafana provisioning in the Compose file uses `http://prometheus:9090` and must not be reused unchanged inside a cluster.

## Failure and recovery

| Mechanism | What it actually does |
|---|---|
| Demo failure | Returns 500 or 503, or adds latency, for a bounded request count. Does not touch probes, metrics, or remediation |
| Analysis | Classifies supplied evidence. Does not change infrastructure |
| Simulated remediation | Writes an audit row. `simulate_clear_demo_failure` can clear this process's demo flag when dry-run is off and the incident is Approved |
| kubelet restart | Restarts a container whose process exited. This app does not do that |
| Argo CD sync | Applies Git. Manual in the default Application. Not the same as this API |

Lifecycle: `Detected → Analysed → Proposed → Approved → Executed → Verified`, plus `Rejected`, `Failed`, and `Needs investigation`. Creation may start at `Proposed` or `Needs investigation` from the analysis result. Later invalid transitions return HTTP 409. Execution that is not a dry-run is refused unless the status is `Approved`, and by default `REMEDIATION_DRY_RUN_ONLY=true` forces a dry-run anyway.

## GitOps behaviour

Default Application (`deploy/argocd/application.yaml`):

- Manual sync. Nothing changes in the cluster until an operator syncs.
- No automated prune. Deleting a manifest from Git does not delete the cluster object.
- No self-heal. Cluster drift is left in place until the next manual sync.
- Empty finalizers. Deleting the Application object does not cascade-delete workloads.

`application-automated.example.yaml` turns on automated sync and self-heal, and leaves prune false. Self-heal reverts live edits (for example a manual replica change) to Git. Prune, if later set true, deletes cluster objects that are not in Git. That can remove a Service or PVC. Do not enable prune without a reviewed resource list.

## Optional AWS shape

The Terraform stack, if applied, would create:

- A VPC with two public subnets (NAT and internet gateway only) and two private subnets.
- One NAT gateway and its public IPv4 address.
- An EKS control plane. Private endpoint on. Public endpoint off unless `enable_cluster_public_endpoint=true` and `authorized_cidrs` is a non-empty list that is not `0.0.0.0/0`.
- One managed node in a private subnet (`t3.small` by default). That is not a highly available node group.
- A customer-managed KMS key for Kubernetes secret encryption, with rotation enabled.
- Control-plane logs to CloudWatch for 14 days, and reject-only VPC flow logs for 7 days.

Workers reach the internet through NAT so they can pull images. There is no public load balancer in this stack. `kubectl` from a laptop will not reach a private-only API.

Costs that start when someone runs apply include the EKS control plane (on the order of $0.10 per hour), NAT gateway hourly charge plus data processing, one EC2 node, EBS volumes, a public IPv4 address, and CloudWatch. Prices change. Confirm them in AWS before apply. This repository never runs apply or destroy.
