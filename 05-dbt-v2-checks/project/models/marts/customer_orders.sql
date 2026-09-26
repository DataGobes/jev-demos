select
    c.customer_id,
    min(o.order_date)  as first_order_date,
    count(o.order_id)  as order_count,
    sum(o.order_total) as lifetime_value
from {{ ref('stg_customers') }} as c
left join {{ ref('stg_orders') }} as o on o.customer_id = c.customer_id
group by c.customer_id
