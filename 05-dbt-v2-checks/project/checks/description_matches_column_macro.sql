-- Probe 5b: the mock judge as a DuckDB macro defined inside the check. dbt passes a DuckDB
-- check's SQL to the driver unsplit (dbt-adapter/src/adapter/adapter_impl.rs:808-818), and
-- DuckDB 1.5.4 runs every statement and returns the last one's rows (probes/probe_adbc.py).
create or replace temp macro mock_judge(col, descr) as
    coalesce(contains(lower(col), list_filter(
        string_split(regexp_replace(lower(descr), '[^a-z0-9 ]', ' ', 'g'), ' '),
        w -> length(w) >= 3 and not list_contains(
            ['the','and','for','with','from','into','per','was','were','are','this','that','its','their','which'], w)
    )[-1]), true);

select
    c.node_unique_id as unique_id,
    c.column_name,
    c.description,
    'description does not match column (mock judge, duckdb macro)' as message
from {{ info_schema('node_columns') }} as c
where coalesce(trim(c.description), '') <> ''
  and not mock_judge(c.column_name, c.description)
