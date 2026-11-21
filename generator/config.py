"""Fixed knobs of the generator. Changing any of them changes the output for every date."""
from __future__ import annotations

import datetime as dt

GENERATOR_VERSION = "1"

# The first day that exists. Earlier dates are rejected.
EPOCH = dt.date(2026, 1, 1)
# From this date the shop writes `in_transit` where it used to write `shipped`.
STATUS_RENAME_DATE = dt.date(2026, 6, 1)

# Master data grows by a fixed amount per day, so the id range that exists on any day is a
# formula and no earlier day has to be read.
BASE_CUSTOMERS, NEW_CUSTOMERS_PER_DAY = 2000, 40
BASE_SELLERS, NEW_SELLERS_PER_DAY = 120, 1
BASE_PRODUCTS, NEW_PRODUCTS_PER_DAY = 600, 8

ORDERS_PER_DAY = 500
WEEKDAY_FACTOR = (1.0, 0.95, 0.95, 1.0, 1.1, 1.25, 1.2)  # Monday .. Sunday
DAILY_GROWTH = 0.0015

# order_id = <day index> * ORDER_ID_DAY + <n>; late arrivals use the top of the range.
ORDER_ID_DAY = 100_000
LATE_ID_OFFSET = 90_000
LATE_ID_PER_LAG = 3_000
ORPHAN_PRODUCT_BASE = 9_000_000

# Order outcome mix (status at the time the partition is written).
STATUS_WEIGHTS = {"placed": 5, "paid": 15, "shipped": 25, "delivered": 50, "cancelled": 5}
PAID_STATUSES = {"paid", "shipped", "in_transit", "delivered"}
SHIPPED_STATUSES = {"shipped", "in_transit", "delivered"}
VOUCHER_RATE = 0.10
REFUND_RATE = 0.03

# Documented defects (generator/DEFECTS.md). Counts per partition are exact: round(n * rate).
DUPLICATE_RATE = 0.005
LATE_RATE = 0.02
LATE_MAX_LAG_DAYS = 3
ORPHAN_RATE = 0.002
CASING_RATE = 0.10

TAX_RATE = 0.11  # PPN, included in shop prices
COMMISSION_RATE = 0.05
VOUCHERS_PER_MONTH = 5
CAMPAIGNS_PER_MONTH = 3

PAYMENT_METHODS = ("bank_transfer", "virtual_account", "ewallet", "card", "cod")
COURIERS = ("JNE", "J&T", "SiCepat", "AnterAja", "Pos Indonesia", "GoSend")
CHANNELS = ("google", "meta", "tiktok", "email")
REFUND_REASONS = ("damaged", "wrong_item", "late_delivery", "changed_mind")
SHIPPING_FEES = (0, 9000, 12000, 15000, 20000)
