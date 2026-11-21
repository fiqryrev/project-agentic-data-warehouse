#!/usr/bin/env python3
"""check_harness_parity: every wired agent tool declares all six duties and reaches every skill.

The duty list comes from `.agents/harnesses.yaml` itself (`duties:`), and must be the six
from PLAN section 9: entry, rules, skills, hooks, permissions, mcp. For each harness, each
duty is either a mapping the checker can verify or `{none: <reason>}`.

    entry:       {file, imports}        file exists and imports the shared entry (@AGENTS.md)
    rules:       {path, via}            folder of rule files, referenced from the `via` file
    skills:      {path, source}         every <source>/<skill>/SKILL.md resolves under <path>
    hooks:       {settings, scripts}    each script exists and is wired in the settings file
    permissions: {settings}             settings file has deny, ask and allow lists
    mcp:         {config}               a JSON file with an `mcpServers` mapping
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import yaml

try:
    from helpers.govlib import REPO, report
except ModuleNotFoundError:
    from govlib import REPO, report  # type: ignore

NAME = "check_harness_parity"
REGISTRY = Path(".agents") / "harnesses.yaml"
EXPECTED_DUTIES = ["entry", "rules", "skills", "hooks", "permissions", "mcp"]


def _settings(root: Path, rel: str, where: str, errors: list[str]) -> dict | None:
    p = root / rel
    if not p.is_file():
        errors.append(f"{where}: settings file {rel} not found")
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        errors.append(f"{where}: {rel} is not valid JSON ({exc})")
        return None


def skills_in(source: Path) -> list[str]:
    return sorted(p.parent.name for p in source.glob("*/SKILL.md"))


def check_duty(root: Path, harness: str, duty: str, spec, errors: list[str]) -> None:
    where = f"{harness}.{duty}"
    if not isinstance(spec, dict):
        errors.append(f"{where}: must be a mapping (or {{none: <reason>}})")
        return
    if "none" in spec:
        if not str(spec["none"] or "").strip():
            errors.append(f"{where}: 'none' needs a reason")
        return
    if duty == "entry":
        f, imp = root / str(spec.get("file", "")), str(spec.get("imports", ""))
        if not f.is_file():
            errors.append(f"{where}: entry file {spec.get('file')} not found")
        elif not (root / imp).is_file():
            errors.append(f"{where}: imported file {imp} not found")
        elif f"@{imp}" not in f.read_text(encoding="utf-8"):
            errors.append(f"{where}: {spec['file']} does not import @{imp}")
    elif duty == "rules":
        path, via = root / str(spec.get("path", "")), root / str(spec.get("via", ""))
        if not path.is_dir() or not list(path.glob("*.md")):
            errors.append(f"{where}: rules folder {spec.get('path')} missing or empty")
        if not via.is_file() or str(spec.get("path")) not in via.read_text(encoding="utf-8"):
            errors.append(f"{where}: {spec.get('via')} must point to {spec.get('path')}")
    elif duty == "skills":
        path, source = root / str(spec.get("path", "")), root / str(spec.get("source", ""))
        if not source.is_dir():
            errors.append(f"{where}: skill source {spec.get('source')} not found")
            return
        names = skills_in(source)
        if not names:
            errors.append(f"{where}: no skills under {spec.get('source')}")
        for name in names:
            if not (path / name / "SKILL.md").is_file():
                errors.append(f"{where}: skill '{name}' is not reachable from {spec.get('path')}")
            text = (source / name / "SKILL.md").read_text(encoding="utf-8")
            if not text.startswith("---") or f"name: {name}" not in text.split("---")[1]:
                errors.append(f"{where}: skill '{name}' needs frontmatter with name: {name}")
    elif duty == "hooks":
        settings = _settings(root, str(spec.get("settings", "")), where, errors)
        scripts = spec.get("scripts") or []
        if not scripts:
            errors.append(f"{where}: list the hook scripts under 'scripts'")
        wired = json.dumps((settings or {}).get("hooks") or {})
        for s in scripts:
            if not (root / s).is_file():
                errors.append(f"{where}: hook script {s} not found")
            if settings is not None and s not in wired:
                errors.append(f"{where}: hook script {s} is not wired in {spec.get('settings')}")
    elif duty == "permissions":
        settings = _settings(root, str(spec.get("settings", "")), where, errors)
        perms = (settings or {}).get("permissions") or {}
        if settings is not None:
            for key in ("deny", "ask", "allow"):
                if not isinstance(perms.get(key), list) or not perms.get(key):
                    errors.append(f"{where}: permissions.{key} must be a non-empty list")
    elif duty == "mcp":
        cfg = _settings(root, str(spec.get("config", "")), where, errors)
        if cfg is not None and not isinstance(cfg.get("mcpServers"), dict):
            errors.append(f"{where}: {spec.get('config')} needs an mcpServers mapping")


def check(root: Path = REPO) -> list[str]:
    reg_path = root / REGISTRY
    if not reg_path.is_file():
        return [f"{REGISTRY} not found"]
    reg = yaml.safe_load(reg_path.read_text(encoding="utf-8")) or {}
    errors: list[str] = []
    duties = reg.get("duties")
    if duties != EXPECTED_DUTIES:
        errors.append(f"duties must be {EXPECTED_DUTIES}, got {duties}")
        duties = EXPECTED_DUTIES
    harnesses = reg.get("harnesses")
    if not isinstance(harnesses, dict) or not harnesses:
        return errors + ["harnesses must list at least one wired tool"]
    for name, h in harnesses.items():
        if not isinstance(h, dict):
            errors.append(f"{name}: must be a mapping")
            continue
        declared = set(h) - {"name", "status"}
        for duty in duties:
            if duty not in h:
                errors.append(f"{name}: duty '{duty}' is not declared")
            else:
                check_duty(root, name, duty, h[duty], errors)
        for extra in sorted(declared - set(duties)):
            errors.append(f"{name}: '{extra}' is not one of the registry duties")
    return errors


def main() -> int:
    return report(NAME, check())


if __name__ == "__main__":
    sys.exit(main())
