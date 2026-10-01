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
  {{ return(var('jev_catalog') ~ '.' ~ var('jev_function_schema') ~ '.'
            ~ ('noul_pack' if jev_mode() == 'live' else 'noul_pack_demo')) }}
{% endmacro %}

{% macro jev_judge_name() %}
  {%- set j = var('judge', 'jev') | string -%}
  {%- if j != 'jev' and j not in var('jev_llm_endpoints') -%}
    {{ exceptions.raise_compiler_error("jev: judge must be 'jev' or one of "
        ~ (var('jev_llm_endpoints') | join(', ')) ~ ", got '" ~ j ~ "'") }}
  {%- endif -%}
  {{ return(j) }}
{% endmacro %}

{% macro jev_is_llm() %}{{ return(jev_judge_name() != 'jev') }}{% endmacro %}

{#- the model id in the cache key and the ledger: Jev's pinned version, or the endpoint name -#}
{% macro jev_judge_model() %}
  {{ return(jev_judge_name() if jev_is_llm() else var('jev_model')) }}
{% endmacro %}

{% macro jev_layout() %}{{ return('row' if jev_is_llm() else 'nested') }}{% endmacro %}

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
  {{ return("sha2(concat_ws(chr(31), " ~ jev_sql_string(jev_judge_model()) ~ ", "
            ~ jev_sql_string(jev_mode()) ~ ", " ~ jev_sql_string(jev_layout()) ~ ", "
            ~ jev_sql_string(var('jev_prompt_version')) ~ ", " ~ jev_sql_string(question_json)
            ~ ", " ~ state_expr ~ "), 256)") }}
{% endmacro %}

{#- The LLM prompt, built from the same question JSON Jev receives (single source). -#}
{% macro jev_prompt_expr(question_json, state_expr) %}
  {%- set q = fromjson(question_json) -%}
  {%- set head = "You judge one database record against a statement.\nStatement: "
                 ~ q['instructions'] ~ "\n" -%}
  {%- if q.get('criteria') -%}
    {%- set head = head ~ "Answer true when: " ~ q['criteria']['true'] ~ "\n"
                        ~ "Answer false when: " ~ q['criteria']['false'] ~ "\n" -%}
  {%- endif -%}
  {%- set head = head ~ "record = " -%}
  {%- set tail = "\nReturn JSON: \"decision\" is true if the statement holds for the record, "
                 ~ "else false; \"probability\" is your probability (0 to 1) that it holds." -%}
  {{ return("concat(" ~ jev_sql_string(head) ~ ", " ~ state_expr ~ ", " ~ jev_sql_string(tail) ~ ")") }}
{% endmacro %}

{#- One LLM call (live: ai_query; demo: the SIMULATED llm_demo). Returns the
    STRUCT<result STRING, errorMessage STRING> expression (S2: field `result`). -#}
{% macro jev_llm_call(prompt_expr) %}
  {%- set endpoint = jev_judge_name() -%}
  {%- if jev_mode() == 'demo' -%}
    {{ return(jev_relation('llm_demo') ~ "(" ~ jev_sql_string(endpoint) ~ ", " ~ prompt_expr ~ ")") }}
  {%- endif -%}
  {%- set params = "'temperature', 0.0" -%}
  {%- if endpoint in var('jev_llm_reasoning_low') -%}
    {%- set params = params ~ ", 'reasoning_effort', 'low'" -%}
  {%- endif -%}
  {{ return("ai_query(" ~ jev_sql_string(endpoint) ~ ", " ~ prompt_expr
            ~ ", responseFormat => " ~ jev_sql_string(var('jev_llm_response_format'))
            ~ ", modelParameters => named_struct(" ~ params ~ "), failOnError => false)") }}
{% endmacro %}
