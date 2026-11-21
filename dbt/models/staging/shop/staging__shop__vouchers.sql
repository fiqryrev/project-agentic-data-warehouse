select distinct
    voucher_code, discount_pct, max_discount_idr, min_spend_idr, valid_from, valid_to, _dt
from {{ source('lake', 'shop__vouchers') }}
