{{ config(tags=['production']) }}
select cast(id as bigint) as review_id,
       cast(stars as int) as stars,
       concat_ws('\n', summary, text) as body
from read_files('/Volumes/jev_demo/production/raw/', format => 'parquet')
