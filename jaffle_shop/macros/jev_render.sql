{#- pytest helpers: print macro output between markers. Offline `render` target only. -#}
{% macro jev_render_question(fails_if, criteria=none) %}
  {{ print('-- BEGIN\n' ~ jev_question(fails_if, criteria) ~ '\n-- END') }}
{% endmacro %}

{% macro jev_render_key(column_name, context, fails_if, criteria=none) %}
  {%- set q = jev_question(fails_if, criteria) -%}
  {{ print('-- BEGIN\n' ~ jev_key_expr(jev_state_expr(column_name, context), q) ~ '\n-- END') }}
{% endmacro %}

{#- `selected_names`: optional list of node names; stands in for dbt's selected_resources (which
    holds unique_ids) when given -- see jev_tests_for. -#}
{% macro jev_render_judge(model_name, selected_names=none) %}
  {%- set node = graph.nodes['model.jaffle_shop.' ~ model_name] -%}
  {%- set selected = none -%}
  {%- if selected_names is not none -%}
    {%- set selected = [] -%}
    {%- for n in graph.nodes.values() -%}
      {%- if n.name in selected_names -%}{%- do selected.append(n.unique_id) -%}{%- endif -%}
    {%- endfor -%}
  {%- endif -%}
  {%- set parts = [] -%}
  {%- for t in jev_tests_for(node.unique_id, selected) -%}
    {%- set s = jev_judge_sql(t, node.relation_name) -%}
    {%- do parts.append('-- count\n' ~ s['count'] ~ '\n-- insert\n' ~ s['insert'] ~ '\n-- inserted\n' ~ s['inserted']) -%}
  {%- endfor -%}
  {{ print('-- BEGIN\n' ~ (parts | join('\n')) ~ '\n-- END') }}
{% endmacro %}

{% macro jev_render_summary_lines(s) %}
  {%- set out = jev_summary_lines(s) -%}
  {{ print('-- BEGIN\n' ~ out.line1 ~ '\n' ~ out.line2 ~ '\n' ~ out.ok ~ '\n-- END') }}
{% endmacro %}
