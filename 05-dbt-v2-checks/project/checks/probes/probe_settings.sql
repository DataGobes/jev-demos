-- The DuckDB settings of the database dbt runs checks on. Returns rows on purpose (warn).
select name, value
from duckdb_settings()
where name in ('enable_external_access', 'allow_community_extensions', 'allow_unsigned_extensions',
               'autoinstall_known_extensions', 'autoload_known_extensions', 'lock_configuration')
order by name
