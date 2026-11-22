"""Create Langfuse's score configs and the annotation queue from infra/langfuse/scores.yaml.

    uv run python infra/langfuse/bootstrap.py      # run by `make up-obs`, idempotent

Creates what is missing; a config that exists with other categories is reported, not changed
(Langfuse ties scores to the config id, so a change means a new name). Prints names only.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from llm.observe import Langfuse, read_env  # noqa: E402

SPEC = Path(__file__).with_name("scores.yaml")


def config_body(spec: dict) -> dict:
    body = {"name": spec["name"], "dataType": spec["dataType"], "description": spec.get("description")}
    if spec["dataType"] == "CATEGORICAL":
        body["categories"] = [{"label": str(c), "value": float(i)} for i, c in enumerate(spec["categories"])]
    return body


def drift(spec: dict, have: dict) -> str | None:
    if have.get("dataType") != spec["dataType"]:
        return f"dataType {have.get('dataType')} != {spec['dataType']}"
    if spec["dataType"] == "CATEGORICAL":
        labels = [c.get("label") for c in have.get("categories") or []]
        if labels != [str(c) for c in spec["categories"]]:
            return f"categories {labels} != {spec['categories']}"
    return None


def wait_ready(lf: Langfuse, timeout_s: int = 120) -> None:
    deadline = time.monotonic() + timeout_s
    while True:
        try:
            lf.call("GET", "/api/public/score-configs?limit=1")
            return
        except (RuntimeError, OSError):
            if time.monotonic() > deadline:
                raise
            time.sleep(5)


def main() -> int:
    spec = yaml.safe_load(SPEC.read_text(encoding="utf-8"))
    lf = Langfuse(read_env(REPO / ".env"))
    wait_ready(lf)
    have = lf.score_configs()
    problems = []
    for item in spec["automatic"] + spec["label_form"]:
        if item["name"] in have:
            if (d := drift(item, have[item["name"]])):
                problems.append(f"{item['name']}: {d}")
            continue
        have[item["name"]] = lf.call("POST", "/api/public/score-configs", config_body(item))
        print(f"[langfuse-bootstrap] score config {item['name']} created")
    q = spec["queue"]
    queues = {x.get("name"): x for x in lf.pages("/api/public/annotation-queues")}
    if q["name"] not in queues:
        lf.call("POST", "/api/public/annotation-queues", {
            "name": q["name"], "description": " ".join(q["description"].split()),
            "scoreConfigIds": [have[n]["id"] for n in q["score_configs"]]})
        print(f"[langfuse-bootstrap] annotation queue {q['name']} created")
    for p in problems:
        print(f"[langfuse-bootstrap] WARN {p} (left as it is)")
    print(f"[langfuse-bootstrap] ok: {len(spec['automatic']) + len(spec['label_form'])} score configs, "
          f"queue {q['name']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
