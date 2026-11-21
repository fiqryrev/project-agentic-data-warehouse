"""Parquet schema of every generated table, keyed by (source, table)."""
from __future__ import annotations

import pyarrow as pa

I, S, D, T = pa.int64(), pa.string(), pa.date32(), pa.timestamp("us")


def _s(*fields: tuple[str, pa.DataType]) -> pa.Schema:
    return pa.schema([pa.field(name, typ) for name, typ in fields])


SCHEMAS: dict[tuple[str, str], pa.Schema] = {
    ("shop", "categories"): _s(("category_id", I), ("category_name", S), ("parent_name", S)),
    ("shop", "customers"): _s(("customer_id", I), ("full_name", S), ("email", S), ("city", S),
                              ("province", S), ("created_at", T), ("updated_at", T)),
    ("shop", "sellers"): _s(("seller_id", I), ("seller_name", S), ("city", S), ("province", S),
                            ("created_at", T)),
    ("shop", "products"): _s(("product_id", I), ("seller_id", I), ("category_id", I),
                             ("product_name", S), ("price_idr", I), ("created_at", T),
                             ("updated_at", T)),
    ("shop", "vouchers"): _s(("voucher_code", S), ("discount_pct", I), ("max_discount_idr", I),
                             ("min_spend_idr", I), ("valid_from", D), ("valid_to", D)),
    ("shop", "orders"): _s(("order_id", I), ("customer_id", I), ("order_status", S),
                           ("voucher_code", S), ("shipping_fee_idr", I), ("created_at", T),
                           ("updated_at", T)),
    ("shop", "order_items"): _s(("order_item_id", I), ("order_id", I), ("product_id", I),
                                ("quantity", I), ("unit_price_idr", I)),
    ("shop", "payments"): _s(("payment_id", I), ("order_id", I), ("payment_method", S),
                             ("amount_idr", I), ("paid_at", T)),
    ("shop", "shipments"): _s(("shipment_id", I), ("order_id", I), ("courier", S),
                              ("shipment_status", S), ("shipped_at", T), ("delivered_at", T)),
    ("shop", "refunds"): _s(("refund_id", I), ("order_id", I), ("refund_reason", S),
                            ("amount_idr", I), ("refunded_at", T)),
    ("ledger", "invoices"): _s(("invoice_id", S), ("order_ref", S), ("cust_ref", S),
                               ("invoice_date", D), ("invoice_status", S), ("gross_idr", I),
                               ("tax_idr", I), ("refund_idr", I), ("net_revenue_idr", I),
                               ("posted_at", T)),
    ("ledger", "invoice_lines"): _s(("invoice_id", S), ("line_no", I), ("product_ref", I),
                                    ("quantity", I), ("line_amount_idr", I)),
    ("ledger", "settlements"): _s(("settlement_id", S), ("seller_ref", S),
                                  ("settlement_date", D), ("gross_sales_idr", I),
                                  ("commission_idr", I), ("payout_idr", I)),
    ("marketing", "campaigns"): _s(("campaign_id", I), ("campaign_name", S), ("channel", S),
                                   ("start_date", D), ("end_date", D), ("budget_idr", I)),
    ("marketing", "daily_spend"): _s(("spend_date", D), ("campaign_id", I), ("spend_idr", I),
                                     ("impressions", I), ("clicks", I)),
}
