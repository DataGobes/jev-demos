select
    order_date         as revenue_date,
    sum(order_total)   as daily_revenue,
    count(*)           as order_count
from {{ ref('stg_orders') }}
where status <> 'returned'
group by order_date
