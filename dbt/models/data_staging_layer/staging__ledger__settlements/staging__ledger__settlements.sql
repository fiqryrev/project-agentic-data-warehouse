select distinct
    settlement_id,
    {{ key_number('seller_ref', 'S-') }} as seller_id,
    settlement_date,
    gross_sales_idr,
    commission_idr,
    payout_idr,
    _dt
from {{ source('lake', 'ledger__settlements') }}
