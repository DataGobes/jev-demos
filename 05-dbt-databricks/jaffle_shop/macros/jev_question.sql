{#-
  Building blocks shared by the jev_expect test and the jev_judge post-hook. The test finds the
  hook's judgments by key, so both MUST build the question, state and key through these macros.
-#}

{% macro jev_mode() %}
  {%- set mode = (env_var('JEV_MODE', var('jev_mode', 'live')) | string | lower) -%}
  {%- if mode not in ['live', 'demo'] -%}
    {{ exceptions.raise_compiler_error("jev: JEV_MODE must be 'live' or 'demo', got '" ~ mode ~ "'") }}
  {%- endif -%}
  {{ return(mode) }}
{% endmacro %}

{% macro jev_relation(name) %}
  {{ return(var('jev_catalog') ~ '.' ~ var('jev_schema') ~ '.' ~ name) }}
{% endmacro %}

{% macro jev_function() %}
  {{ return(jev_relation('noul_pack' if jev_mode() == 'live' else 'noul_pack_demo')) }}
{% endmacro %}

{% macro jev_sql_string(s) %}
  {{ return("'" ~ (s | string | replace("\\", "\\\\") | replace("'", "\\'")) ~ "'") }}
{% endmacro %}

{% macro jev_rewrite(text) %}
  {%- if text is none -%}{{ return(none) }}{%- endif -%}
  {{ return(modules.re.sub('`([A-Za-z_][A-Za-z0-9_]*)`', '`record.\\1`', text | string)) }}
{% endmacro %}

{% macro jev_question(fails_if, criteria=none) %}
  {%- if fails_if is not string or not (fails_if | trim) -%}
    {{ exceptions.raise_compiler_error("jev_expect: `fails_if` must be a non-empty sentence") }}
  {%- endif -%}
  {%- set question = {"instructions": jev_rewrite(fails_if)} -%}
  {%- if criteria is not none -%}
    {%- set normalized = {} -%}
    {%- for key, value in criteria.items() -%}
      {%- set k = (key | string | lower) -%}
      {%- if k not in ["true", "false"] -%}
        {{ exceptions.raise_compiler_error("jev_expect: `criteria` keys must be true/false, got " ~ key) }}
      {%- endif -%}
      {%- do normalized.update({k: jev_rewrite(value)}) -%}
    {%- endfor -%}
    {%- do question.update({"criteria": normalized}) -%}
  {%- endif -%}
  {{ return(tojson(question)) }}
{% endmacro %}

{% macro jev_state_expr(column_name, context=[]) %}
  {%- set parts = [] -%}
  {%- for f in [column_name] + (context or []) -%}
    {%- do parts.append("'" ~ f ~ "', " ~ adapter.quote(f)) -%}
  {%- endfor -%}
  {{ return("to_json(named_struct(" ~ (parts | join(", ")) ~ "))") }}
{% endmacro %}

{% macro jev_key_expr(state_expr, question_json) %}
  {{ return("sha2(concat_ws(chr(31), " ~ jev_sql_string(var('jev_model')) ~ ", "
            ~ jev_sql_string(jev_mode()) ~ ", 'nested', " ~ jev_sql_string(question_json)
            ~ ", " ~ state_expr ~ "), 256)") }}
{% endmacro %}
