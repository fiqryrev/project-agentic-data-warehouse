select
    s.spend_date, s.campaign_id, c.channel_name, s.spend_idr, s.impression_count, s.click_count,
    {{ dbt_audit_columns() }}
from {{ ref('staging__marketing__daily_spend') }} s
left join {{ ref('staging__marketing__campaigns') }} c using (campaign_id)
