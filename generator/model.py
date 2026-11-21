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
    seconds = r.randrange(86_400)
    return {
        "customer_id": cid,
        "full_name": f"{first} {last}",
        "email": f"{first.lower()}.{last.lower()}.{cid}@example.com",
        "city": city["city"],
        "province": city["province"],
        # the base customers were migrated at go-live, midnight of the first day
        "created_at": at(day, 0 if cid <= c.BASE_CUSTOMERS else seconds),
    }


def customer_row(seed: int, cid: int) -> dict:
    row = customer(seed, cid)
    row["updated_at"] = row["created_at"]
    return row


def movers(seed: int, day: dt.date) -> list[int]:
    """Existing customers who move to another city on this day."""
    i = day_index(day)
    existing = customers_through(i - 1)
    r = rng(seed, "movers", day.isoformat())
    return sorted(r.sample(range(1, existing + 1), exact_count(existing, c.MOVE_RATE)))


@lru_cache(maxsize=4096)
def _movers_on(seed: int, i: int) -> frozenset[int]:
    return frozenset(movers(seed, day_of(i)))


def previous_move_day(seed: int, cid: int, i: int) -> int | None:
    """The last day index before i on which the customer moved, if any."""
    born = created_day(c.BASE_CUSTOMERS, c.NEW_CUSTOMERS_PER_DAY, cid)
    for j in range(i - 1, born, -1):
        if cid in _movers_on(seed, j):
            return j
    return None


@lru_cache(maxsize=65_536)
def moved_customer(seed: int, cid: int, day: dt.date) -> dict:
    """The customer's row as the shop writes it on the day they move. The destination is
    never the city they live in just before the move (their latest version)."""
    row = customer(seed, cid)
    before = previous_move_day(seed, cid, day_index(day))
    current = row if before is None else moved_customer(seed, cid, day_of(before))
    r = rng(seed, "move", cid, day.isoformat())
    cities = [x for x in reference("cities") if x["city"] != current["city"]]
    city = r.choices(cities, weights=[int(x["weight"]) for x in cities])[0]
    row.update(city=city["city"], province=city["province"],
               updated_at=at(day, r.randrange(86_400)))
    return row


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


@lru_cache(maxsize=200_000)
def reprice_schedule(seed: int, pid: int) -> tuple[int, int]:
    """(first change day index, days between changes) for a product."""
    r = rng(seed, "reprice", pid)
    every = r.randint(*c.REPRICE_EVERY_DAYS)
    born = created_day(c.BASE_PRODUCTS, c.NEW_PRODUCTS_PER_DAY, pid)
    return born + r.randint(1, every), every


def price_changes_by(seed: int, pid: int, i: int) -> int:
    """How many price changes the product has had by the end of day index i."""
    first, every = reprice_schedule(seed, pid)
    return 0 if i < first else 1 + (i - first) // every


def price_at(seed: int, pid: int, i: int) -> int:
    """The product's list price on day index i."""
    base = product(seed, pid)["price_idr"]
    k = price_changes_by(seed, pid, i)
    if k == 0:
        return base
    factor = rng(seed, "reprice", pid, k).uniform(*c.REPRICE_FACTOR)
    return max(int(round(base * factor, -2)), 1000)


def product_row(seed: int, pid: int, day: dt.date) -> dict:
    """The product as the shop writes it on its creation day or on a price-change day."""
    i = day_index(day)
    row = dict(product(seed, pid))
    row["price_idr"] = price_at(seed, pid, i)
    if row["created_at"].date() == day:
        row["updated_at"] = row["created_at"]
    else:
        k = price_changes_by(seed, pid, i)
        row["updated_at"] = at(day, rng(seed, "reprice-at", pid, k).randrange(86_400))
    return row


