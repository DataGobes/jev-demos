{#- on-run-end: one summary line + the once-per-row counters for this invocation. -#}
{% macro jev_summary() %}
  {%- if not execute or flags.WHICH not in ['run', 'build'] -%}{{ return('') }}{%- endif -%}
  {%- set inv = jev_sql_string(invocation_id) -%}
  {%- set h = run_query("select count(*), coalesce(sum(tested), 0), coalesce(sum(missing), 0),
        coalesce(sum(inserted), 0), coalesce(sum(oversized), 0), max(mode), max(requested_model)
      from " ~ jev_relation('hook_runs') ~ " where invocation_id = " ~ inv) -%}
  {%- set hooks = h.columns[0].values()[0] | int -%}
  {%- if hooks == 0 -%}{{ return('') }}{%- endif -%}
  {%- set tested = h.columns[1].values()[0] | int -%}
  {%- set missing = h.columns[2].values()[0] | int -%}
  {%- set inserted = h.columns[3].values()[0] | int -%}
  {%- set oversized = h.columns[4].values()[0] | int -%}
  {%- set mode = h.columns[5].values()[0] -%}
  {%- set r = run_query("select count(*), coalesce(sum(pack_tokens), 0), coalesce(sum(pack_rows), 0),
        coalesce(sum(attempts - 1), 0), coalesce(sum(greatest(size(filter(retry_statuses, s -> s = 429)), 0)), 0),
        count_if(error is not null),
        coalesce((unix_micros(max(finished_at)) - unix_micros(min(started_at))) / 1e6, 0),
        max(answered_model)
      from " ~ jev_relation('requests') ~ " where invocation_id = " ~ inv) -%}
  {%- set packs = r.columns[0].values()[0] | int -%}
  {%- set tokens = r.columns[1].values()[0] | int -%}
  {%- set pack_rows = r.columns[2].values()[0] | int -%}
  {%- set retries = r.columns[3].values()[0] | int -%}
  {%- set throttled = r.columns[4].values()[0] | int -%}
  {%- set errors = r.columns[5].values()[0] | int -%}
  {%- set span = r.columns[6].values()[0] | float -%}
  {%- set answered = r.columns[7].values()[0] or var('jev_model') -%}
  {%- set dups = run_query("select count(*) from (select key from " ~ jev_relation('judgments')
        ~ " where p is not null group by key having count(*) > 1)").columns[0].values()[0] | int -%}
  {%- set cached = ((tested - missing) * 100 / tested) if tested else 0 -%}
  {%- set cost = tokens * var('jev_price_per_mtok_usd') / 1000000 -%}
  {%- set label = 'SIMULATED' if mode == 'demo' else 'LIVE' -%}
  {%- set line1 = "Jev · {:,} judgments · {:.0f}% cached · {:,} requests · {:,} retries ({:,}× 429) · {:.1f} s Jev · ${:.3f} · {} {} budget={}k".format(
        tested, cached, packs, retries, throttled, span, cost, label, answered,
        (var('jev_pack_token_budget') / 1000) | int) -%}
  {%- if errors -%}{%- set line1 = line1 ~ " · " ~ errors ~ " errors" -%}{%- endif -%}
  {%- set ok = (inserted == missing) and (pack_rows == inserted - oversized) and (dups == 0) -%}
  {%- set line2 = "Jev · once-per-row {}: {:,} inserted = {:,} missing · packs sum {:,} (+{:,} too long) · {:,} duplicate keys".format(
        'OK' if ok else 'VIOLATED', inserted, missing, pack_rows, oversized, dups) -%}
  {%- do log(line1, info=True) -%}
  {%- do log(line2, info=True) -%}
  {{ return('') }}
{% endmacro %}
