{% docs dim__sales__sellers %}

Sellers on the marketplace, one row per seller, with the shop name, city, province and creation
time. The source writes a seller once, on the day it is created, and sellers do not change, so
there is no history. Analysts use it to name sellers and to group sales and payouts by seller
location.

## Potential Analyses

1. **Payouts by seller** -- join `fact__finance__settlements` on `seller_id`, sum `payout_idr` and `commission_idr` per `seller_name`.
2. **Sales by seller city** -- join `dim__sales__products` on `seller_id`, then `fact__sales__order_items` on `product_version_key`, and sum `line_amount_idr` by `city_name`.
3. **Seller growth** -- count `seller_id` by `created_at::date` or month.
4. **Sellers with no sales** -- left join `fact__finance__settlements` on `seller_id` and keep rows with no settlement in a period.

## Grain

One row per `seller_id`.

## Table Lineage

```
dim__sales__sellers
└── staging__shop__sellers          (data_staging_layer)
    └── data_lake_layer.shop__sellers          (data_lake_layer)
```

## Units and Conventions

- `created_at` is naive UTC.
- The ledger writes the seller as `seller_ref` `S-00007`; here it is the numeric `seller_id`.
- Seller names are fictional.

## Known Caveats

- No history: if a seller ever changed city, only the written version would show. The generator never changes a seller.
- No defect in `generator/DEFECTS.md` touches sellers.

## Refresh Cadence

Rebuilt by the daily dbt build.

## Change History

| Version | Date | Author | Summary |
| --- | --- | --- | --- |
| 1.0.0 | 2026-11-22 | data-engineering | Initial doc block. |

{% enddocs %}