def repriced(seed: int, day: dt.date) -> list[int]:
    """Existing products whose price changes on this day."""
    i = day_index(day)
    out = []
    for pid in range(1, products_through(i - 1) + 1):
        first, every = reprice_schedule(seed, pid)
        if i >= first and (i - first) % every == 0:
            out.append(pid)
    return out


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
#
# Every order has a timeline (created, then paid or cancelled, shipped, delivered, maybe
# refunded) that is a pure function of (seed, order_id). A partition holds what the source
# wrote that day: an order row for each order with an event on that day, carrying its state at
# the end of the day, plus the payment, shipment, refund and ledger rows of that day's
# events. No timestamp in a partition is later than the end of its day.


def order_count(seed: int, day: dt.date) -> int:
    r = rng(seed, "volume", day.isoformat())
    i = day_index(day)
    n = c.ORDERS_PER_DAY * c.WEEKDAY_FACTOR[day.weekday()] * (1 + c.DAILY_GROWTH * i)
    return int(round(n * r.uniform(0.9, 1.1)))


def order_exists(seed: int, order_id: int) -> bool:
    i, k = divmod(order_id, c.ORDER_ID_DAY)
    return i >= 0 and 1 <= k <= order_count(seed, day_of(i))


def _secs(r: random.Random, bounds: tuple[int, int]) -> dt.timedelta:
    return dt.timedelta(seconds=r.randint(*bounds))


def timeline(seed: int, order_id: int) -> dict:
    """One order with its items, money and event times."""
    i = order_id // c.ORDER_ID_DAY
    day = day_of(i)
    r = rng(seed, "order", order_id)
    created = at(day, r.randrange(86_400))
    voucher_code = None
    if r.random() < c.VOUCHER_RATE:
        voucher_code = f"HEMAT{month_key(day)}{r.randint(1, c.VOUCHERS_PER_MONTH)}"
    items = []
    for line in range(1, r.choices((1, 2, 3, 4), weights=(50, 30, 15, 5))[0] + 1):
        pid = r.randint(1, products_through(i))
        price = price_at(seed, pid, i)
        if rng(seed, "orphan", order_id, line).random() < c.ORPHAN_RATE:
            pid = c.ORPHAN_PRODUCT_BASE + r.randrange(1_000_000)
        items.append({"order_item_id": order_id * 10 + line, "order_id": order_id,
                      "product_id": pid, "quantity": r.choices((1, 2, 3), weights=(75, 18, 7))[0],
                      "unit_price_idr": price})
    # customers who existed before the order: those created before the order day (on the
    # first day, the base customers migrated at midnight)
    order = {"order_id": order_id,
             "customer_id": r.randint(1, customers_through(i - 1) if i else c.BASE_CUSTOMERS),
             "voucher_code": voucher_code, "shipping_fee_idr": r.choice(c.SHIPPING_FEES),
             "created_at": created}
    subtotal = sum(x["quantity"] * x["unit_price_idr"] for x in items)
    t = {"order": order, "items": items, "gross": subtotal - _discount(seed, order, subtotal)
         + order["shipping_fee_idr"], "payment_method": r.choice(c.PAYMENT_METHODS),
         "courier": r.choice(c.COURIERS), "events": [(created, "placed")]}
    outcome = r.choices(list(c.OUTCOME_WEIGHTS), weights=list(c.OUTCOME_WEIGHTS.values()))[0]
    if outcome == "cancelled":
        t["events"].append((created + _secs(r, c.CANCEL_DELAY), "cancelled"))
    elif outcome == "completed":
        paid = created + _secs(r, c.PAY_DELAY)
        shipped = paid + _secs(r, c.SHIP_DELAY)
        delivered = shipped + _secs(r, c.DELIVER_DELAY)
        t["events"] += [(paid, "paid"), (shipped, "shipped"), (delivered, "delivered")]
        t.update(paid_at=paid, shipped_at=shipped, delivered_at=delivered)
        if r.random() < c.REFUND_RATE:
            first = items[0]
            full = r.random() < 0.3
            t["refund"] = {
                "amount": t["gross"] if full else min(t["gross"],
                                                      first["quantity"] * first["unit_price_idr"]),
                "reason": r.choice(c.REFUND_REASONS),
                "at": delivered + _secs(r, c.REFUND_DELAY),
            }
    return t


