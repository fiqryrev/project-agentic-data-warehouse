-- The full category list arrives every day; keep the latest copy of each category.
select category_id, category_name, parent_name, _dt
from {{ source('lake', 'shop__categories') }}
qualify row_number() over (partition by category_id order by _dt desc) = 1
