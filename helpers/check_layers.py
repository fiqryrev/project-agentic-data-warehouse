#!/usr/bin/env python3
"""check_layers: lineage only flows downward (PLAN section 4).

- staging reads exactly one `source('lake', '<source>__<table>')`, the lake table its own name
  points at (staging is 1:1 with a lake table), declared in the project's sources, and no ref;
- warehouse refs staging and warehouse models only, and reads no source;
- mart refs warehouse and mart models only, and reads no source;
- every ref names a model that exists.
"""
from __future__ import annotations

import sys
from pathlib import Path

try:
    from helpers import dbtlib
    from helpers.govlib import report
except ModuleNotFoundError:
    import dbtlib  # type: ignore
    from govlib import report  # type: ignore

NAME = "check_layers"
MAY_REF = {"staging": (), "warehouse": ("staging", "warehouse"), "mart": ("warehouse", "mart")}


def check(models: list[dbtlib.Model], sources: dict[str, set[str]]) -> list[str]:
    layer_of = {m.name: m.layer for m in models}
    errors = []
    for m in models:
        where = str(m.path)
        if m.layer not in MAY_REF:
            errors.append(f"{where}: not under a layer folder ({', '.join(MAY_REF)})")
            continue
        for ref in m.refs:
            if ref not in layer_of:
                errors.append(f"{where}: ref('{ref}') names no model")
            elif layer_of[ref] not in MAY_REF[m.layer]:
                allowed = " and ".join(MAY_REF[m.layer]) or "no model (only the lake)"
                errors.append(f"{where}: {m.layer} reads {layer_of[ref]} model '{ref}'; "
                              f"{m.layer} may read {allowed}")
        if m.layer == "staging":
            expected = ("lake", m.name.removeprefix("staging__"))
            if m.sources != [expected]:
                errors.append(f"{where}: staging reads exactly source('lake', '{expected[1]}'); "
                              f"found {m.sources or 'none'}")
            for src, table in m.sources:
                if table not in sources.get(src, set()):
                    errors.append(f"{where}: source('{src}', '{table}') is not declared in "
                                  f"models/staging/_sources.yml")
        elif m.sources:
            errors.append(f"{where}: {m.layer} reads sources {m.sources}; only staging reads the lake")
    return errors


def main(argv: list[str] | None = None) -> int:
    project = Path(argv[0]) if argv else dbtlib.DBT_DIR
    return report(NAME, check(dbtlib.load_models(project), dbtlib.load_sources(project)))


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
