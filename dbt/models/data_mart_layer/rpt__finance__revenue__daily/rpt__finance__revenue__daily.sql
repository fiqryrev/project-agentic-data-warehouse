-- Revenue per day as the two systems see it: money the shop received, and the ledger's
-- gross, refunds, PPN and net revenue on the invoice date.
with shop as (
    select paid_date as revenue_date, sum(amount_idr) as shop_paid_idr
    from {{ ref('fact__sales__payments') }}
    group by 1
),
ledger as (
    select
        invoice_date as revenue_date,
        count(*) as invoice_count,
        sum(gross_idr) as ledger_gross_idr,
        sum(refund_idr) as ledger_refund_idr,
        sum(tax_idr) as ledger_tax_idr,
        sum(net_revenue_idr) as net_revenue_idr
    from {{ ref('fact__finance__invoices') }}
    group by 1
)
select
    revenue_date,
    coalesce(l.invoice_count, 0) as invoice_count,
    coalesce(s.shop_paid_idr, 0) as shop_paid_idr,
    coalesce(l.ledger_gross_idr, 0) as ledger_gross_idr,
    coalesce(l.ledger_refund_idr, 0) as ledger_refund_idr,
    coalesce(l.ledger_tax_idr, 0) as ledger_tax_idr,
    coalesce(l.net_revenue_idr, 0) as net_revenue_idr,
    {{ dbt_audit_columns() }}
from shop s
full outer join ledger l using (revenue_date)
