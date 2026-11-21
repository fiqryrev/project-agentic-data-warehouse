"""Build every source table for one day, from (seed, date) alone.

Nothing here reads the clock or earlier partitions. Each random stream is seeded from a
SHA-256 of (seed, purpose, key), so a day, a customer or a product always comes out the same,
whichever days were generated before it.
"""
from __future__ import annotations

import csv
import datetime as dt
import hashlib
import random
from functools import lru_cache
from pathlib import Path

from generator import config as c

REFERENCE = Path(__file__).resolve().parent / "reference"
Rows = list[dict]


# --------------------------------------------------------------------------- basics


def rng(seed: int, *key) -> random.Random:
    digest = hashlib.sha256("|".join(map(str, (seed, *key))).encode()).digest()
    return random.Random(int.from_bytes(digest[:16], "big"))


def day_index(day: dt.date) -> int:
    i = (day - c.EPOCH).days
    if i < 0:
        raise ValueError(f"{day} is before the first generated day {c.EPOCH}")
    return i


def day_of(i: int) -> dt.date:
    return c.EPOCH + dt.timedelta(days=i)


def at(day: dt.date, seconds: int) -> dt.datetime:
    return dt.datetime.combine(day, dt.time()) + dt.timedelta(seconds=seconds)


@lru_cache(maxsize=None)
def reference(name: str) -> tuple[dict, ...]:
    with open(REFERENCE / f"{name}.csv", encoding="utf-8", newline="") as fh:
        return tuple(csv.DictReader(fh))


def exact_count(n: int, rate: float) -> int:
    return int(round(n * rate))


def month_key(day: dt.date) -> int:
    return day.year * 100 + day.month


def month_bounds(day: dt.date) -> tuple[dt.date, dt.date]:
    start = day.replace(day=1)
    nxt = (start + dt.timedelta(days=32)).replace(day=1)
    return start, nxt - dt.timedelta(days=1)


def starts_catalog(day: dt.date) -> bool:
    """Monthly catalogs (vouchers, campaigns) are published on the 1st, or on the epoch."""
    return day.day == 1 or day == c.EPOCH


# --------------------------------------------------------------------------- id ranges


def through(base: int, per_day: int, i: int) -> int:
    """Highest id that exists at the end of day index i (0 before the epoch)."""
    return 0 if i < 0 else base + per_day * i


def created_day(base: int, per_day: int, entity_id: int) -> int:
    return 0 if entity_id <= base else 1 + (entity_id - base - 1) // per_day


def customers_through(i: int) -> int:
    return through(c.BASE_CUSTOMERS, c.NEW_CUSTOMERS_PER_DAY, i)


def sellers_through(i: int) -> int:
    return through(c.BASE_SELLERS, c.NEW_SELLERS_PER_DAY, i)


def products_through(i: int) -> int:
    return through(c.BASE_PRODUCTS, c.NEW_PRODUCTS_PER_DAY, i)


# --------------------------------------------------------------------------- master data


def _city(r: random.Random) -> dict:
    cities = reference("cities")
    return r.choices(cities, weights=[int(x["weight"]) for x in cities])[0]


def customer(seed: int, cid: int) -> dict:
    r = rng(seed, "customer", cid)
    first = r.choice(reference("first_names"))["first_name"]
    last = r.choice(reference("last_names"))["last_name"]
    city = _city(r)
    day = day_of(created_day(c.BASE_CUSTOMERS, c.NEW_CUSTOMERS_PER_DAY, cid))
    return {
        "customer_id": cid,
        "full_name": f"{first} {last}",
        "email": f"{first.lower()}.{last.lower()}.{cid}@example.com",
        "city": city["city"],
        "province": city["province"],
        "created_at": at(day, r.randrange(86_400)),
    }


def seller(seed: int, sid: int) -> dict:
    r = rng(seed, "seller", sid)
    city = _city(r)
    word = r.choice(("Jaya", "Makmur", "Sentosa", "Abadi", "Berkah", "Mandiri", "Sejahtera"))
    last = r.choice(reference("last_names"))["last_name"]
    day = day_of(created_day(c.BASE_SELLERS, c.NEW_SELLERS_PER_DAY, sid))
    return {
        "seller_id": sid,
        "seller_name": f"Toko {last} {word} {sid}",
        "city": city["city"],
        "province": city["province"],
        "created_at": at(day, r.randrange(86_400)),
    }


