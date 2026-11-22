select distinct
    invoice_id, line_no as line_number, product_ref as product_id, quantity as item_quantity, line_amount_idr, _dt
from {{ source('lake', 'ledger__invoice_lines') }}
