"""The generator: same seed and date give identical files; defects appear as documented."""
import datetime as dt
from collections import Counter

import pyarrow.parquet as pq
import pytest

from generator import config as c
from generator import model
from generator.__main__ import main as cli
from generator.schemas import SCHEMAS
from generator.write import manifest_path, partition_path, write_day

SEED = 42
DAYS = [dt.date(2026, 1, 1), dt.date(2026, 1, 2), dt.date(2026, 5, 31), dt.date(2026, 6, 1),
        dt.date(2026, 11, 21)]


@pytest.fixture(scope="module")
def land(tmp_path_factory):
    out = tmp_path_factory.mktemp("land")
    manifests = {d: write_day(SEED, d, out) for d in DAYS}
    return out, manifests


def read(out, source, table, day):
    return pq.read_table(partition_path(out, source, table, day)).to_pylist()


# --------------------------------------------------------------------------- determinism


def test_same_seed_and_date_give_identical_files(land, tmp_path):
    out, manifests = land
    for day in (DAYS[1], DAYS[3]):
        again = write_day(SEED, day, tmp_path)
        assert again == manifests[day]
        for source, table in SCHEMAS:
            assert (partition_path(out, source, table, day).read_bytes()
                    == partition_path(tmp_path, source, table, day).read_bytes())
        assert manifest_path(out, day).read_bytes() == manifest_path(tmp_path, day).read_bytes()


def test_a_day_does_not_depend_on_other_days(land, tmp_path):
    """Generating 2026-06-01 alone gives the same files as generating it after other days."""
    out, manifests = land
    assert write_day(SEED, dt.date(2026, 6, 1), tmp_path) == manifests[dt.date(2026, 6, 1)]


def test_other_seed_or_date_changes_the_data(land, tmp_path):
    _, manifests = land
    other = write_day(SEED + 1, DAYS[1], tmp_path)
    assert other["tables"]["shop.orders"]["sha256"] != manifests[DAYS[1]]["tables"]["shop.orders"]["sha256"]
    assert (manifests[DAYS[1]]["tables"]["shop.orders"]["sha256"]
            != manifests[DAYS[2]]["tables"]["shop.orders"]["sha256"])


def test_date_before_epoch_is_rejected(tmp_path):
    with pytest.raises(ValueError):
        model.build_day(SEED, dt.date(2025, 12, 31))
    assert cli(["--date", "2025-12-31", "--out", str(tmp_path)]) == 1


def test_cli_range(tmp_path, capsys):
    assert cli(["--start", "2026-01-01", "--end", "2026-01-02", "--out", str(tmp_path)]) == 0
    assert manifest_path(tmp_path, dt.date(2026, 1, 2)).is_file()
    assert "2026-01-02: 15 tables" in capsys.readouterr().out


# --------------------------------------------------------------------------- shape


def test_every_table_has_a_file_with_its_schema(land):
    out, _ = land
    for day in DAYS:
        for (source, table), schema in SCHEMAS.items():
            assert pq.read_schema(partition_path(out, source, table, day)).equals(schema)


def test_master_data_grows_by_formula(land):
    out, _ = land
    first = read(out, "shop", "customers", DAYS[0])
    assert [r["customer_id"] for r in first] == list(range(1, c.BASE_CUSTOMERS + 1))
    second = read(out, "shop", "customers", DAYS[1])
    assert [r["customer_id"] for r in second] == list(
        range(c.BASE_CUSTOMERS + 1, c.BASE_CUSTOMERS + c.NEW_CUSTOMERS_PER_DAY + 1))
    assert len(read(out, "shop", "products", DAYS[1])) == c.NEW_PRODUCTS_PER_DAY
    assert len(read(out, "shop", "categories", DAYS[4])) == 20


def test_monthly_catalogs_on_the_first(land):
    out, _ = land
    assert len(read(out, "shop", "vouchers", DAYS[3])) == c.VOUCHERS_PER_MONTH
    assert read(out, "shop", "vouchers", DAYS[2]) == []
    assert len(read(out, "marketing", "campaigns", DAYS[0])) == c.CAMPAIGNS_PER_MONTH
    assert len(read(out, "marketing", "daily_spend", DAYS[2])) == c.CAMPAIGNS_PER_MONTH


# --------------------------------------------------------------------------- integrity


def test_keys_resolve_except_planted_orphans(land):
    out, _ = land
    for day in DAYS:
        i = model.day_index(day)
        orders = read(out, "shop", "orders", day)
        ids = {o["order_id"] for o in orders}
        assert all(1 <= o["customer_id"] <= model.customers_through(i) for o in orders)
        items = read(out, "shop", "order_items", day)
        assert {x["order_id"] for x in items} == ids
        for x in items:
            assert (x["product_id"] <= model.products_through(i)
                    or x["product_id"] >= c.ORPHAN_PRODUCT_BASE)
        for table in ("payments", "shipments", "refunds"):
            assert {r["order_id"] for r in read(out, "shop", table, day)} <= ids
        codes = {o["voucher_code"] for o in orders if o["voucher_code"]}
        assert all(code.startswith("HEMAT2026") for code in codes)


