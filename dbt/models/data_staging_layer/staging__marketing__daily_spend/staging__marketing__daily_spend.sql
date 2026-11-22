select distinct spend_date, campaign_id, spend_idr, impressions as impression_count, clicks as click_count, _dt
from {{ source('lake', 'marketing__daily_spend') }}
