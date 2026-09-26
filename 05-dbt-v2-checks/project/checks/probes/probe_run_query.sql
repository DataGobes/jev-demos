-- What run_query and `execute` give a check while it renders at parse time.
{%- set result = run_query("select 42 as answer") %}
select
    '{{ execute }}'                     as execute_flag,
    '{{ result is none }}'              as run_query_is_none,
    '{{ (result.rows | length) if result is not none else "n/a" }}' as run_query_rows
