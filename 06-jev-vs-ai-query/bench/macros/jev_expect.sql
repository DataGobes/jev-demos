{#-
  Semantic test: returns rows the judge flags, plus rows with no successful judgment yet
  (jev_p and jev_decision NULL). Jev flags p >= threshold; an LLM flags decision = true.
  Judgments come from the jev_judge post-hook; the key includes the judge, so each judge's
  judgments are separate. Rows carry the judge, mode and invocation that wrote them.
-#}
{% test jev_expect(model, column_name, fails_if, context=[], threshold=0.5, criteria=none) %}
  {%- if threshold is not number or threshold <= 0 or threshold > 1 -%}
    {{ exceptions.raise_compiler_error("jev_expect: `threshold` must be in (0, 1], got " ~ threshold) }}
  {%- endif -%}
  {%- set question = jev_question(fails_if, criteria) -%}
  {%- set key = jev_key_expr(jev_state_expr(column_name, context), question) -%}

with tested as (
  select *, {{ key }} as __jev_key
  from {{ model }}
  where {{ adapter.quote(column_name) }} is not null
),
judged as (
  select key, p, decision from {{ jev_relation('judgments') }}
  where p is not null or decision is not null
)
select tested.* except (__jev_key), judged.p as jev_p, judged.decision as jev_decision,
       {{ jev_sql_string(jev_judge_name()) }} as jev_judge,
       {{ jev_sql_string(jev_mode()) }} as jev_mode,
       {{ jev_sql_string(invocation_id) }} as jev_invocation_id
from tested
left join judged on judged.key = tested.__jev_key
where judged.key is null
   or ({{ 'judged.decision = true' if jev_is_llm() else 'judged.p >= ' ~ threshold }})
{% endtest %}
