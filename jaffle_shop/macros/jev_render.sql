{#- pytest helpers: print macro output between markers. Offline `render` target only. -#}
{% macro jev_render_question(fails_if, criteria=none) %}
  {{ print('-- BEGIN\n' ~ jev_question(fails_if, criteria) ~ '\n-- END') }}
{% endmacro %}

{% macro jev_render_key(column_name, context, fails_if, criteria=none) %}
  {%- set q = jev_question(fails_if, criteria) -%}
  {{ print('-- BEGIN\n' ~ jev_key_expr(jev_state_expr(column_name, context), q) ~ '\n-- END') }}
{% endmacro %}

{% macro jev_render_judge(model_name) %}
  {%- set node = graph.nodes['model.jaffle_shop.' ~ model_name] -%}
  {%- set parts = [] -%}
  {%- for t in jev_tests_for(node.unique_id) -%}
    {%- set s = jev_judge_sql(t, node.relation_name) -%}
    {%- do parts.append('-- count\n' ~ s['count'] ~ '\n-- insert\n' ~ s['insert'] ~ '\n-- inserted\n' ~ s['inserted']) -%}
  {%- endfor -%}
  {{ print('-- BEGIN\n' ~ (parts | join('\n')) ~ '\n-- END') }}
{% endmacro %}
