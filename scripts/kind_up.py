"""Команда №3 из README: весь путь до модели в kind-кластере одной командой.

    uv run python scripts/kind_up.py            # сборка -> kind -> apply -> rollout -> ответ модели через port-forward
    uv run python scripts/kind_up.py --keep     # то же, но port-forward остаётся открытым (для curl и k9s)
    uv run python scripts/kind_up.py --delete   # снести кластер

Нужны: docker, kind, kubectl. Python-скрипт, а не bash, чтобы одинаково работало на Windows и macOS/Linux.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CLUSTER = "mlpro"
CONTEXT = f"kind-{CLUSTER}"
IMAGE = "shoppers-service:1.0"
DEPLOY = "deploy/shoppers-service"
LOCAL_PORT = 8080


def run(*cmd: str, capture: bool = False) -> str:
    print(f"\n$ {' '.join(cmd)}", flush=True)
    res = subprocess.run(cmd, cwd=ROOT, text=True, capture_output=capture, check=False)
    if res.returncode != 0:
        if capture:
            print(res.stdout, res.stderr, sep="\n")
        sys.exit(f"команда упала с кодом {res.returncode}: {' '.join(cmd)}")
    return res.stdout if capture else ""


def kubectl(*args: str, capture: bool = False) -> str:
    return run("kubectl", "--context", CONTEXT, *args, capture=capture)


def wait_ready(url: str, timeout: float = 60) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2) as r:
                if r.status == 200:
                    return
        except (urllib.error.URLError, OSError):
            time.sleep(1)
    sys.exit(f"port-forward не поднялся за {timeout:.0f} с: {url}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--keep", action="store_true", help="оставить port-forward открытым до Ctrl+C")
    ap.add_argument("--delete", action="store_true", help="удалить кластер и выйти")
    args = ap.parse_args()

    for tool in ("docker", "kind", "kubectl"):
        if shutil.which(tool) is None:
            sys.exit(f"не найден `{tool}` в PATH. Установите его (см. REPORT.md, раздел «Что нужно установить»)")

    if args.delete:
        run("kind", "delete", "cluster", "--name", CLUSTER)
        return

    run("docker", "build", "-t", IMAGE, ".")

    existed = CLUSTER in run("kind", "get", "clusters", capture=True).split()
    if not existed:
        run("kind", "create", "cluster", "--name", CLUSTER)
    run("kind", "load", "docker-image", IMAGE, "--name", CLUSTER)  # без этого будет ImagePullBackOff

    kubectl("apply", "-f", "k8s/")
    if existed:  # тот же тег 1.0, но образ мог измениться: заставим поды подхватить его
        kubectl("rollout", "restart", DEPLOY)
    kubectl("rollout", "status", DEPLOY, "--timeout=180s")
    kubectl("get", "pods", "-o", "wide")

    print(f"\n$ kubectl port-forward svc/shoppers-service {LOCAL_PORT}:80", flush=True)
    pf = subprocess.Popen(["kubectl", "--context", CONTEXT, "port-forward", "svc/shoppers-service", f"{LOCAL_PORT}:80"],
                          cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)  # fmt: skip
    try:
        base = f"http://127.0.0.1:{LOCAL_PORT}"
        wait_ready(f"{base}/ready")
        body = (ROOT / "good.json").read_bytes()
        req = urllib.request.Request(f"{base}/v1/predict", data=body, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=10) as r:
            print(f"\nPOST {base}/v1/predict -> HTTP {r.status}")
            print(json.dumps(json.loads(r.read()), indent=2, ensure_ascii=False))
        if args.keep:
            print(f"\nport-forward открыт: {base}/docs   (Ctrl+C - остановить). Сейчас самое время для скрина k9s.")
            pf.wait()
    except KeyboardInterrupt:
        pass
    finally:
        pf.terminate()


if __name__ == "__main__":
    main()
