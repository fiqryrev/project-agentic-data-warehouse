{% docs shop__shipments %}

Raw shipment states from the shop. A row is written on the day the parcel is
handed to the courier and another on the day it is delivered; if both happen on the same day only
the delivered row is written. `staging__shop__shipments` reads it.

## Potential Analyses

1. **Delivery time** -- delivered rows: `delivered_at - shipped_at`, averaged by `courier`.
2. **Parcels shipped per day** -- `count(*)` of shipped or in-transit rows grouped by `_dt`.
3. **Courier mix** -- `count(distinct shipment_id)` grouped by `courier`.
4. **Still in transit** -- shipments whose latest row is not `delivered`.

## Grain

One row per `shipment_id` and `shipment_status`.

## Table Lineage

```
shop__shipments
└── data/landing/shop/shipments/dt=YYYY-MM-DD/part-0.parquet   (landing: written by generator/, loaded by loader/)
```

## Units and Conventions

- Timestamps (`_at`) are naive UTC; dates (`_date`, `_dt`) are calendar days.
- `shipment_id` equals the `order_id`.
- `delivered_at` is null on the shipped row.
- Every row carries the loader's audit columns: `_dt` (partition date the row arrived in), `_source_file` (landing file, relative to the landing folder), `_loaded_at` (when the load ran, UTC) and `_batch_id` (`<date>-<first 12 hex of the manifest SHA-256>`).
- Column names are the source's own (no renames); staging applies the warehouse names.

## Known Caveats

- Renamed status: `shipped` before 2026-06-01, `in_transit` from that date (`generator/DEFECTS.md`, da-0005).
- A parcel shipped and delivered on one day has only a delivered row, so counting shipped rows undercounts shipments; count distinct `shipment_id` instead.

## Refresh Cadence

Appended per daily partition by the loader; reloading a day replaces that `_dt` in one transaction.

## Change History

| Version | Date | Author | Summary |
| --- | --- | --- | --- |
| 1.0.0 | 2026-11-22 | data-engineering | Initial doc block. |

{% enddocs %}
