{% macro jev_render_question(fails_if, criteria=none) %}
  {{ print('-- BEGIN\n' ~ jev_question(fails_if, criteria) ~ '\n-- END') }}
{% endmacro %}

{% macro jev_render_key(column_name, context, fails_if, criteria=none) %}
  {%- set q = jev_question(fails_if, criteria) -%}
  {{ print('-- BEGIN\n' ~ jev_key_expr(jev_state_expr(column_name, context), q) ~ '\n-- END') }}
{% endmacro %}

{% macro jev_render_prompt(column_name, context, fails_if, criteria=none) %}
  {%- set q = jev_question(fails_if, criteria) -%}
  {{ print('-- BEGIN\n' ~ jev_prompt_expr(q, jev_state_expr(column_name, context)) ~ '\n-- END') }}
{% endmacro %}

{% macro jev_render_llm_call() %}
  {{ print('-- BEGIN\n' ~ jev_llm_call("'P'") ~ '\n-- END') }}
{% endmacro %}

{% macro jev_render_state(column_name, context) %}
  {{ print('-- BEGIN\n' ~ jev_state_expr(column_name, context) ~ '\n-- END') }}
{% endmacro %}

{% macro jev_render_judge(model_name) %}
  {%- set node = graph.nodes['model.bench.' ~ model_name] -%}
  {%- set parts = [] -%}
  {%- for t in jev_tests_for(node.unique_id, none) -%}
    {%- set s = jev_judge_sql(t, node.relation_name) -%}
    {%- do parts.append('-- count\n' ~ s['count'] ~ '\n-- insert\n' ~ s['insert'] ~ '\n-- inserted\n' ~ s['inserted']) -%}
  {%- endfor -%}
  {{ print('-- BEGIN\n' ~ (parts | join('\n')) ~ '\n-- END') }}
{% endmacro %}

{% macro jev_render_llm_summary(inserted, missing, dups) %}
  {%- set out = jev_llm_summary_lines({
        "judge": jev_judge_name(), "mode": jev_mode(), "tested": missing, "missing": missing,
        "inserted": inserted, "errors": 0, "span": 1.5, "dups": dups}) -%}
  {{ print('-- BEGIN\n' ~ out.line2 ~ '\nok=' ~ out.ok ~ '\n-- END') }}
{% endmacro %}
