-- Step 3: the trivial check. Every model column needs a description. 0 rows = pass.
select
    c.node_unique_id as unique_id,
    c.column_name,
    'column has no description' as message
from {{ info_schema('node_columns') }} as c
join {{ info_schema('models') }} as m on m.unique_id = c.node_unique_id
where coalesce(trim(c.description), '') = ''