def _discount(seed: int, order: dict, subtotal: int) -> int:
    code = order["voucher_code"]
    if not code:
        return 0
    month, k = int(code[5:11]), int(code[11:])
    v = voucher(seed, month, k, order["created_at"].date())
    if subtotal < v["min_spend_idr"]:
        return 0
    return min(subtotal * v["discount_pct"] // 100, v["max_discount_idr"])


@lru_cache(maxsize=64)
def _timelines_of(seed: int, i: int) -> tuple[dict, ...]:
    """All orders created on day index i."""
    return tuple(timeline(seed, i * c.ORDER_ID_DAY + k)
                 for k in range(1, order_count(seed, day_of(i)) + 1))


def _active(seed: int, day: dt.date) -> list[dict]:
    """Orders that may have an event on this day (created within the lifecycle horizon)."""
    i = day_index(day)
    return [t for x in range(max(0, i - c.LIFECYCLE_DAYS), i + 1) for t in _timelines_of(seed, x)]


def _on(ts: dt.datetime | None, day: dt.date) -> bool:
    return ts is not None and ts.date() == day


def _invoice(t: dict, refund: int, posted: dt.datetime) -> dict:
    o, gross = t["order"], t["gross"]
    return {
        "invoice_id": f"INV-{o['order_id']}",
        "order_ref": f"ORD-{o['order_id']}",
        "cust_ref": f"C-{o['customer_id']:07d}",
        "invoice_date": t["paid_at"].date(),
        "invoice_status": ("REFUNDED" if refund and refund >= gross
                           else "PARTIAL_REFUND" if refund else "PAID"),
        "gross_idr": gross,
        "tax_idr": int(round(gross - gross / (1 + c.TAX_RATE))),
        "refund_idr": refund,
        "net_revenue_idr": int(round((gross - refund) / (1 + c.TAX_RATE))),
        "posted_at": posted,
    }


def base_order_rows(seed: int, day: dt.date) -> Rows:
    """Order rows as the source wrote them on this day, before late delivery or duplicates."""
    rows = []
    for t in _active(seed, day):
        todays = [(ts, s) for ts, s in t["events"] if ts.date() == day]
        if not todays:
            continue
        cut = [(ts, s) for ts, s in t["events"] if ts.date() <= day]
        rows.append({**t["order"], "order_status": cut[-1][1], "updated_at": todays[-1][0]})
    return rows


def _late_plan(seed: int, day: dt.date) -> tuple[Rows, dict[int, int]]:
    """The day's base rows, and {row index: days late} for the rows held back."""
    rows = base_order_rows(seed, day)
    r = rng(seed, "late", day.isoformat())
    held = sorted(r.sample(range(len(rows)), exact_count(len(rows), c.LATE_RATE)))
    return rows, {k: r.randint(1, c.LATE_MAX_LAG_DAYS) for k in held}


def order_rows(seed: int, day: dt.date) -> Rows:
    """The day's order rows with the documented defects: late rows and duplicates."""
    i = day_index(day)
    rows, held_today = _late_plan(seed, day)
    keep = [x for k, x in enumerate(rows) if k not in held_today]
    for back in range(1, c.LATE_MAX_LAG_DAYS + 1):
        if i - back < 0:
            continue
        earlier, held = _late_plan(seed, day_of(i - back))
        keep += [dict(earlier[k]) for k, lag in held.items() if lag == back]
    for x in keep:
        if x["order_status"] == "shipped" and day >= c.STATUS_RENAME_DATE:
            x["order_status"] = "in_transit"
    r = rng(seed, "duplicates", day.isoformat())
    dup = set(r.sample(range(len(keep)), exact_count(len(keep), c.DUPLICATE_RATE)))
    out = []
    for k, x in enumerate(keep):
        out.append(x)
        if k in dup:
            out.append(dict(x))
    return out


def build_day(seed: int, day: dt.date) -> dict[tuple[str, str], Rows]:
    """Every table for one partition date. Keys are (source, table)."""
    i = day_index(day)
    out: dict[tuple[str, str], Rows] = {}

    # master data: categories every day; customers and products when created or changed;
    # sellers when created
    out["shop", "categories"] = [
        {"category_id": int(x["category_id"]), "category_name": x["category_name"],
         "parent_name": x["parent_name"]} for x in reference("categories")]
    customers = [customer_row(seed, cid) for cid in range(customers_through(i - 1) + 1,
                                                           customers_through(i) + 1)]
    customers += [dict(moved_customer(seed, cid, day)) for cid in movers(seed, day)]
    r_case = rng(seed, "casing", day.isoformat())
    for idx in r_case.sample(range(len(customers)), exact_count(len(customers), c.CASING_RATE)):
        row = customers[idx]
        row["city"] = row["city"].upper() if r_case.random() < 0.5 else row["city"].lower()
    out["shop", "customers"] = customers
    out["shop", "sellers"] = [seller(seed, s) for s in range(sellers_through(i - 1) + 1,
                                                             sellers_through(i) + 1)]
    out["shop", "products"] = [product_row(seed, p, day)
                               for p in [*repriced(seed, day),
                                         *range(products_through(i - 1) + 1,
                                                products_through(i) + 1)]]
    month = month_key(day)
    out["shop", "vouchers"] = ([voucher(seed, month, k, day)
                                for k in range(1, c.VOUCHERS_PER_MONTH + 1)]
                               if starts_catalog(day) else [])
    campaigns = [campaign(seed, month, k, day) for k in range(1, c.CAMPAIGNS_PER_MONTH + 1)]
    out["marketing", "campaigns"] = campaigns if starts_catalog(day) else []

    out["shop", "orders"] = order_rows(seed, day)
    items, payments, shipments, refunds, invoices, lines = [], [], [], [], [], []
    seller_sales: dict[int, int] = {}
    renamed = day >= c.STATUS_RENAME_DATE
    for t in _active(seed, day):
        o = t["order"]
        oid = o["order_id"]
        if _on(o["created_at"], day):
            items.extend(dict(x) for x in t["items"])
        if _on(t.get("paid_at"), day):
            payments.append({"payment_id": oid, "order_id": oid,
                             "payment_method": t["payment_method"], "amount_idr": t["gross"],
                             "paid_at": t["paid_at"]})
            invoices.append(_invoice(t, 0, t["paid_at"]))
            for n, x in enumerate(t["items"], 1):
                amount = x["quantity"] * x["unit_price_idr"]
                lines.append({"invoice_id": f"INV-{oid}", "line_no": n,
                              "product_ref": x["product_id"], "quantity": x["quantity"],
                              "line_amount_idr": amount})
                if x["product_id"] < c.ORPHAN_PRODUCT_BASE:
                    sid = product(seed, x["product_id"])["seller_id"]
                    seller_sales[sid] = seller_sales.get(sid, 0) + amount
        shipped_today, delivered_today = _on(t.get("shipped_at"), day), _on(t.get("delivered_at"), day)
        if shipped_today or delivered_today:
            shipments.append({
                "shipment_id": oid, "order_id": oid, "courier": t["courier"],
                "shipment_status": ("delivered" if delivered_today
                                    else "in_transit" if renamed else "shipped"),
                "shipped_at": t["shipped_at"],
                "delivered_at": t["delivered_at"] if delivered_today else None,
            })
        refund = t.get("refund")
        if refund and _on(refund["at"], day):
            refunds.append({"refund_id": oid, "order_id": oid, "refund_reason": refund["reason"],
                            "amount_idr": refund["amount"], "refunded_at": refund["at"]})
            invoices.append(_invoice(t, refund["amount"], refund["at"]))

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
