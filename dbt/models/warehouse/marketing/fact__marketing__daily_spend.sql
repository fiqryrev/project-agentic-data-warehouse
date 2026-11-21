select
    s.spend_date, s.campaign_id, c.channel, s.spend_idr, s.impressions, s.clicks,
    {{ dbt_audit_columns() }}
from {{ ref('staging__marketing__daily_spend') }} s
left join {{ ref('staging__marketing__campaigns') }} c using (campaign_id)