@lru_cache(maxsize=200_000)
def product(seed: int, pid: int) -> dict:
    r = rng(seed, "product", pid)
    i = created_day(c.BASE_PRODUCTS, c.NEW_PRODUCTS_PER_DAY, pid)
    cat = r.choice(reference("categories"))
    lo, hi = int(cat["price_min_idr"]), int(cat["price_max_idr"])
    # log-uniform between the category bounds, rounded to Rp100
    price = int(round(lo * (hi / lo) ** r.random(), -2))
    grade = r.choice(("Basic", "Plus", "Pro", "Premium", "Lite", "Original"))
    return {
        "product_id": pid,
        "seller_id": r.randint(1, sellers_through(i)),
        "category_id": int(cat["category_id"]),
        "product_name": f"{cat['category_name']} {grade} {pid}",
        "price_idr": max(price, 1000),
        "created_at": at(day_of(i), r.randrange(86_400)),
    }


def voucher(seed: int, month: int, k: int, day: dt.date) -> dict:
    r = rng(seed, "voucher", month, k)
    start, end = month_bounds(day)
    return {
        "voucher_code": f"HEMAT{month}{k}",
        "discount_pct": r.choice((5, 10, 15, 20)),
        "max_discount_idr": r.choice((10_000, 25_000, 50_000, 100_000)),
        "min_spend_idr": r.choice((0, 50_000, 100_000, 250_000)),
        "valid_from": start,
        "valid_to": end,
    }


def campaign(seed: int, month: int, k: int, day: dt.date) -> dict:
    r = rng(seed, "campaign", month, k)
    start, end = month_bounds(day)
    channel = c.CHANNELS[(month + k) % len(c.CHANNELS)]
    theme = r.choice(("Gajian", "Akhir Bulan", "Flash Sale", "Ramadan", "Belanja Hemat"))
    return {
        "campaign_id": month * 10 + k,
        "campaign_name": f"{theme} {month} {channel}",
        "channel": channel,
        "start_date": start,
        "end_date": end,
        "budget_idr": r.choice((50, 75, 100, 150, 200)) * 1_000_000,
    }


# --------------------------------------------------------------------------- orders


def _order_count(seed: int, day: dt.date) -> int:
    r = rng(seed, "volume", day.isoformat())
    i = day_index(day)
    n = c.ORDERS_PER_DAY * c.WEEKDAY_FACTOR[day.weekday()] * (1 + c.DAILY_GROWTH * i)
    return int(round(n * r.uniform(0.9, 1.1)))


def _status(r: random.Random, partition_day: dt.date) -> str:
    s = r.choices(list(c.STATUS_WEIGHTS), weights=list(c.STATUS_WEIGHTS.values()))[0]
    if s == "shipped" and partition_day >= c.STATUS_RENAME_DATE:
        return "in_transit"
    return s


def _one_order(seed: int, r: random.Random, order_id: int, order_day_i: int,
               partition_day: dt.date) -> dict:
    """An order with its items and money, before defects are applied."""
    order_day = day_of(order_day_i)
    created = at(order_day, r.randrange(86_400))
    status = _status(r, partition_day)
    voucher_code = None
    if r.random() < c.VOUCHER_RATE:
        voucher_code = f"HEMAT{month_key(order_day)}{r.randint(1, c.VOUCHERS_PER_MONTH)}"
    items = []
    for line in range(1, r.choices((1, 2, 3, 4), weights=(50, 30, 15, 5))[0] + 1):
        pid = r.randint(1, products_through(order_day_i))
        items.append({
            "order_item_id": order_id * 10 + line,
            "order_id": order_id,
            "product_id": pid,
            "quantity": r.choices((1, 2, 3), weights=(75, 18, 7))[0],
            "unit_price_idr": product(seed, pid)["price_idr"],
        })
    return {
        "order": {
            "order_id": order_id,
            "customer_id": r.randint(1, customers_through(order_day_i)),
            "order_status": status,
            "voucher_code": voucher_code,
            "shipping_fee_idr": r.choice(c.SHIPPING_FEES),
            "created_at": created,
        },
        "items": items,
        "payment_method": r.choice(c.PAYMENT_METHODS),
        "pay_delay": r.randint(60, 6 * 3600),
        "courier": r.choice(c.COURIERS),
        "ship_delay": r.randint(2 * 3600, 30 * 3600),
        "deliver_delay": r.randint(86_400, 4 * 86_400),
    }


