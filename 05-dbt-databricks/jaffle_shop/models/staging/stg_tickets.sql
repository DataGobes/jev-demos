select id as ticket_id, customer_id, subject, body from {{ ref('raw_tickets') }}
