{{ config(tags=['baseline'], store_failures=true, severity='warn') }}
{#- flags a query that mentions none of its intent's words (longer than 2 letters) -#}
select query_id, query, intent
from {{ ref('stg_banking_queries') }}
where size(filter(split(intent, '_'), w -> length(w) > 2 and lower(query) like concat('%', w, '%'))) = 0
