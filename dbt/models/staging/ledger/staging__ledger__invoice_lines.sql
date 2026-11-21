select distinct
    invoice_id, line_no, product_ref as product_id, quantity, line_amount_idr, _dt
from {{ source('lake', 'ledger__invoice_lines') }}