def _discount(seed: int, order: dict, subtotal: int) -> int:
    code = order["voucher_code"]
    if not code:
        return 0
    month, k = int(code[5:11]), int(code[11:])
    v = voucher(seed, month, k, order["created_at"].date())
    if subtotal < v["min_spend_idr"]:
        return 0
    return min(subtotal * v["discount_pct"] // 100, v["max_discount_idr"])


def build_day(seed: int, day: dt.date) -> dict[tuple[str, str], Rows]:
    """Every table for one partition date. Keys are (source, table)."""
    i = day_index(day)
    out: dict[tuple[str, str], Rows] = {}

    # master data: categories every day, others on the day they are created
    out["shop", "categories"] = [
        {"category_id": int(x["category_id"]), "category_name": x["category_name"],
         "parent_name": x["parent_name"]} for x in reference("categories")]
    customers = [customer(seed, cid) for cid in range(customers_through(i - 1) + 1,
                                                       customers_through(i) + 1)]
    r_case = rng(seed, "casing", day.isoformat())
    for idx in r_case.sample(range(len(customers)), exact_count(len(customers), c.CASING_RATE)):
        row = customers[idx]
        row["city"] = row["city"].upper() if r_case.random() < 0.5 else row["city"].lower()
    out["shop", "customers"] = customers
    out["shop", "sellers"] = [seller(seed, s) for s in range(sellers_through(i - 1) + 1,
                                                             sellers_through(i) + 1)]
    out["shop", "products"] = [dict(product(seed, p)) for p in range(products_through(i - 1) + 1,
                                                                     products_through(i) + 1)]
    month = month_key(day)
    out["shop", "vouchers"] = ([voucher(seed, month, k, day)
                                for k in range(1, c.VOUCHERS_PER_MONTH + 1)]
                               if starts_catalog(day) else [])
    campaigns = [campaign(seed, month, k, day) for k in range(1, c.CAMPAIGNS_PER_MONTH + 1)]
    out["marketing", "campaigns"] = campaigns if starts_catalog(day) else []

    # orders of the day, then late arrivals from up to three days back
    r = rng(seed, "orders", day.isoformat())
    built = [_one_order(seed, r, i * c.ORDER_ID_DAY + k + 1, i, day)
             for k in range(_order_count(seed, day))]
    n_late = exact_count(len(built), c.LATE_RATE)
    for j in range(n_late if i > 0 else 0):
        lag = r.randint(1, min(c.LATE_MAX_LAG_DAYS, i))
        oid = (i - lag) * c.ORDER_ID_DAY + c.LATE_ID_OFFSET + (lag - 1) * c.LATE_ID_PER_LAG + j + 1
        built.append(_one_order(seed, r, oid, i - lag, day))

    orders, items, payments, shipments, refunds = [], [], [], [], []
    invoices, lines = [], []
    seller_sales: dict[int, int] = {}
    for b in built:
        o = b["order"]
        orders.append(o)
        items.extend(b["items"])
    # orphan keys: a few items point at products that never existed
    r_def = rng(seed, "defects", day.isoformat())
    for idx in sorted(r_def.sample(range(len(items)), exact_count(len(items), c.ORPHAN_RATE))):
        items[idx]["product_id"] = c.ORPHAN_PRODUCT_BASE + r_def.randrange(1_000_000)

    delivered = [b for b in built if b["order"]["order_status"] == "delivered"]
    refunded = {id(b) for b in r_def.sample(delivered, exact_count(len(delivered), c.REFUND_RATE))}
    for b in built:
        o = b["order"]
        status = o["order_status"]
        if status not in c.PAID_STATUSES:
            continue
        subtotal = sum(x["quantity"] * x["unit_price_idr"] for x in b["items"])
        gross = subtotal - _discount(seed, o, subtotal) + o["shipping_fee_idr"]
        paid_at = o["created_at"] + dt.timedelta(seconds=b["pay_delay"])
        payments.append({"payment_id": o["order_id"], "order_id": o["order_id"],
                         "payment_method": b["payment_method"], "amount_idr": gross,
                         "paid_at": paid_at})
        if status in c.SHIPPED_STATUSES:
            shipped_at = paid_at + dt.timedelta(seconds=b["ship_delay"])
            shipments.append({
                "shipment_id": o["order_id"], "order_id": o["order_id"],
                "courier": b["courier"], "shipment_status": status, "shipped_at": shipped_at,
                "delivered_at": (shipped_at + dt.timedelta(seconds=b["deliver_delay"])
                                 if status == "delivered" else None),
            })
        refund = 0
        if id(b) in refunded:
            r_ref = rng(seed, "refund", o["order_id"])
            full = r_ref.random() < 0.3
            first = b["items"][0]
            refund = gross if full else min(gross, first["quantity"] * first["unit_price_idr"])
            refunds.append({"refund_id": o["order_id"], "order_id": o["order_id"],
                            "refund_reason": r_ref.choice(c.REFUND_REASONS),
                            "amount_idr": refund,
                            "refunded_at": paid_at + dt.timedelta(days=r_ref.randint(3, 10))})
        tax = int(round(gross - gross / (1 + c.TAX_RATE)))
        invoices.append({
            "invoice_id": f"INV-{o['order_id']}",
            "order_ref": f"ORD-{o['order_id']}",
            "cust_ref": f"C-{o['customer_id']:07d}",
            "invoice_date": paid_at.date(),
            "invoice_status": ("REFUNDED" if refund and refund >= gross
                               else "PARTIAL_REFUND" if refund else "PAID"),
            "gross_idr": gross,
            "tax_idr": tax,
            "refund_idr": refund,
            "net_revenue_idr": int(round((gross - refund) / (1 + c.TAX_RATE))),
        })
        for n, x in enumerate(b["items"], 1):
            amount = x["quantity"] * x["unit_price_idr"]
            lines.append({"invoice_id": f"INV-{o['order_id']}", "line_no": n,
                          "product_ref": x["product_id"], "quantity": x["quantity"],
                          "line_amount_idr": amount})
            if x["product_id"] < c.ORPHAN_PRODUCT_BASE:
                sid = product(seed, x["product_id"])["seller_id"]
                seller_sales[sid] = seller_sales.get(sid, 0) + amount

    # duplicates: a few order rows are delivered twice by the source
    dup = set(r_def.sample(range(len(orders)), exact_count(len(orders), c.DUPLICATE_RATE)))
    with_dups = []
    for idx, o in enumerate(orders):
        with_dups.append(o)
        if idx in dup:
            with_dups.append(dict(o))

    out["shop", "orders"] = with_dups
    out["shop", "order_items"] = items
    out["shop", "payments"] = payments
    out["shop", "shipments"] = shipments
    out["shop", "refunds"] = refunds
    out["ledger", "invoices"] = invoices
    out["ledger", "invoice_lines"] = lines
    out["ledger", "settlements"] = [
        {"settlement_id": f"STL-{day:%Y%m%d}-{sid}", "seller_ref": f"S-{sid:05d}",
         "settlement_date": day, "gross_sales_idr": gross,
         "commission_idr": int(round(gross * c.COMMISSION_RATE)),
         "payout_idr": gross - int(round(gross * c.COMMISSION_RATE))}
        for sid, gross in sorted(seller_sales.items())]

    r_mkt = rng(seed, "spend", day.isoformat())
    spend = []
    for camp in campaigns:
        daily = camp["budget_idr"] // (camp["end_date"].day)
        amount = int(round(daily * r_mkt.uniform(0.6, 1.3), -3))
        impressions = int(amount / r_mkt.uniform(15, 60))
        spend.append({"spend_date": day, "campaign_id": camp["campaign_id"], "spend_idr": amount,
                      "impressions": impressions,
                      "clicks": int(impressions * r_mkt.uniform(0.005, 0.03))})
    out["marketing", "daily_spend"] = spend
    return out
