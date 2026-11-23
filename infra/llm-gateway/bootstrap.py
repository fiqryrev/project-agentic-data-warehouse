"""Gateway bootstrap: provider keys present, one virtual key per caller (budgets.yaml).

    uv run python infra/llm-gateway/bootstrap.py check-keys     # before `docker compose up`
    uv run python infra/llm-gateway/bootstrap.py keys           # after the gateway is healthy

`keys` is idempotent: a caller whose key in .env still works gets its budget, models and tags
updated; a caller without a working key gets a new one, written to .env. Prints key aliases and
budgets only, never key values. Needs only the standard library and PyYAML.
"""
from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO))       # run as a script; helpers/ is at the repository root
from helpers import envfile  # noqa: E402

BUDGETS = HERE / "budgets.yaml"
GATEWAY = "http://127.0.0.1:4000"
PROVIDER_KEYS = ("NVIDIA_API_KEY", "OPENROUTER_API_KEY")


def read_env(path: Path) -> dict[str, str]:
    """The file only: `check-keys` and `keys` run on the host against `.env` itself."""
    return envfile.read_file(path)


def set_env(path: Path, key: str, value: str) -> None:
    envfile.set_key(path, key, value)


def key_request(caller: dict, duration: str) -> dict:
    """The /key/generate and /key/update body for a caller in budgets.yaml."""
    return {
        "key_alias": caller["name"],
        "max_budget": float(caller["max_budget_usd"]),
        "budget_duration": duration,
        "models": list(caller["models"]),
        "metadata": {"tags": [f"caller:{caller['name']}"]},
    }


def call(method: str, path: str, token: str, body: dict | None = None,
         base: str = GATEWAY) -> tuple[int, dict]:
    req = urllib.request.Request(base + path, method=method,
                                 data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Authorization": f"Bearer {token}",
                                          "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return resp.status, json.loads(resp.read() or b"{}")
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read() or b"{}")
        except ValueError:
            return e.code, {}


def master_key(env: dict[str, str]) -> str:
    secret = env.get("LITELLM_MASTER_SECRET")
    if not secret:
        sys.exit("[bootstrap] LITELLM_MASTER_SECRET is empty; run make up-obs")
    return f"sk-{secret}"


def check_keys(env_path: Path) -> int:
    env = read_env(env_path)
    missing = [k for k in PROVIDER_KEYS if not env.get(k)]
    if missing:
        print(f"[bootstrap] put {', '.join(missing)} in .env (gitignored) before make up-obs")
        return 1
    print(f"[bootstrap] provider keys present: {', '.join(PROVIDER_KEYS)}")
    return 0


def ensure_keys(env_path: Path, budgets_path: Path = BUDGETS, base: str = GATEWAY) -> int:
    env = read_env(env_path)
    master = master_key(env)
    cfg = yaml.safe_load(budgets_path.read_text(encoding="utf-8"))
    for caller in cfg["callers"]:
        body = key_request(caller, cfg["budget_duration"])
        existing = env.get(caller["env"], "")
        status = 0
        if existing:
            status, _ = call("POST", "/key/update", master, {"key": existing, **body}, base)
        if status == 200:
            action = "updated"
        else:
            status, out = call("POST", "/key/generate", master, body, base)
            if status != 200 or not out.get("key"):
                print(f"[bootstrap] {caller['name']}: key/generate failed ({status}): {out}")
                return 1
            set_env(env_path, caller["env"], out["key"])
            action = "created"
        print(f"[bootstrap] {caller['name']}: {action}, ${body['max_budget']:.2f} per "
              f"{cfg['budget_duration']}, models {', '.join(body['models'])}")
    return 0


def main(argv: list[str]) -> int:
    env_path = REPO / ".env"
    if argv[:1] == ["check-keys"]:
        return check_keys(env_path)
    if argv[:1] == ["keys"]:
        return ensure_keys(env_path)
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
