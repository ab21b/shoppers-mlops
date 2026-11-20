import argparse
import json
import time
import urllib.error
import urllib.request


def health(url: str, host: str) -> dict | None:
    req = urllib.request.Request(f"{url}/health", headers={"Host": host})
    try:
        with urllib.request.urlopen(req, timeout=2) as r:
            return json.loads(r.read())
    except (urllib.error.URLError, OSError, ValueError):
        return None


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--expect", required=True, help="ожидаемая версия, например shoppers-rf-v1")
    ap.add_argument("--url", default="http://127.0.0.1")
    ap.add_argument("--host", default="shoppers.localhost")
    ap.add_argument("--timeout", type=float, default=300)
    args = ap.parse_args()

    before = health(args.url, args.host)
    print("сейчас /health:", before)
    input("Нажмите Enter одновременно с кликом в MLflow UI")
    t0 = time.time()
    last = None
    while time.time() - t0 < args.timeout:
        h = health(args.url, args.host)
        version = h.get("model_version") if h else None
        if version != last:
            print(f"[{time.time() - t0:6.1f} с] /health: {h}")
            last = version
        if version == args.expect:
            print(f"\nОтвет версии {args.expect} получен через {time.time() - t0:.1f} с после клика")
            return
        time.sleep(0.5)
    print("таймаут: ожидаемая версия не появилась")


if __name__ == "__main__":
    main()
