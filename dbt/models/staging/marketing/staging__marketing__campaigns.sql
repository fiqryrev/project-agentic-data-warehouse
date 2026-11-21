select distinct
    campaign_id, campaign_name, channel, start_date, end_date, budget_idr, _dt
from {{ source('lake', 'marketing__campaigns') }}
