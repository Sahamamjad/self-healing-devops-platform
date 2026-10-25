# Security

## Threat model

The service is a local demonstration API. Operators send incident evidence that may include logs, tokens, or text that tries to instruct the analyser. The trust boundary is the HTTP request. Evidence is untrusted. Optional AI output is also untrusted and is never executed.

In scope:

- Unauthorized use of demo failure or remediation.
- Secret leakage in API responses, logs, metrics, or an AI request.
- Command injection disguised as a remediation action.
- Oversized payloads.
- Excessive container and workflow permissions.

Out of scope for the default build:

- Mutating a live Kubernetes cluster. The adapter is not implemented, and setting `KUBERNETES_REMEDIATION_ENABLED=true` rejects the call.
- Multi-tenant authentication. Remediation and demo failure use shared tokens when those features are turned on. There is no end-user identity system.
- Protection against a person who can already change environment variables or the SQLite file on the host.

## Secrets

No secret is required to boot. `.env` is gitignored. Compose does not embed a production credential. `GRAFANA_ADMIN_PASSWORD` defaults to `local-demo-change-me` for a workstation only. Change it before any shared deployment. Anonymous Grafana access is Viewer, with sign-up disabled.

Demo and remediation tokens are compared with `hmac.compare_digest`. They are not written to `/api/v1/status`.

Redaction before storage and before any AI call covers `Authorization: Bearer` values, `bearer` tokens, `token` / `password` / `api_key` assignments, AWS access-key IDs shaped `AKIA...`, and PEM private-key headers. Redaction is best-effort. It is not a complete secret scanner.

## Permissions

- Container user `10001`, `allowPrivilegeEscalation: false`, all capabilities dropped, `RuntimeDefault` seccomp, read-only root filesystem on Kubernetes, writable `/data` and `/tmp` only.
- Service account token automount is off. The pod does not need the Kubernetes API.
- GitHub Actions CI and security jobs use `contents: read`. The release job adds `packages: write` and runs only for `v*` tags or a manual dispatch on `main`. It does not run on pull requests.
- Terraform node and cluster roles attach the AWS managed EKS policies required to run a node, plus a flow-log role that can write one log group. There is no `AdministratorAccess` policy in the stack.
- The public EKS endpoint is off by default. Opening it requires an explicit variable and forbids `0.0.0.0/0` in `authorized_cidrs`.

## Network exposure

Compose publishes `8000`, `9090`, and `3000` on the host. That is for a local demo. Do not expose those ports on a shared network without replacing the Grafana password and putting a real authenticator in front of the API.

The NetworkPolicy allows ingress to TCP 8000 from any source and egress to DNS only. It does nothing until the cluster CNI enforces NetworkPolicy. AI summaries would need extra egress if you enable them inside that policy.

## AI data handling

`AI_SUMMARIES_ENABLED` defaults to false. When enabled, the URL must be `https`, redirects are not followed, and the JSON body is the redacted analysis. The bearer token is sent only to that URL and is not copied into the stored summary. The stored object sets `execution_authority` to false. A failed or skipped summary does not change the rule result.

## Remediation controls

Allowed actions: `simulate_clear_demo_failure` and `simulate_restart_application`. `none` and anything containing shell metacharacters are rejected. `simulate_restart_application` records a note. It does not restart a process. `simulate_clear_demo_failure` clears the in-memory demo flag only when dry-run is disabled, remediation is enabled, and the incident has reached `Approved`.

Default `REMEDIATION_DRY_RUN_ONLY=true` forces the audit to stay a dry-run. Dry-run does not clear the demo flag.

## Known risks

- Shared demo and remediation tokens are not user-bound. Anyone who has the token can call those routes.
- Redaction can miss secrets that do not match the patterns.
- Grafana's local default password is guessable. It is a placeholder.
- `pip-audit` does not audit this project name on PyPI because the package is not published. Third-party dependencies were audited; see `docs/TEST_RESULTS.md`.
- Trivy was not installed on this workstation, so no local container or misconfiguration scan result is claimed. The security workflow runs Trivy and fails on critical or high findings.
- Image tags are not digest-pinned.
- SQLite files under `data/` are local application data. Do not commit them. They are gitignored.
