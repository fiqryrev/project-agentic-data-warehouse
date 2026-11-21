-- One row per invoice posting. Ledger keys are turned back into the shop's numeric ids.
select distinct
    invoice_id,
    {{ key_number('order_ref', 'ORD-') }} as order_id,
    {{ key_number('cust_ref', 'C-') }} as customer_id,
    invoice_date,
    invoice_status,
    gross_idr,
    tax_idr,
    refund_idr,
    net_revenue_idr,
    posted_at,
    _dt
from {{ source('lake', 'ledger__invoices') }}
