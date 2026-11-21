-- net revenue = (gross - refund) / 1.11, rounded to the rupiah.
select invoice_id
from {{ ref('fact__finance__invoices') }}
where abs(net_revenue_idr - round((gross_idr - refund_idr) / 1.11)) > 1
