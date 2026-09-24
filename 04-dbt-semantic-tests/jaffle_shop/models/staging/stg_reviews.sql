select id as review_id, order_id, stars, body from {{ ref('raw_reviews') }}
