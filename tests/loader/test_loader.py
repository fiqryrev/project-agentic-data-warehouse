"""The lake loader: idempotent per date, audit columns, checksums and schema drift."""
import datetime as dt
import json
import shutil

import duckdb
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from generator.write import write_day
from loader.__main__ import main as cli
from loader.load import AUDIT_COLUMNS, LoadError, load_day, manifest_file, partition_file

D1, D2, D3 = dt.date(2026, 1, 1), dt.date(2026, 1, 2), dt.date(2026, 1, 3)


@pytest.fixture(scope="module")
def landing(tmp_path_factory):
    out = tmp_path_factory.mktemp("landing")
    for day in (D1, D2, D3):
        write_day(42, day, out)
    return out


@pytest.fixture
def con(tmp_path):
    c = duckdb.connect(str(tmp_path / "w.duckdb"))
    yield c
    c.close()


def counts(con):
    tables = con.execute("SELECT table_name FROM information_schema.tables "
                         "WHERE table_schema = 'lake' ORDER BY 1").fetchall()
    return {t: con.execute(f"SELECT _dt, count(*) FROM lake.{t} GROUP BY 1 ORDER BY 1").fetchall()
            for (t,) in tables}


def test_loading_a_day_twice_leaves_counts_unchanged(landing, con):
    """M3 done-when."""
    for day in (D1, D2, D3):
        load_day(con, landing, day)
    before = counts(con)
    load_day(con, landing, D2)
    load_day(con, landing, D2)
    assert counts(con) == before
    assert len(before) == 15


def test_counts_match_manifest(landing, con):
    got = load_day(con, landing, D2)
    manifest = json.loads(manifest_file(landing, D2).read_text())
    assert got == {f"lake.{k.replace('.', '__')}": v["rows"] for k, v in manifest["tables"].items()}


def test_audit_columns(landing, con):
    t0 = dt.datetime(2026, 1, 2, 3, 4, 5)
    load_day(con, landing, D2, loaded_at=t0)
    cols = [r[0] for r in con.execute("DESCRIBE lake.shop__orders").fetchall()]
    assert cols[-4:] == list(AUDIT_COLUMNS)
    row = con.execute("SELECT DISTINCT _dt, _source_file, _loaded_at, _batch_id "
                      "FROM lake.shop__orders").fetchall()
    assert len(row) == 1
    d, src, loaded, batch = row[0]
    assert d == D2 and src == "shop/orders/dt=2026-01-02/part-0.parquet" and loaded == t0
    assert batch.startswith("2026-01-02-") and len(batch) == len("2026-01-02-") + 12
    comment = con.execute("SELECT comment FROM duckdb_columns() WHERE table_name = 'shop__orders' "
                          "AND column_name = '_batch_id'").fetchone()[0]
    assert "manifest" in comment


def test_same_input_same_batch_id(landing, con):
    load_day(con, landing, D2)
    first = con.execute("SELECT DISTINCT _batch_id FROM lake.shop__orders").fetchall()
    load_day(con, landing, D2)
    assert con.execute("SELECT DISTINCT _batch_id FROM lake.shop__orders").fetchall() == first


def test_reload_touches_only_its_date(landing, con):
    load_day(con, landing, D1, loaded_at=dt.datetime(2026, 1, 1, 1))
    load_day(con, landing, D2, loaded_at=dt.datetime(2026, 1, 2, 1))
    load_day(con, landing, D2, loaded_at=dt.datetime(2026, 1, 9, 9))
    stamps = dict(con.execute("SELECT _dt, max(_loaded_at) FROM lake.shop__orders GROUP BY 1").fetchall())
    assert stamps[D1] == dt.datetime(2026, 1, 1, 1) and stamps[D2] == dt.datetime(2026, 1, 9, 9)


def test_late_rows_keep_the_partition_date(landing, con):
    load_day(con, landing, D3)
    late = con.execute("SELECT count(*) FROM lake.shop__orders "
                       "WHERE CAST(updated_at AS DATE) < _dt").fetchone()[0]
    assert late > 0


def test_checksum_mismatch_refuses_to_load(landing, con, tmp_path):
    bad = tmp_path / "bad"
    shutil.copytree(landing, bad)
    path = partition_file(bad, "shop", "orders", D2)
    rows = pq.read_table(path).slice(0, 5)
    pq.write_table(rows, path)
    with pytest.raises(LoadError, match="checksum"):
        load_day(con, bad, D2)
    assert con.execute("SELECT count(*) FROM information_schema.schemata "
                       "WHERE schema_name = 'lake'").fetchone()[0] == 0


def test_missing_manifest_fails(con, tmp_path):
    with pytest.raises(LoadError, match="no manifest"):
        load_day(con, tmp_path, D2)


def _rewrite(landing, day, table, transform):
    """Change a partition and fix the manifest, as a source with a new schema would."""
    path = partition_file(landing, "shop", table, day)
    pq.write_table(transform(pq.read_table(path)), path)
    mpath = manifest_file(landing, day)
    m = json.loads(mpath.read_text())
    import hashlib
    m["tables"][f"shop.{table}"]["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    m["tables"][f"shop.{table}"]["rows"] = pq.read_metadata(path).num_rows
    mpath.write_text(json.dumps(m))


def test_new_column_stops_the_load_and_rolls_back(landing, con, tmp_path):
    drift = tmp_path / "drift"
    shutil.copytree(landing, drift)
    load_day(con, drift, D1)
    before = counts(con)
    _rewrite(drift, D2, "orders",
             lambda t: t.append_column("channel", pa.array(["app"] * t.num_rows)))
    with pytest.raises(LoadError, match="differ from the table"):
        load_day(con, drift, D2)
    assert counts(con) == before  # nothing from D2, not even the tables before orders


def test_cli(landing, tmp_path, capsys):
    db = tmp_path / "x" / "w.duckdb"
    assert cli(["--start", "2026-01-01", "--end", "2026-01-02", "--landing", str(landing),
                "--db", str(db)]) == 0
    assert "2026-01-02: 15 lake tables" in capsys.readouterr().out
    assert cli(["--date", "2026-01-05", "--landing", str(landing), "--db", str(db)]) == 1


def test_default_database_is_the_development_file():
    """Codex review on PR #9: manual loads never write the daily build file."""
    from pathlib import Path

    from loader.__main__ import DEV_DB
    assert DEV_DB == Path("data/dev/warehouse.duckdb")
    makefile = (Path(__file__).resolve().parents[2] / "Makefile").read_text()
    assert "DB    ?= data/dev/warehouse.duckdb" in makefile
    assert "data/build" not in DEV_DB.as_posix()
