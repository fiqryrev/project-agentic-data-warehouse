select distinct spend_date, campaign_id, spend_idr, impressions, clicks, _dt
from {{ source('lake', 'marketing__daily_spend') }}
