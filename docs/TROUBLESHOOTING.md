# Troubleshooting

Commands assume the repository root. On macOS this folder's name may end with a space (`self healing `). A sibling folder without the space is an older copy and is not this git repository. Use the folder that contains this file and `.git`.

## Startup

`alembic upgrade head` before the first local run. Readiness returns HTTP 503 `schema_missing` until that migration has been applied.

`APP_ENV` must be `development`, `demo`, or `production`. Other values fail at startup.

Port 8000 already in use: stop the other process or set `PORT`.

Python.org macOS builds sometimes lack a CA bundle. `pip` then fails TLS. Point `SSL_CERT_FILE` and `PIP_CERT` at `/etc/ssl/cert.pem`. Do not pass `--trusted-host` or disable verification.

## Docker

`Cannot connect to the Docker daemon`: start Docker Desktop and wait until `docker info` works. The CLI can be installed while the daemon is stopped.

Compose app volume is not writable: the `volume-init` service must finish first. It chowns `/data` to uid `10001`. If you run the image with `docker run` and a bind mount, the mount must be writable by uid `10001`.

`docker compose up` fails on the Grafana password: export `GRAFANA_ADMIN_PASSWORD` or accept the local default in `compose.yaml`.

Prometheus or Grafana crash-loop on a volume: the init container must have chowned `/prometheus` to `65534` and `/grafana` to `472`. Those ids match the Prometheus 3.15.1 image user `nobody` and the Grafana 13.2.4 `GF_UID`.

Healthcheck uses `python` inside the app image. It is not a shell `curl` check. Do not replace it with a binary the image does not contain.

## Database

`database_unavailable`: the SQLite parent directory is missing or not writable. Local default directory is `./data`.

`schema_missing`: tables were not created. `create_all` is for tests. Operators use Alembic.

Two processes writing one SQLite file can return `database is locked`. Run one replica.

The container database path has four slashes: `sqlite+pysqlite:////data/app.sqlite` (absolute `/data/app.sqlite`). Three slashes is a relative path.

## Kubernetes and Helm

`helm template` succeeds and a cluster rollout was not performed when no kube context exists. `kubectl` pointing at `localhost:8080` and getting connection refused means there is no local API server.

`replicaCount` greater than 1 with persistence enabled fails the template on purpose.

Image pull errors on a remote cluster: the chart default repository `ghcr.io/example/self-healing-devops-platform` is a placeholder. Load a local image or set `image.repository` and an immutable tag.

Readiness 503 in a pod: the entrypoint migrates on boot. If the volume is not writable by uid `10001`, migration fails and the pod restarts. `fsGroup: 10001` is what makes a new PVC writable.

NetworkPolicy blocks scrapes only when the CNI enforces policies. If probes work but Prometheus cannot scrape, check that ingress to port 8000 is allowed from the scraper namespace.

## Argo CD

Application status Unknown or ComparisonError: `repoURL` still contains `REPLACE_OWNER`, or the repository is private and Argo CD has no credential. The chart path `deploy/helm/self-healing-platform` must exist on `targetRevision`.

Sync does nothing until you sync manually. That is the default. Automated sync is only in the example manifest.

OutOfSync after an edit in the cluster, with self-heal off: expected. Sync again or revert the live edit. Turning on self-heal makes Argo CD revert the live edit to Git. Turning on prune deletes objects that are not in Git.

## Monitoring

Prometheus target down in Compose: the app healthcheck must pass before Prometheus starts, and the target host is `app`, not `localhost`.

Grafana has no data: pick datasource UID `prometheus` and a time range after the app received traffic. Idle histograms are empty. That is not a broken dashboard.

Alert rules reference `job="self-healing-app"`. A differently named scrape job will not match `ServiceUnavailable`.

`promtool check config` on the Compose file from a laptop fails if `rule_files` still says `/etc/prometheus/rules.yml`, because that path exists in the container, not on the laptop. Check rules with `promtool check rules deploy/monitoring/prometheus/rules.yml`. Inside the container the absolute path is correct.

## Tests

`pytest` skips Helm and Terraform when those binaries are not on `PATH`. Skips are not passes. `scripts/verify.py` prints `SKIPPED` or `NOT RUN` for the same reason.

Demo failure tests need the demo fixtures. The default client must receive HTTP 404 from `POST /api/v1/demo/failure`.
