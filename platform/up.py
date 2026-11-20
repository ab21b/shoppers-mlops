"""Платформа в kind одной командой: кластер с портом 80, Traefik, MLflow, metrics-server.

    uv run python platform/up.py                  # кластер mlops
    uv run python platform/up.py --cluster other  # другое имя (то же имя нужно в ci.yml, KIND_CLUSTER)
    uv run python platform/up.py --delete         # снести кластер

Повторный запуск безопасен: что уже стоит, только обновится. Нужны: docker, kind, kubectl, helm.
Python-скрипт, а не bash, чтобы одинаково работал на Windows и macOS/Linux.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TRAEFIK_CHART = "41.6.0"
METRICS_SERVER_CHART = "3.14.0"


def run(*cmd: str, check: bool = True, capture: bool = False) -> str:
    print(f"\n$ {' '.join(cmd)}", flush=True)
    res = subprocess.run(cmd, cwd=ROOT, text=True, capture_output=capture, check=False)
    if check and res.returncode != 0:
        if capture:
            print(res.stdout, res.stderr, sep="\n")
        sys.exit(f"команда упала с кодом {res.returncode}: {' '.join(cmd)}")
    return res.stdout if capture else ""


def check_mlflow(timeout: int = 90) -> bool:
    """Ходим на 127.0.0.1:80 с заголовком Host: так проверка не зависит от того, как ОС резолвит *.localhost."""
    import time

    req = urllib.request.Request("http://127.0.0.1/health", headers={"Host": "mlflow.localhost"})
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(req, timeout=3) as r:
                if r.status == 200:
                    return True
        except (urllib.error.URLError, OSError):
            pass
        time.sleep(2)
    return False


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cluster", default="mlops")
    ap.add_argument("--delete", action="store_true")
    args = ap.parse_args()
    ctx = f"kind-{args.cluster}"

    for tool in ("docker", "kind", "kubectl", "helm"):
        if shutil.which(tool) is None:
            sys.exit(f"не найден `{tool}` в PATH (см. README.md, раздел «Установка с нуля»)")

    if args.delete:
        run("kind", "delete", "cluster", "--name", args.cluster)
        return

    print(f"== кластер {args.cluster}")
    if args.cluster not in run("kind", "get", "clusters", capture=True).split():
        run("kind", "create", "cluster", "--name", args.cluster, "--config", "platform/kind-config.yaml")

    print("== Traefik (Ingress-контроллер)")
    run("helm", "repo", "add", "traefik", "https://traefik.github.io/charts", check=False)
    run("helm", "repo", "add", "metrics-server", "https://kubernetes-sigs.github.io/metrics-server/", check=False)
    run("helm", "repo", "update")
    run("helm", "--kube-context", ctx, "upgrade", "--install", "traefik", "traefik/traefik", "--version", TRAEFIK_CHART,
        "-n", "traefik", "--create-namespace", "-f", "platform/traefik-values.yaml", "--wait")  # fmt: skip

    print("== MLflow и его Ingress")
    run("kubectl", "--context", ctx, "apply", "-f", "platform/mlflow.yaml")
    run("kubectl", "--context", ctx, "apply", "-f", "platform/ingress.yaml")

    print("== metrics-server (нужен HPA и kubectl top)")
    run("helm", "--kube-context", ctx, "upgrade", "--install", "metrics-server", "metrics-server/metrics-server",
        "--version", METRICS_SERVER_CHART, "-n", "kube-system",
        "-f", "platform/metrics-server-values.yaml", "--wait")  # fmt: skip

    run("kubectl", "--context", ctx, "-n", "mlops", "rollout", "status", "deploy/mlflow", "--timeout=10m")
    run("kubectl", "--context", ctx, "get", "pods,ingress", "-A")

    print("\n== проверка входа")
    if check_mlflow():
        print("MLflow отвечает через Ingress: откройте http://mlflow.localhost")
    else:
        print("MLflow пока не ответил на 127.0.0.1:80. Подождите минуту и откройте http://mlflow.localhost;"
              " если не откроется, смотрите README.md, раздел «Если что-то не работает».")  # fmt: skip


if __name__ == "__main__":
    main()
