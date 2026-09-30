"""Minimal Statement Execution API client on databricks-sdk (auth: CLI profile, OAuth)."""

import os
import time
from dataclasses import dataclass, field

DEFAULT_PROFILE = "jev-demo-5"
DEFAULT_WAREHOUSE = "jev-demo-5"
_DONE = {"SUCCEEDED", "FAILED", "CANCELED", "CLOSED"}


@dataclass
class Result:
    state: str
    columns: list[str] = field(default_factory=list)
    rows: list[list] = field(default_factory=list)
    error: str | None = None
    statement_id: str | None = None
    wall_s: float = 0.0

    def scalar(self):
        return self.rows[0][0] if self.rows else None


def _client(profile: str | None):
    from databricks.sdk import WorkspaceClient

    return WorkspaceClient(
        profile=profile or os.environ.get("DATABRICKS_CONFIG_PROFILE", DEFAULT_PROFILE))


def resolve_warehouse_id(client, name_or_id: str) -> str:
    for w in client.warehouses.list():
        if name_or_id in (w.name, w.id):
            return w.id
    raise LookupError(f"no SQL warehouse named or with id {name_or_id!r}")


def dbt_env(
    profile: str | None = None, warehouse: str | None = None, *, client=None
) -> dict[str, str]:
    """Environment for running dbt against the workspace: host, warehouse HTTP path and a
    short-lived bearer token from the CLI profile's auth. Never print or log the result."""
    client = client or _client(profile)
    host = client.config.host.removeprefix("https://").rstrip("/")
    auth = client.config.authenticate() or {}
    scheme, _, token = (auth.get("Authorization") or "").partition(" ")
    if scheme != "Bearer" or not token:
        raise RuntimeError(
            "the Databricks CLI profile did not yield a bearer token; "
            "run `databricks auth login` for the profile and retry")
    wid = resolve_warehouse_id(
        client, warehouse or os.environ.get("JEV_WAREHOUSE", DEFAULT_WAREHOUSE))
    return {
        "DATABRICKS_HOST": host,
        "JEV_HTTP_PATH": f"/sql/1.0/warehouses/{wid}",
        "DBT_DATABRICKS_TOKEN": token,
    }


class Sql:
    def __init__(self, profile: str | None = None, warehouse: str | None = None, *,
                 client=None, warehouse_id: str | None = None):
        self.client = client or _client(profile)
        self.warehouse_id = warehouse_id or resolve_warehouse_id(
            self.client, warehouse or os.environ.get("JEV_WAREHOUSE", DEFAULT_WAREHOUSE))

    def run(self, sql: str, timeout_s: float = 900) -> Result:
        se = self.client.statement_execution
        t0 = time.monotonic()
        resp = se.execute_statement(statement=sql, warehouse_id=self.warehouse_id,
                                    wait_timeout="50s", on_wait_timeout=_continue())
        while _state(resp) not in _DONE:
            if time.monotonic() - t0 > timeout_s:
                se.cancel_execution(resp.statement_id)
                return Result("CANCELED", error=f"timed out after {timeout_s:.0f} s",
                              statement_id=resp.statement_id, wall_s=time.monotonic() - t0)
            time.sleep(2)
            resp = se.get_statement(resp.statement_id)
        res = Result(_state(resp), statement_id=resp.statement_id, wall_s=time.monotonic() - t0)
        if res.state != "SUCCEEDED":
            err = getattr(resp.status, "error", None)
            res.error = getattr(err, "message", None) or str(err)
            return res
        manifest = resp.manifest
        has_schema = manifest and manifest.schema
        res.columns = [c.name for c in manifest.schema.columns] if has_schema else []
        result = resp.result
        rows = list(result.data_array or []) if result else []
        nxt = getattr(result, "next_chunk_index", None) if result else None
        while nxt is not None:
            chunk = se.get_statement_result_chunk_n(resp.statement_id, nxt)
            rows.extend(chunk.data_array or [])
            nxt = chunk.next_chunk_index
        res.rows = rows
        return res


def _state(resp) -> str:
    state = resp.status.state
    return getattr(state, "value", state)


def _continue():
    try:
        from databricks.sdk.service.sql import ExecuteStatementRequestOnWaitTimeout

        return ExecuteStatementRequestOnWaitTimeout.CONTINUE
    except ImportError:  # older/newer SDK naming
        return "CONTINUE"
