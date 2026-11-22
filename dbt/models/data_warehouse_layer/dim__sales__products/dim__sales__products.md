{% docs dim__sales__products %}

Products with price history: one row per price version, the first when the product is created
and another each time it is repriced, valid from `valid_from_at` until `valid_to_at`. Each row
carries the seller and the category name and group. Analysts use it to read the price a line was
sold at (through `product_version_key` on `fact__sales__order_items`), to track price changes, and
to roll sales up by category or seller.

## Potential Analyses

1. **Sales by category** -- join `fact__sales__order_items` on `product_version_key` and sum `line_amount_idr` by `parent_name` or `category_name`.
2. **Price change history** -- per `product_id`, order by `valid_from_at` and compare `price_idr` with `lag(price_idr)` to get each repricing and its factor.
3. **Current catalogue** -- filter `is_current` for one row per product with today's price; count per `seller_id` or `category_name`.
4. **Seller sales** -- join `fact__sales__order_items` on `product_version_key`, group by `seller_id`, and join `dim__sales__sellers` for the name.
5. **Price on a given day** -- filter `valid_from_at::date <= :day and (valid_to_at is null or valid_to_at::date > :day)`.

## Grain

One row per `product_version_key` (equivalently, per `product_id` and `valid_from_at`).

## Table Lineage

```
dim__sales__products
├── staging__shop__products            (staging)
│   └── lake.shop__products            (lake)
└── staging__shop__categories          (staging)
    └── lake.shop__categories          (lake)
```

## Units and Conventions

- `price_idr` is the list price in whole rupiah, PPN included.
- Timestamps `_at` are naive UTC; `valid_to_at` is null on the current version, and `is_current` is true on exactly one version per product (`scd2_valid`).
- `product_version_key` is `md5(product_id || '|' || updated_at)`.
- The ledger writes the seller as `seller_ref` `S-00007`; here it is the numeric `seller_id`.

## Known Caveats

- Counting rows counts price versions, not products; use `count(distinct product_id)` or filter `is_current`.
- Order lines match a version by order day, not timestamp: the shop prices a whole day at one price, so a repricing during a day applies to that whole day. Every line's `unit_price_idr` equals the matched version's `price_idr` (test `assert_order_item_price_matches_product_version`).
- Orphan product ids (from 9,000,000) on order lines have no row here (da-0004); joins from `fact__sales__order_items` must be left joins or those lines drop out.
- Category name and group come from the current category list, not a history of it.

## Refresh Cadence

Rebuilt by the daily dbt build.

## Change History

| Version | Date | Author | Summary |
| --- | --- | --- | --- |
| 1.0.0 | 2026-11-22 | data-engineering | Initial doc block. |

{% enddocs %}
