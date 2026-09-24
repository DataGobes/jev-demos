"""dbt-duckdb plugin: `plugins: [{module: jevdbt.plugin, config: {...}}]` in profiles.yml."""

from __future__ import annotations

from typing import Any

from dbt.adapters.duckdb.plugins import BasePlugin

from jevdbt.runtime import get_runtime
from jevdbt.udf import register


class Plugin(BasePlugin):
    def initialize(self, plugin_config: dict[str, Any]) -> None:
        self._config = dict(plugin_config)

    def configure_connection(self, conn: Any) -> None:
        register(conn, get_runtime(self._config))
