{% macro jev_summary() %}
  {%- if execute -%}
    {%- set result = run_query("select jev_stats()") -%}
    {%- set stats = fromjson(result.columns[0].values()[0]) -%}
    {%- if stats["judgments"] > 0 -%}
      {#- Persist the stats JSON so scripts/score.py can show LIVE/SIMULATED provenance and the
          gate line even when called without --run. This reflects the last dbt invocation that
          made judgments -- the same invocation the stored-failure tables above were written by,
          since both are written within that run. #}
      {%- do run_query("create schema if not exists main_dbt_test__audit") -%}
      {%- do run_query(
            "create or replace table main_dbt_test__audit.jev_last_run as select jev_stats() as stats"
          ) -%}
      {%- do log(stats["summary"], info=True) -%}
    {%- endif -%}
  {%- endif -%}
{% endmacro %}
