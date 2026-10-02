{#-
  Semantic test: returns the rows whose judgment p >= threshold, plus rows that have no judgment
  yet (jev_p is NULL: run `dbt build` so the jev_judge post-hook can judge them). Judgments are
  made by the post-hook on the tested model and stored in jev_demo.jev.judgments; this test only
  reads them, so it stays an ordinary dbt test.
  Each returned row also says which mode (live|demo) and which dbt invocation wrote it
  (jev_mode, jev_invocation_id): in a `dbt build` the test and the judging hook share the
  invocation, so scripts/score.py and show.py can tell stored failures of the scored run from
  stale or SIMULATED ones.
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
  select key, p from {{ jev_relation('judgments') }} where p is not null
)
select tested.* except (__jev_key), judged.p as jev_p,
       {{ jev_sql_string(jev_mode()) }} as jev_mode,
       {{ jev_sql_string(invocation_id) }} as jev_invocation_id
from tested
left join judged on judged.key = tested.__jev_key
where judged.p is null or judged.p >= {{ threshold }}
{% endtest %}
