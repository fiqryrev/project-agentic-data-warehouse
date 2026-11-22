{% docs fact__sales__order_items %}

Order lines, one row per line, each tied to the product version valid on the order day and the
customer version valid at the moment the order was placed. This is the table for "what sold, at
what price, to whom and where": `product_version_key` leads to the price, seller and category,
`customer_version_key` to the customer's city at order time. Lines are written once, on the
order's creation day, and never change.

## Potential Analyses

1. **Merchandise value by category** -- join `dim__sales__products` on `product_version_key` and sum `line_amount_idr` by `parent_name` or `category_name` and `order_date`.
2. **Sales by customer city at order time** -- join `dim__sales__customers` on `customer_version_key` and sum `line_amount_idr` by `city_name`.
3. **Top products** -- sum `item_quantity` and `line_amount_idr` per `product_id`; join `dim__sales__products` with `is_current` for today's name.
4. **Basket size** -- per `order_id`, count lines and sum `item_quantity`; then average by `order_date`.
5. **Lines of completed orders only** -- join `fact__sales__orders` on `order_id` and filter `order_status in ('paid', 'in_transit', 'delivered')`, since lines exist for cancelled and abandoned orders too.

## Grain

One row per `order_item_id`.

## Table Lineage

```
fact__sales__order_items
├── staging__shop__order_items          (data_staging_layer)
│   └── data_lake_layer.shop__order_items          (data_lake_layer)
├── staging__shop__orders               (data_staging_layer)
│   └── data_lake_layer.shop__orders               (data_lake_layer)
├── dim__sales__products                (data_warehouse_layer)
│   └── staging__shop__products         (data_staging_layer)
└── dim__sales__customers               (data_warehouse_layer)
    └── staging__shop__customers        (data_staging_layer)
```

## Units and Conventions

- Money in whole rupiah (`_idr`), PPN included. `line_amount_idr = item_quantity * unit_price_idr`.
- `order_date` is the day the order was created.
- `order_item_id` is `order_id * 10 + line number`.

## Known Caveats

- `line_amount_idr` is before voucher and shipping, so lines do not sum to what the customer paid; for money received use `fact__sales__payments` or `fact__finance__invoices`.
- Lines exist for every order, including cancelled and abandoned ones; filter on the order status before calling it sales.
- Orphan product ids (from 9,000,000, da-0004) keep a null `product_version_key`; inner joins to `dim__sales__products` drop them. The not-null test warns instead of failing.
- Products match by order day (a repricing applies to the whole day); customers match by order timestamp (a move later that day does not apply yet). Tests `assert_order_item_price_matches_product_version` and `assert_order_customer_existed_at_order_time` check both.
- When the order row is a late row still in transit (da-0003), `customer_id` and `customer_version_key` are null until it lands and `order_date` falls back to the line's partition day.

## Refresh Cadence

Rebuilt by the daily dbt build.

## Change History

| Version | Date | Author | Summary |
| --- | --- | --- | --- |
| 1.0.0 | 2026-11-22 | data-engineering | Initial doc block. |

{% enddocs %}
