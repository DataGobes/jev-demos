"""Probe what DuckDB 1.5.4 accepts when SQL arrives the way dbt v2 sends a check.

dbt v2 runs a check by passing its whole rendered SQL string, unsplit, to one ADBC
execute on an in-memory DuckDB (dbt-adapter/src/adapter/adapter_impl.rs:808-818,
dbt-tasks-sa/src/check_adapter.rs:51-71). This opens the same engine version
(DUCKDB_DRIVER_VERSION = 1.5.4, dbt-adbc/src/lib.rs:81) through its ADBC entrypoint
and sends each probe as one execute call.
"""

from adbc_driver_duckdb import dbapi

PROBES = {
    "settings": """
        select name, value from duckdb_settings()
        where name in ('enable_external_access','allow_community_extensions',
                       'allow_unsigned_extensions','autoinstall_known_extensions',
                       'autoload_known_extensions','lock_configuration')
        order by name""",
    "single_select": "select 42 as answer",
    "multi_statement_macro": """
        create or replace macro judge(col, descr) as
            not contains(lower(col), lower(split_part(descr, ' ', -1)));
        select judge('order_total', 'customer email') as mismatch""",
    "multi_statement_macro_returns_last": """
        create or replace temp table t as select 1 as a;
        select count(*) as n from t""",
    "loaded_extensions": """
        select extension_name, loaded, installed from duckdb_extensions()
        where loaded or installed order by 1""",
    "install_httpfs": "install httpfs",
    "load_httpfs": "load httpfs",
    "install_community_shellfs": "install shellfs from community",
    "read_local_file": "select length(content) as bytes from read_text('/etc/hostname')",
    "http_read": "select count(*) from read_text('https://pypi.org/simple/duckdb/')",
}


def main() -> None:
    # A fresh in-memory database per probe, so one failure cannot abort the next
    # probe's transaction.
    for name, sql in PROBES.items():
        with dbapi.connect(":memory:") as conn:
            cur = conn.cursor()
            try:
                cur.execute(sql)
                rows = cur.fetchall()
                print(f"[OK]    {name}: {rows}")
            except Exception as e:  # noqa: BLE001 - probe reports every failure verbatim
                msg = str(e).splitlines()[0][:200]
                print(f"[ERROR] {name}: {type(e).__name__}: {msg}")
            finally:
                cur.close()


if __name__ == "__main__":
    main()
