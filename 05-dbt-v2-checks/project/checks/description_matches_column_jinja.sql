-- Probe 5a: the mock judge inlined by a Jinja macro (macros/mock_judge.sql).
-- Sees name + description only: at parse a check cannot read model SQL
-- (raw_code/compiled_code are not in the parse-safe `models` view).
select
    c.node_unique_id as unique_id,
    c.column_name,
    c.description,
    'description does not match column (mock judge, jinja)' as message
from {{ info_schema('node_columns') }} as c
where coalesce(trim(c.description), '') <> ''
  and not {{ mock_judge_matches('c.column_name', 'c.description') }}
