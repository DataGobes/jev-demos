{{ config(tags=['production']) }}
{%- set volume = '/Volumes/' ~ var('jev_catalog') ~ '/production/raw/' %}
select cast(id as bigint) as review_id,
       cast(stars as int) as stars,
       concat_ws('\n', summary, text) as body
from read_files({{ jev_sql_string(volume) }}, format => 'parquet')
