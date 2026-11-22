-- Current state of each shipment.
select
    shipment_id, order_id, courier_name, shipment_status, shipped_at, delivered_at,
    {{ dbt_audit_columns() }}
from {{ ref('staging__shop__shipments') }}
qualify row_number() over (
    partition by shipment_id order by coalesce(delivered_at, shipped_at) desc, _dt desc
) = 1
