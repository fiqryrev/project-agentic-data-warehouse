"""check_duckdb_compat: pins agree, readers must see the same file."""
import json
import subprocess
import sys

import duckdb

from helpers import check_duckdb_compat as c

PINS = {"loader": ">=1.5.5,<1.6",
        "readers": {"dbt": {"version": duckdb.__version__, "mode": "rw"},
                    "auto_ontology": {"version": duckdb.__version__, "mode": "ro"}}}


def local_runner(version, db, mode):
    """The probe with this environment's DuckDB: no download needed in tests."""
    out = subprocess.run([sys.executable, "-c", c.PROBE, db, mode], check=True,
                         capture_output=True, text=True).stdout
    return json.loads(out.strip().splitlines()[-1])


def test_repo_pins_match_pyproject():
    assert c.pyproject_duckdb_spec() == c.load_pins()["loader"]
    assert set(c.load_pins()["readers"]) == {"dbt", "auto_ontology"}


def test_passes_with_a_reader_that_sees_the_file(tmp_path):
    assert c.check(PINS, runner=local_runner, workdir=tmp_path, loader_spec=">=1.5.5,<1.6") == []


def test_pin_drift_fails(tmp_path):
    errors = c.check(PINS, runner=local_runner, workdir=tmp_path, loader_spec=">=1.6")
    assert any("keep them equal" in e for e in errors)


def test_reader_that_cannot_open_fails(tmp_path):
    def broken(version, db, mode):
        raise RuntimeError("IO Error: file was written by a newer version")
    errors = c.check(PINS, runner=broken, workdir=tmp_path, loader_spec=">=1.5.5,<1.6")
    assert len(errors) == 2 and all("could not open" in e for e in errors)


def test_reader_seeing_other_rows_or_no_comments_fails(tmp_path):
    def wrong(version, db, mode):
        seen = local_runner(version, db, mode)
        seen["rows"]["shop__orders"] += 1
        seen["comment"] = None
        return seen
    errors = c.check(PINS, runner=wrong, workdir=tmp_path, loader_spec=">=1.5.5,<1.6")
    assert any("different lake row counts" in e for e in errors)
    assert any("column comments" in e for e in errors)
