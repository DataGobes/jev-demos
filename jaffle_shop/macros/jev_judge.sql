{#-
  Post-hook on every model (dbt_project.yml): judges the states of this model's jev_expect tests
  that have no successful judgment yet, and appends them to jev_demo.jev.judgments.

  Per test: one count query, one INSERT ... SELECT that calls the UC function once per pack, one
  count of what was inserted, one hook_runs row. Raises if inserted != missing.
  Packs are cut by estimated tokens (budget) and a row cap; REPARTITION(n) caps how many packs run
  at once (the function is Arrow-batched: packs in one partition run one after another).
-#}

{% macro jev_tests_for(node_id) %}
  {%- set tests = [] -%}
  {%- for n in graph.nodes.values() -%}
    {%- if n.resource_type == 'test' and n.attached_node == node_id
          and n.test_metadata and n.test_metadata.name == 'jev_expect'
          and n.config.enabled -%}
      {%- do tests.append(n) -%}
    {%- endif -%}
  {%- endfor -%}
  {{ return(tests | sort(attribute='name')) }}
{% endmacro %}

{% macro jev_judge_sql(t, relation) %}
  {%- set kw = t.test_metadata.kwargs -%}
  {%- set column = kw['column_name'] -%}
  {%- set context = kw.get('context') or [] -%}
  {%- set question = jev_question(kw['fails_if'], kw.get('criteria')) -%}
  {%- set state = jev_state_expr(column, context) -%}
  {%- set key = jev_key_expr(state, question) -%}
  {%- set judgments = jev_relation('judgments') -%}
  {%- set limit = var('jev_row_token_limit') -%}
  {%- set model_lit = jev_sql_string(var('jev_model')) -%}
  {%- set result_schema = "values ARRAY<DOUBLE>, input_tokens BIGINT, model STRING, error STRING, attempts INT, retries ARRAY<STRUCT<attempt: INT, status: INT, t: DOUBLE>>, pack_uuid STRING, started DOUBLE, finished DOUBLE" -%}
  {%- set common -%}
with tested as (
  select distinct {{ key }} as key, {{ state }} as state
  from {{ relation }}
  where {{ adapter.quote(column) }} is not null
),
missing as (
  select tested.key, tested.state,
         cast(ceil((length(tested.state) + {{ question | length }}) / 3.0) + 20 as bigint) as est
  from tested
  {#- `question = ...` changes no result (the key contains the question). It scopes this read so
      that Delta row-level concurrency does not treat other hooks' concurrent appends (other
      questions, other dbt threads) as conflicts: DELTA_CONCURRENT_APPEND.ROW_LEVEL_CHANGES. #}
  left anti join (
    select key from {{ judgments }} where p is not null and question = {{ jev_sql_string(question) }}
  ) done
    on done.key = tested.key
)
  {%- endset -%}
  {%- set count_sql -%}
{{ common }}
select (select count(*) from tested) as tested,
       count(*) as missing,
       count_if(est > {{ limit }}) as oversized
from missing
  {%- endset -%}
  {%- set insert_sql -%}
insert into {{ judgments }} (
  key, test_name, model_name, question, state, p, requested_model, answered_model, mode, layout,
  pack_uuid, pack_rows, pack_tokens, pack_est_tokens, attempts, retry_statuses, error,
  started_at, finished_at, invocation_id, judged_at
)
{{ common }},
fit as (select * from missing where est <= {{ limit }}),
bucketed as (
  select key, state, est,
         floor((sum(est) over (order by key rows between unbounded preceding and current row) - est)
               / {{ var('jev_pack_token_budget') }}) as bucket
  from fit
),
numbered as (
  select key, state, est, bucket,
         floor((row_number() over (partition by bucket order by key) - 1)
               / {{ var('jev_pack_max_rows') }}) as sub
  from bucketed
),
packs as (
  select /*+ REPARTITION({{ var('jev_max_concurrency') }}) */ bucket, sub,
         array_sort(collect_list(named_struct('key', key, 'state', state, 'est', est))) as items
  from numbered
  group by bucket, sub
),
called as (
  select items,
         from_json({{ jev_function() }}(transform(items, x -> x.state), {{ jev_sql_string(question) }}, {{ model_lit }}),
                   '{{ result_schema }}') as r
  from packs
),
exploded as (
  select r, size(items) as pack_rows,
         aggregate(items, cast(0 as bigint), (acc, x) -> acc + x.est) as pack_est, pos, item
  from called
  lateral view posexplode(items) e as pos, item
)
select item.key, {{ jev_sql_string(t.name) }}, {{ jev_sql_string(t.attached_node.split('.')[-1]) }},
       {{ jev_sql_string(question) }}, item.state, r.values[pos], {{ model_lit }}, r.model,
       {{ jev_sql_string(jev_mode()) }}, 'nested', r.pack_uuid, pack_rows, r.input_tokens, pack_est,
       r.attempts, transform(r.retries, x -> x.status), r.error,
       timestamp_seconds(r.started), timestamp_seconds(r.finished),
       {{ jev_sql_string(invocation_id) }}, current_timestamp()
from exploded
union all
select key, {{ jev_sql_string(t.name) }}, {{ jev_sql_string(t.attached_node.split('.')[-1]) }},
       {{ jev_sql_string(question) }}, state, cast(null as double), {{ model_lit }},
       cast(null as string), {{ jev_sql_string(jev_mode()) }}, 'nested', cast(null as string),
       cast(null as int), cast(null as bigint), est, cast(0 as int), cast(null as array<int>),
       concat('row exceeds token limit (est ', est, ' tokens > {{ limit }})'),
       cast(null as timestamp), cast(null as timestamp),
       {{ jev_sql_string(invocation_id) }}, current_timestamp()
from missing
where est > {{ limit }}
  {%- endset -%}
  {%- set inserted_sql -%}
select count(*) from {{ judgments }}
where invocation_id = {{ jev_sql_string(invocation_id) }} and test_name = {{ jev_sql_string(t.name) }}
  {%- endset -%}
  {{ return({"count": count_sql, "insert": insert_sql, "inserted": inserted_sql}) }}
{% endmacro %}

{% macro jev_judge() %}
  {%- if not execute or flags.WHICH not in ['run', 'build'] -%}{{ return('') }}{%- endif -%}
  {%- for t in jev_tests_for(model.unique_id) -%}
    {%- set s = jev_judge_sql(t, this) -%}
    {%- set c = run_query(s['count']) -%}
    {%- set tested = c.columns[0].values()[0] | int -%}
    {%- set missing = c.columns[1].values()[0] | int -%}
    {%- set oversized = c.columns[2].values()[0] | int -%}
    {%- if missing > 0 -%}{%- do run_query(s['insert']) -%}{%- endif -%}
    {%- set inserted = run_query(s['inserted']).columns[0].values()[0] | int -%}
    {%- do run_query("insert into " ~ jev_relation('hook_runs') ~ " values ("
          ~ jev_sql_string(invocation_id) ~ ", " ~ jev_sql_string(t.name) ~ ", "
          ~ jev_sql_string(model.name) ~ ", " ~ jev_sql_string(jev_mode()) ~ ", "
          ~ jev_sql_string(var('jev_model')) ~ ", " ~ tested ~ ", " ~ missing ~ ", "
          ~ oversized ~ ", " ~ inserted ~ ", current_timestamp())") -%}
    {%- do log("Jev · " ~ ('SIMULATED' if jev_mode() == 'demo' else 'LIVE') ~ " · " ~ t.name ~ " · "
              ~ tested ~ " tested · " ~ (missing - oversized) ~ " judged now · "
              ~ oversized ~ " too long", info=True) -%}
    {%- if inserted != missing -%}
      {{ exceptions.raise_compiler_error("jev_judge: " ~ t.name ~ ": inserted " ~ inserted
          ~ " rows for " ~ missing ~ " missing states (one evaluation per row violated)") }}
    {%- endif -%}
  {%- endfor -%}
  {{ return('') }}
{% endmacro %}
