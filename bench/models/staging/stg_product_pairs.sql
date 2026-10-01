{#- Candidate pairs, two product records per row; no labels. sample = the test split -#}
select pair_id, split, left_record, right_record
from read_files('/Volumes/jev_demo/bench/raw/abt_buy_pairs.parquet', format => 'parquet')
{% if var('bench_scope') == 'sample' %}
where split = 'test'
{% elif var('bench_scope') == 'pilot' %}
where pair_id in (select pair_id from read_files('/Volumes/jev_demo/bench/raw/abt_buy_pairs.parquet',
                  format => 'parquet') where split = 'test' order by pair_id limit 50)
{% endif %}
