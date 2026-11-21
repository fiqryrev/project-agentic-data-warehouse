select
    campaign_id, campaign_name, channel, start_date, end_date, budget_idr,
    {{ dbt_audit_columns() }}
from {{ ref('staging__marketing__campaigns') }}
