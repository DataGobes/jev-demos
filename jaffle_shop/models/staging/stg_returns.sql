select id as return_id, order_id, reason_code, comment from {{ ref('raw_returns') }}
