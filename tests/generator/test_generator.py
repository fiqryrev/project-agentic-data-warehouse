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
    new = [r["customer_id"] for r in second if r["created_at"].date() == DAYS[1]]
    assert new == list(range(c.BASE_CUSTOMERS + 1,
                             c.BASE_CUSTOMERS + c.NEW_CUSTOMERS_PER_DAY + 1))
    new_products = [r for r in read(out, "shop", "products", DAYS[1])
                    if r["created_at"].date() == DAYS[1]]
    assert len(new_products) == c.NEW_PRODUCTS_PER_DAY
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
        for o in orders:
            created_i = model.day_index(o["created_at"].date())
            assert o["order_id"] // c.ORDER_ID_DAY == created_i
            assert 1 <= o["customer_id"] <= model.customers_through(created_i)
        items = read(out, "shop", "order_items", day)
        assert {x["order_id"] // c.ORDER_ID_DAY for x in items} == {i}
        for x in items:
            assert (x["product_id"] <= model.products_through(i)
                    or x["product_id"] >= c.ORPHAN_PRODUCT_BASE)
        for table in ("payments", "shipments", "refunds"):
            assert all(model.order_exists(SEED, r["order_id"]) for r in read(out, "shop", table, day))
        codes = {o["voucher_code"] for o in orders if o["voucher_code"]}
        assert all(code.startswith("HEMAT2026") for code in codes)


def test_ledger_matches_shop_money(land):
    out, _ = land
    day = DAYS[4]
    payments = {p["order_id"]: p for p in read(out, "shop", "payments", day)}
    refunds = {r["order_id"]: r for r in read(out, "shop", "refunds", day)}
    invoices = read(out, "ledger", "invoices", day)
    first = [v for v in invoices if v["refund_idr"] == 0]
    adjusted = [v for v in invoices if v["refund_idr"] > 0]
    assert len(first) == len(payments) and len(adjusted) == len(refunds) > 0
    for inv in invoices:
        oid = int(inv["order_ref"].removeprefix("ORD-"))
        gross, refund = inv["gross_idr"], inv["refund_idr"]
        if refund:
            assert refunds[oid]["amount_idr"] == refund
            assert inv["posted_at"] == refunds[oid]["refunded_at"]
        else:
            assert payments[oid]["amount_idr"] == gross
            assert inv["posted_at"] == payments[oid]["paid_at"]
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


# --------------------------------------------------------------------------- time


TIMESTAMPS = {
    ("shop", "orders"): ("created_at", "updated_at"),
    ("shop", "payments"): ("paid_at",),
    ("shop", "shipments"): ("shipped_at", "delivered_at"),
    ("shop", "refunds"): ("refunded_at",),
    ("ledger", "invoices"): ("posted_at",),
    ("shop", "customers"): ("created_at",),
    ("shop", "products"): ("created_at",),
}


def test_no_timestamp_after_its_partition_day(land):
    """Codex review on PR #7: a partition is what the source knew by the end of that day."""
    out, _ = land
    for day in DAYS:
        end = dt.datetime.combine(day + dt.timedelta(days=1), dt.time())
        for (source, table), cols in TIMESTAMPS.items():
            for row in read(out, source, table, day):
                for col in cols:
                    assert row[col] is None or row[col] < end, (table, col, row)


def test_status_matches_events_up_to_the_row(land):
    """An order row's status is the last event by the end of its updated_at day."""
    out, _ = land
    for day in DAYS:
        for o in read(out, "shop", "orders", day):
            t = model.timeline(SEED, o["order_id"])
            seen = [s for ts, s in t["events"] if ts.date() <= o["updated_at"].date()]
            expected = seen[-1]
            if expected == "shipped" and day >= c.STATUS_RENAME_DATE:
                expected = "in_transit"
            assert o["order_status"] == expected
            assert o["updated_at"] in [ts for ts, _ in t["events"]]
        for s in read(out, "shop", "shipments", day):
            assert (s["delivered_at"] is not None) == (s["shipment_status"] == "delivered")


# --------------------------------------------------------------------------- defects


def test_duplicates_exact_count(land):
    out, _ = land
    for day in DAYS:
        rows = read(out, "shop", "orders", day)
        counts = Counter(tuple(sorted(r.items())) for r in rows)
        dups = [k for k, n in counts.items() if n > 1]
        assert len(dups) == round(len(counts) * c.DUPLICATE_RATE)
        assert all(counts[k] == 2 for k in dups)


def test_late_rows(land):
    out, _ = land
    assert all(o["updated_at"].date() == DAYS[0] for o in read(out, "shop", "orders", DAYS[0]))
    for day in DAYS[1:]:
        i = model.day_index(day)
        rows = {tuple(sorted(r.items())) for r in read(out, "shop", "orders", day)}
        late = [dict(r) for r in rows if dict(r)["updated_at"].date() < day]
        expected = sum(1 for back in range(1, c.LATE_MAX_LAG_DAYS + 1) if i - back >= 0
                       for lag in model._late_plan(SEED, model.day_of(i - back))[1].values()
                       if lag == back)
        assert len(late) == expected > 0
        for o in late:
            assert 1 <= (day - o["updated_at"].date()).days <= c.LATE_MAX_LAG_DAYS
        held = model._late_plan(SEED, day)[1]
        on_time = len(rows) - len(late)
        assert len(held) == round((on_time + len(held)) * c.LATE_RATE)


def test_orphan_keys_are_rare_and_marked(land):
    out, _ = land
    items = [x for day in DAYS for x in read(out, "shop", "order_items", day)]
    orphans = [x for x in items if x["product_id"] >= c.ORPHAN_PRODUCT_BASE]
    assert 0 < len(orphans) < len(items) * c.ORPHAN_RATE * 3


def test_status_renamed_mid_history(land):
    out, _ = land
    before = {o["order_status"] for o in read(out, "shop", "orders", DAYS[2])}
    after = {o["order_status"] for o in read(out, "shop", "orders", DAYS[3])}
    assert "shipped" in before and "in_transit" not in before
    assert "in_transit" in after and "shipped" not in after
    assert {"delivered", "paid", "placed"} <= before
    ship_before = {s["shipment_status"] for s in read(out, "shop", "shipments", DAYS[2])}
    ship_after = {s["shipment_status"] for s in read(out, "shop", "shipments", DAYS[3])}
    assert "shipped" in ship_before and "shipped" not in ship_after


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



# --------------------------------------------------------------------------- history (M4)


def test_customers_move(land):
    """A share of existing customers is written again, with another city, on the day they move."""
    out, _ = land
    day = DAYS[4]
    rows = read(out, "shop", "customers", day)
    moved = [r for r in rows if r["created_at"].date() < day]
    existing = model.customers_through(model.day_index(day) - 1)
    assert len(moved) == round(existing * c.MOVE_RATE) > 0
    for r in moved:
        first = model.customer(SEED, r["customer_id"])
        assert r["city"].lower() != first["city"].lower() or r["province"] != first["province"]
        assert r["updated_at"].date() == day and r["full_name"] == first["full_name"]
    assert all(r["updated_at"] == r["created_at"] for r in rows if r not in moved)


def test_products_are_repriced(land):
    out, _ = land
    day = DAYS[4]
    i = model.day_index(day)
    rows = read(out, "shop", "products", day)
    changed = [r for r in rows if r["created_at"].date() < day]
    assert changed, "some products change price on any later day"
    for r in changed:
        assert r["price_idr"] == model.price_at(SEED, r["product_id"], i)
        assert r["updated_at"].date() == day
        assert model.price_changes_by(SEED, r["product_id"], i) > \
            model.price_changes_by(SEED, r["product_id"], i - 1)


def test_order_items_use_the_price_of_the_order_day(land):
    out, _ = land
    for day in DAYS:
        i = model.day_index(day)
        for x in read(out, "shop", "order_items", day):
            if x["product_id"] < c.ORPHAN_PRODUCT_BASE:
                assert x["unit_price_idr"] == model.price_at(SEED, x["product_id"], i)



def test_a_move_always_changes_the_current_city():
    """Codex review on PR #11: a second move starts from the latest city, not the first."""
    seen_repeat = 0
    for i in range(1, 400):
        day = model.day_of(i)
        for cid in model.movers(SEED, day):
            before = model.previous_move_day(SEED, cid, i)
            current = (model.customer(SEED, cid) if before is None
                       else model.moved_customer(SEED, cid, model.day_of(before)))
            assert model.moved_customer(SEED, cid, day)["city"] != current["city"]
            seen_repeat += before is not None
    assert seen_repeat > 0, "the range should include customers who move twice"


def test_orders_only_name_customers_that_already_exist(land):
    out, _ = land
    for day in DAYS:
        for o in read(out, "shop", "orders", day):
            assert model.customer(SEED, o["customer_id"])["created_at"] <= o["created_at"]
