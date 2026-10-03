{{ config(tags=['baseline'], store_failures=true, severity='warn') }}
{#- flags a pair whose token-Jaccard similarity reaches the threshold fit on the train split -#}
with t as (
  select cast(value as double) as threshold from {{ ref('baseline_params') }}
  where name = 'abt_jaccard_threshold'
),
tok as (
  select pair_id,
         array_distinct(filter(split(regexp_replace(lower(replace(left_record, '-', '')), '[^a-z0-9]+', ' '), ' '), x -> x != '')) as a,
         array_distinct(filter(split(regexp_replace(lower(replace(right_record, '-', '')), '[^a-z0-9]+', ' '), ' '), x -> x != '')) as b
  from {{ ref('stg_product_pairs') }}
)
select pair_id, size(array_intersect(a, b)) / size(array_union(a, b)) as jaccard
from tok, t
where size(array_union(a, b)) > 0
  and size(array_intersect(a, b)) / size(array_union(a, b)) >= t.threshold
