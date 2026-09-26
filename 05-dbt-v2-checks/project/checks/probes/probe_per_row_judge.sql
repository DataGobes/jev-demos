-- Can check SQL call the judge once per column? (read_json with a per-row URL.)
load '{{ env_var("HTTPFS_EXT", "httpfs") }}';
select c.node_unique_id as unique_id, c.column_name, j.ok
from {{ info_schema('node_columns') }} as c,
     read_json('{{ env_var("MOCK_JUDGE_URL", "http://127.0.0.1:8765/judge") }}?name=' || c.column_name || '&description=' || c.description) as j
where not j.ok
