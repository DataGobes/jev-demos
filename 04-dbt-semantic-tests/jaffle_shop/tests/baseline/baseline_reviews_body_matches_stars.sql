{{ config(tags=['baseline'], store_failures=true, severity='warn') }}
with lexicon as (
  select *,
    len(regexp_extract_all(lower(body), '\b(great|love|loved|amazing|delicious|best|perfect|excellent|fantastic|tasty|recommend|good|lovely|fresh|yum)\b'))
    - len(regexp_extract_all(lower(body), '\b(never|worst|awful|terrible|disgusting|cold|raw|bad|horrible|inedible|refund|disappointed|soggy|gross)\b'))
      as sentiment
  from {{ ref('stg_reviews') }}
)
select * from lexicon
where (stars >= 4 and sentiment < 0) or (stars <= 2 and sentiment > 0)
