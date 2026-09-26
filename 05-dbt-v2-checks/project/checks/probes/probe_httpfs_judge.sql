-- Can check SQL call a judge over HTTP? Loads httpfs from a local file ($HTTPFS_EXT) and asks
-- the mock judge ($MOCK_JUDGE_URL, probes/mock_judge_server.py) about one column.
-- One row = the judge was reached and said the description does not match.
load '{{ env_var("HTTPFS_EXT", "httpfs") }}';
select 'order_total' as column_name, 'customer email' as description, ok
from read_json('{{ env_var("MOCK_JUDGE_URL", "http://127.0.0.1:8765/judge") }}?name=order_total&description=customer%20email')
where not ok
