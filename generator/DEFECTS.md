# Generator: sources, layout and documented defects

The generator writes a fictional Indonesian marketplace, one Parquet partition per table per
day, from `(seed, date)` alone. The same seed and date always give the same bytes (checked
by `tests/generator/`). Knobs live in `generator/config.py`; changing one changes every day.

```bash
uv run python -m generator --start 2026-01-01 --end 2026-01-07     # default seed 42
```

Output, under `data/landing/` (gitignored):
`<source>/<table>/dt=YYYY-MM-DD/part-0.parquet`, plus
`_manifest/dt=YYYY-MM-DD/manifest.json` with row counts and SHA-256 per file. Every table
has a file every day, empty when nothing happened.

## Sources and tables

| Source | Table | One row per | Written on |
|---|---|---|---|
| `shop` | `categories` | category (20, from `reference/categories.csv`) | every day (full list) |
| `shop` | `customers` | new customer: 2,000 on 2026-01-01, then 40 a day | creation day |
| `shop` | `sellers` | new seller: 120, then 1 a day | creation day |
| `shop` | `products` | new product: 600, then 8 a day | creation day |
| `shop` | `vouchers` | voucher code, 5 per month | the 1st (and 2026-01-01) |
| `shop` | `orders` | order (about 500 a day, weekly pattern, slow growth) | order day, or later (late rows) |
| `shop` | `order_items` | order line, 1 to 4 per order | with its order |
| `shop` | `payments` | payment of an order in `paid`, `shipped`/`in_transit` or `delivered` | with its order |
| `shop` | `shipments` | shipment of an order in `shipped`/`in_transit` or `delivered` | with its order |
| `shop` | `refunds` | refund, 3% of delivered orders (30% full, else the first line) | with its order |
| `ledger` | `invoices` | invoice of a paid order | with its order |
| `ledger` | `invoice_lines` | invoice line | with its invoice |
| `ledger` | `settlements` | seller payout for the day's invoice lines, 5% commission | partition day |
| `marketing` | `campaigns` | campaign, 3 per month, channel rotates | the 1st (and 2026-01-01) |
| `marketing` | `daily_spend` | campaign and day | every day |

Money is in whole rupiah (`*_idr`, int64). Timestamps are naive UTC. The status of an order is
its status when the partition was written; a later partition does not update it.

## The ledger disagrees with the shop on purpose

| What | Shop | Ledger |
|---|---|---|
| Customer key | `customer_id` 1234 | `cust_ref` `C-0001234` |
| Order key | `order_id` | `order_ref` `ORD-<order_id>` |
| Seller key | `seller_id` 7 | `seller_ref` `S-00007` |
| Status vocabulary | `placed`, `paid`, `shipped`/`in_transit`, `delivered`, `cancelled` | `PAID`, `PARTIAL_REFUND`, `REFUNDED` |
| Revenue | `payments.amount_idr`: items minus voucher plus shipping, PPN included | `net_revenue_idr` = (gross minus refund) / 1.11, net of refunds and the 11% PPN |
| Lines | `order_items` | `invoice_lines` hold items before voucher and shipping, so they do not sum to `gross_idr` |
| Refund date | `refunds.refunded_at` 3 to 10 days after payment | refund already in the invoice of the order day |

## Documented defects

Counts are exact per partition: `round(n * rate)`, chosen by a seeded draw.

| Defect | Where | Rate | How to spot it |
|---|---|---|---|
| Casing | `shop.customers.city` all upper or all lower case | 10% of a day's new customers | `city <> initcap(city)` |
| Duplicates | `shop.orders`: a row appears twice, identical | 0.5% of the day's orders | `count(*) > 1` per `order_id` |
| Late rows | `shop.orders` (with items, payments, ...): an order from 1 to 3 days earlier lands in today's partition | 2% of the day's orders | `created_at::date < dt`; their ids are `<day> * 100000 + 90001 ..` |
| Orphan keys | `shop.order_items.product_id` (and `ledger.invoice_lines.product_ref`) points at a product that never existed | 0.2% of the day's items | ids from 9,000,000; no match in `products`; left out of settlements |
| Renamed status | `shop.orders.order_status` and `shop.shipments.shipment_status`: `shipped` becomes `in_transit` | partitions from 2026-06-01 | both values exist across history, never in one partition |

A staging model fixes each of these and says how; the knowledge base records them as `da-`
entries (M6).
