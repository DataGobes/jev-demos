{#- pytest helpers: print macro output between markers. Offline `render` target only. -#}
{% macro jev_render_question(fails_if, criteria=none) %}
  {{ print('-- BEGIN\n' ~ jev_question(fails_if, criteria) ~ '\n-- END') }}
{% endmacro %}

{% macro jev_render_key(column_name, context, fails_if, criteria=none) %}
  {%- set q = jev_question(fails_if, criteria) -%}
  {{ print('-- BEGIN\n' ~ jev_key_expr(jev_state_expr(column_name, context), q) ~ '\n-- END') }}
{% endmacro %}
