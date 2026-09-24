{{ config(tags=['baseline'], store_failures=true, severity='warn') }}
select * from {{ ref('stg_customers') }}
where regexp_matches(full_name, '(?i)\b(test|dummy|asdf|qwerty|xxx|n/?a|unknown|sample|foo|bar|none|null)\b')
   or full_name like '%@%'
   or regexp_matches(full_name, '(?i)\b(bv|b\.v\.|ltd|llc|inc|gmbh|nv|co|company|holding|group)\b')
   or regexp_matches(full_name, '\d')
   or lower(first_name) = lower(last_name)
   or not regexp_matches(lower(full_name), '[aeiouy]')
