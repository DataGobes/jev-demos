{% macro jev_summary() %}
  {%- if execute -%}
    {%- set result = run_query("select jev_stats()") -%}
    {%- set stats = fromjson(result.columns[0].values()[0]) -%}
    {%- if stats["judgments"] > 0 -%}
      {%- do log(stats["summary"], info=True) -%}
    {%- endif -%}
  {%- endif -%}
{% endmacro %}
