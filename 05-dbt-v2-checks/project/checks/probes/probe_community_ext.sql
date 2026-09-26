-- Does dbt pass INSTALL ... FROM community through to DuckDB? (Download is blocked in the
-- sandbox; what matters is whether DuckDB, not dbt, is what refuses.)
install shellfs from community;
select 1 as installed
