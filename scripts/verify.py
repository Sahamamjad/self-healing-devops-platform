#!/usr/bin/env python3
"""Run the local verification checks that this machine can actually perform.

Prints PASS, FAIL, SKIPPED, or NOT RUN. Skipped checks are not successes.
Exit status is 1 when any executed check fails.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VENV_PY = ROOT / ".venv" / "bin" / "python"
RESULTS: list[tuple[str, str, str]] = []


def record(name: str, status: str, detail: str = "") -> None:
    RESULTS.append((name, status, detail.strip()))
    line = f"{status:8} {name}"
    if detail:
        line = f"{line} — {detail.splitlines()[-1][:180]}"
    print(line, flush=True)


def run(name: str, command: list[str], *, cwd: Path | None = None) -> None:
    binary = command[0]
    if shutil.which(binary) is None and not Path(binary).exists():
        record(name, "SKIPPED", f"{binary} is not installed")
        return
    completed = subprocess.run(command, cwd=cwd or ROOT, check=False, capture_output=True, text=True)
    if completed.returncode == 0:
        record(name, "PASS")
        return
    tail = (completed.stdout + "\n" + completed.stderr).strip()
    record(name, "FAIL", tail[-2000:])


def main() -> int:
    python = str(VENV_PY if VENV_PY.exists() else sys.executable)
    if not VENV_PY.exists():
        record("venv", "SKIPPED", "Run make install before the full suite")
    else:
        record("venv", "PASS", python)

    run("ruff check", [python, "-m", "ruff", "check", "src", "tests"])
    run("ruff format", [python, "-m", "ruff", "format", "--check", "src", "tests"])
    run("bandit", [python, "-m", "bandit", "-r", "src", "-c", "pyproject.toml", "-q"])
    run(
        "pytest",
        [python, "-m", "pytest", "--cov=self_healing_platform", "--cov-report=term-missing"],
    )

    if shutil.which("docker") is None:
        record("docker compose config", "SKIPPED", "docker is not installed")
        record("docker build", "NOT RUN", "docker is not installed")
    else:
        info = subprocess.run(["docker", "info"], check=False, capture_output=True, text=True)
        if info.returncode != 0:
            record("docker compose config", "SKIPPED", "docker CLI exists but the daemon is not running")
            record("docker build", "NOT RUN", "docker daemon is not running")
            record("compose stack", "NOT RUN", "docker daemon is not running")
        else:
            run("docker compose config", ["docker", "compose", "config", "--quiet"])
            record("docker build", "NOT RUN", "use make compose-up; this script does not build images")
            record("compose stack", "NOT RUN", "start with make compose-up, then make smoke")

    if shutil.which("helm") is None:
        record("helm lint", "SKIPPED", "helm is not installed")
    else:
        run("helm lint", ["helm", "lint", "deploy/helm/self-healing-platform"])

    if shutil.which("terraform") is None:
        record("terraform fmt", "SKIPPED", "terraform is not installed")
        record("terraform validate", "SKIPPED", "terraform is not installed")
    else:
        tf = ROOT / "terraform" / "aws"
        run("terraform fmt", ["terraform", "fmt", "-check", "-recursive"], cwd=tf)
        run("terraform init", ["terraform", "init", "-backend=false", "-input=false"], cwd=tf)
        run("terraform validate", ["terraform", "validate"], cwd=tf)

    if shutil.which("promtool") is None:
        record("promtool", "SKIPPED", "promtool is not installed")
    else:
        run(
            "promtool check config",
            ["promtool", "check", "config", "deploy/monitoring/prometheus/prometheus.compose.yml"],
        )
        run("promtool check rules", ["promtool", "check", "rules", "deploy/monitoring/prometheus/rules.yml"])

    if shutil.which("kubectl") is None:
        record("kubernetes cluster", "SKIPPED", "kubectl is not installed")
    else:
        cluster = subprocess.run(["kubectl", "cluster-info"], check=False, capture_output=True, text=True)
        if cluster.returncode != 0:
            record("kubernetes rollout", "NOT RUN", "no reachable cluster")
        else:
            record("kubernetes rollout", "NOT RUN", "cluster exists; this script does not deploy")

    record("aws apply", "NOT RUN", "cloud provisioning is not executed by this script")
    record("argo cd reconcile", "NOT RUN", "requires a cluster and a real Git remote")

    print("\nSummary")
    for name, status, _detail in RESULTS:
        print(f"  {status:8} {name}")
    failed = [name for name, status, _detail in RESULTS if status == "FAIL"]
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
