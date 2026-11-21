#!/usr/bin/env python3
"""check_gateway_only: every model call goes through the LiteLLM gateway (PLAN section 8.1).

No tracked file names a model provider's API host or a provider key variable, except:
- `infra/llm-gateway/` and `.env.example`, where the gateway is configured;
- DESIGN_RECORDS, which show the gateway config as a design example (PLAN, M0 findings);
- this checker (it holds the vocabulary) and `tests/governance/` (bad fixtures).
Code that wants a model calls the gateway with a virtual key instead.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

try:
    from helpers.govlib import REPO, report, tracked_files
except ModuleNotFoundError:
    from govlib import REPO, report, tracked_files  # type: ignore

NAME = "check_gateway_only"
GATEWAY_PATHS = ("infra/llm-gateway/", ".env.example")
DESIGN_RECORDS = ("PLAN.md", "docs/m0-findings.md")
CHECKER_PATHS = ("helpers/check_gateway_only.py", "tests/governance/")
ALLOWED = GATEWAY_PATHS + DESIGN_RECORDS + CHECKER_PATHS

PROVIDER_HOSTS = (
    r"api\.openai\.com", r"openrouter\.ai", r"api\.anthropic\.com",
    r"integrate\.api\.nvidia\.com", r"ai\.api\.nvidia\.com", r"api\.nvcf\.nvidia\.com",
    r"generativelanguage\.googleapis\.com", r"aiplatform\.googleapis\.com",
    r"api\.groq\.com", r"api\.mistral\.ai", r"api\.together\.(?:xyz|ai)",
    r"api\.deepseek\.com", r"api\.cohere\.(?:ai|com)", r"api\.fireworks\.ai",
    r"[a-z0-9-]+\.openai\.azure\.com", r"bedrock-runtime\.[a-z0-9-]+\.amazonaws\.com",
)
PROVIDER_KEYS = (
    "OPENAI", "OPENROUTER", "ANTHROPIC", "NVIDIA", "NVIDIA_NIM", "NGC", "GEMINI", "GOOGLE",
    "GROQ", "MISTRAL", "TOGETHER", "TOGETHERAI", "DEEPSEEK", "COHERE", "FIREWORKS",
    "AZURE_OPENAI", "AZURE",
)
HOST_RE = re.compile(r"(?<![a-z0-9.-])(?:" + "|".join(PROVIDER_HOSTS) + r")", re.I)
KEY_RE = re.compile(r"\b(?:" + "|".join(PROVIDER_KEYS) + r")_API_KEY\b")


def allowed(path: str) -> bool:
    return any(path == a or (a.endswith("/") and path.startswith(a)) for a in ALLOWED)


def scan_text(text: str) -> list[str]:
    found = []
    for i, line in enumerate(text.splitlines(), 1):
        for m in HOST_RE.finditer(line):
            found.append(f"line {i}: provider host {m.group(0)}")
        for m in KEY_RE.finditer(line):
            found.append(f"line {i}: provider key name {m.group(0)}")
    return found


def check(paths: list[str], root: Path = REPO) -> list[str]:
    errors = []
    for rel in paths:
        if allowed(rel):
            continue
        path = root / rel
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        errors += [f"{rel} {hit}; call the gateway instead (infra/llm-gateway/)"
                   for hit in scan_text(text)]
    return errors


def main() -> int:
    return report(NAME, check(tracked_files()))


if __name__ == "__main__":
    sys.exit(main())
