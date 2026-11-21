select
    settlement_id, seller_id, settlement_date, gross_sales_idr, commission_idr, payout_idr,
    {{ dbt_audit_columns() }}
from {{ ref('staging__ledger__settlements') }}
