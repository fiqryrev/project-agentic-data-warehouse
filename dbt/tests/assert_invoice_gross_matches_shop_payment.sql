-- The ledger invoices exactly what the shop received for each paid order.
select f.invoice_id, f.gross_idr, p.amount_idr
from {{ ref('fact__finance__invoices') }} f
left join {{ ref('fact__sales__payments') }} p using (order_id)
where p.amount_idr is null or p.amount_idr <> f.gross_idr
