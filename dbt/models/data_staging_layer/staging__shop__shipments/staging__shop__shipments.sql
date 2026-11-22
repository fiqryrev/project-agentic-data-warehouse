-- One row per shipment state; `shipped` is renamed `in_transit` across history.
select distinct
    shipment_id,
    order_id,
    courier as courier_name,
    case when shipment_status = 'shipped' then 'in_transit' else shipment_status end
        as shipment_status,
    shipped_at,
    delivered_at,
    _dt
from {{ source('lake', 'shop__shipments') }}
