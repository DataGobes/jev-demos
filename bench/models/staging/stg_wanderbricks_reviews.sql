{#- Databricks' own sample data: one row per distinct (comment, rating) state, plus the seeded
    planted ratings (review_rows = 0) keyed by comment hash. The natural data holds no
    contradictions (query 2026-10-01): its states are the control. -#}
with natural as (
  select comment, cast(round(rating, 1) as double) as rating, count(*) as review_rows
  from samples.wanderbricks.reviews
  where comment is not null and rating is not null
  group by comment, round(rating, 1)
),
planted as (
  select c.comment, cast(f.rating as double) as rating, cast(0 as bigint) as review_rows
  from (select distinct comment from natural) c
  join {{ ref('wanderbricks_flips') }} f on f.comment_sha256 = sha2(c.comment, 256)
)
select * from (select * from natural union all select * from planted)
{% if var('bench_scope') == 'pilot' %}
order by comment, rating limit 50
{% endif %}
