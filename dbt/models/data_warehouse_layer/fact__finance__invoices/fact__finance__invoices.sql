-- Current state of each ledger invoice: its latest posting.
select
    invoice_id, order_id, customer_id, invoice_date, invoice_status, gross_idr, tax_idr,
    refund_idr, net_revenue_idr, posted_at,
    {{ dbt_audit_columns() }}
from {{ ref('staging__ledger__invoices') }}
qualify row_number() over (partition by invoice_id order by posted_at desc) = 1
