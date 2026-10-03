{#- Banking77 with planted intent swaps applied; scope: pilot (50 of the sample) | sample | full -#}
with raw as (
  select query_id, split, query, intent
  from read_files('/Volumes/jev_demo/bench/raw/banking77.parquet', format => 'parquet')
),
labelled as (
  select raw.query_id, raw.split, raw.query, coalesce(r.labelled_intent, raw.intent) as intent
  from raw left join {{ ref('banking77_relabel') }} r on r.query_id = raw.query_id
)
select * from labelled
{% if var('bench_scope') == 'sample' %}
where query_id in (select query_id from {{ ref('banking77_sample') }})
{% elif var('bench_scope') == 'pilot' %}
where query_id in (select query_id from {{ ref('banking77_sample') }} order by query_id limit 50)
{% endif %}
