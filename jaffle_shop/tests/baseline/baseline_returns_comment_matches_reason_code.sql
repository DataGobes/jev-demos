{{ config(tags=['baseline'], store_failures=true, severity='warn') }}
with keyworded as (
  select *,
    case
      when regexp_matches(comment, '(?i)(broken|burnt|burned|crushed|squashed|leak|spilled|damaged|soggy|mould|mold|raw)') then 'damaged'
      when regexp_matches(comment, '(?i)(wrong|instead of|not what i ordered|someone else|different order|missing)') then 'wrong_item'
      when regexp_matches(comment, '(?i)(late|hours?|waited|took forever|delay|still waiting|\d+\s?min)') then 'late'
      when regexp_matches(comment, '(?i)(changed my mind|don''t need|no longer|by mistake|accident|cancel)') then 'changed_mind'
    end as keyword_code
  from {{ ref('stg_returns') }}
)
select * from keyworded
where keyword_code is not null and reason_code <> 'other' and keyword_code <> reason_code
