select distinct
    voucher_code, discount_pct, max_discount_idr, min_spend_idr, valid_from as valid_from_date, valid_to as valid_to_date, _dt
from {{ source('lake', 'shop__vouchers') }}