def test_ledger_matches_shop_money(land):
    out, _ = land
    day = DAYS[4]
    payments = {p["order_id"]: p for p in read(out, "shop", "payments", day)}
    refunds = {r["order_id"]: r["amount_idr"] for r in read(out, "shop", "refunds", day)}
    invoices = read(out, "ledger", "invoices", day)
    assert len(invoices) == len(payments)
    for inv in invoices:
        oid = int(inv["order_ref"].removeprefix("ORD-"))
        gross = payments[oid]["amount_idr"]
        refund = refunds.get(oid, 0)
        assert inv["gross_idr"] == gross and inv["refund_idr"] == refund
        assert inv["net_revenue_idr"] == round((gross - refund) / (1 + c.TAX_RATE))
        assert inv["cust_ref"].startswith("C-") and len(inv["cust_ref"]) == 9
        expected = "REFUNDED" if refund >= gross and refund else "PARTIAL_REFUND" if refund else "PAID"
        assert inv["invoice_status"] == expected
    lines = read(out, "ledger", "invoice_lines", day)
    settled = sum(s["gross_sales_idr"] for s in read(out, "ledger", "settlements", day))
    assert settled == sum(x["line_amount_idr"] for x in lines
                          if x["product_ref"] < c.ORPHAN_PRODUCT_BASE)
    for s in read(out, "ledger", "settlements", day):
        assert s["payout_idr"] + s["commission_idr"] == s["gross_sales_idr"]


# --------------------------------------------------------------------------- defects


def test_duplicates_exact_count(land):
    out, _ = land
    for day in DAYS:
        orders = read(out, "shop", "orders", day)
        counts = Counter(o["order_id"] for o in orders)
        unique = len(counts)
        dups = [o for o, n in counts.items() if n > 1]
        assert len(dups) == round(unique * c.DUPLICATE_RATE)
        assert all(counts[o] == 2 for o in dups)


def test_late_rows(land):
    out, _ = land
    assert all(o["created_at"].date() == DAYS[0] for o in read(out, "shop", "orders", DAYS[0]))
    for day in DAYS[1:]:
        orders = {o["order_id"]: o for o in read(out, "shop", "orders", day)}
        late = [o for o in orders.values() if o["created_at"].date() < day]
        on_time = len(orders) - len(late)
        assert len(late) == round(on_time * c.LATE_RATE)
        for o in late:
            lag = (day - o["created_at"].date()).days
            assert 1 <= lag <= c.LATE_MAX_LAG_DAYS
            assert o["order_id"] % c.ORDER_ID_DAY > c.LATE_ID_OFFSET


def test_orphan_keys(land):
    out, _ = land
    for day in DAYS:
        items = read(out, "shop", "order_items", day)
        orphans = [x for x in items if x["product_id"] >= c.ORPHAN_PRODUCT_BASE]
        assert len(orphans) == round(len(items) * c.ORPHAN_RATE)


def test_status_renamed_mid_history(land):
    out, _ = land
    before = {o["order_status"] for o in read(out, "shop", "orders", DAYS[2])}
    after = {o["order_status"] for o in read(out, "shop", "orders", DAYS[3])}
    assert "shipped" in before and "in_transit" not in before
    assert "in_transit" in after and "shipped" not in after
    ship_after = {s["shipment_status"] for s in read(out, "shop", "shipments", DAYS[3])}
    assert "shipped" not in ship_after


def test_city_casing(land):
    out, _ = land
    cities = {r["city"] for r in model.reference("cities")}
    for day in (DAYS[0], DAYS[1]):
        rows = read(out, "shop", "customers", day)
        bad = [r for r in rows if r["city"] not in cities]
        assert len(bad) == round(len(rows) * c.CASING_RATE)
        assert all(r["city"] in (r["city"].upper(), r["city"].lower()) for r in bad)


def test_golden_manifest_matches_committed_checksums(tmp_path):
    """Byte-identical across machines: CI (Linux) must reproduce the checksums written on
    the laptop (macOS) with the locked pyarrow. If this fails after a deliberate change to the
    generator, regenerate the golden file and say why in the worknote."""
    import json
    from pathlib import Path

    golden = Path(__file__).parent / "golden" / "manifest-seed42-2026-06-01.json"
    assert write_day(42, dt.date(2026, 6, 1), tmp_path) == json.loads(golden.read_text())
