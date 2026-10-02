select id as customer_id, first_name, last_name,
       trim(concat_ws(' ', first_name, last_name)) as full_name, email
from {{ ref('raw_customers') }}
