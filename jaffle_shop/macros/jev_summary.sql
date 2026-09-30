{#- on-run-end: one summary line + the once-per-row counters for this invocation. -#}

{#- Pure formatting: takes the gathered numbers (dict) and returns {"line1", "line2", "ok"}. -#}
{% macro jev_summary_lines(s) %}
  {%- set label = 'SIMULATED' if s.mode == 'demo' else 'LIVE' -%}
  {%- set cached = ((s.tested - s.missing) * 100 / s.tested) if s.tested else 0 -%}
  {%- set cost = s.tokens * s.price / 1000000 -%}
  {%- set line1 = "Jev · {:,} judgments · {:.0f}% cached · {:,} requests · {:,} retries ({:,}× 429) · {:.1f} s Jev · ${:.3f} · {} {} budget={}k".format(
        s.tested - s.unjudged, cached, s.packs, s.retries, s.throttled, s.span, cost, label,
        s.answered, (s.budget / 1000) | int) -%}
  {%- if s.unjudged > 0 -%}
    {%- set line1 = line1 ~ " · {:,} unjudged ({:,} failed requests)".format(s.unjudged, s.error_packs) -%}
  {%- endif -%}
  {%- set ok = (s.inserted == s.missing) and (s.pack_rows == s.inserted - s.oversized) and (s.dups == 0) -%}
  {%- set line2 = "Jev · once-per-row {} · {}: {:,} inserted = {:,} missing · packs sum {:,} (+{:,} too long) · {:,} duplicate keys".format(
        'OK' if ok else 'VIOLATED', label, s.inserted, s.missing, s.pack_rows, s.oversized, s.dups) -%}
  {{ return({"line1": line1, "line2": line2, "ok": ok}) }}
{% endmacro %}

{% macro jev_summary() %}
  {%- if not execute or flags.WHICH not in ['run', 'build'] -%}{{ return('') }}{%- endif -%}
  {%- set inv = jev_sql_string(invocation_id) -%}
  {%- set h = run_query("select count(*), coalesce(sum(tested), 0), coalesce(sum(missing), 0),
        coalesce(sum(inserted), 0), coalesce(sum(oversized), 0), max(mode), max(requested_model)
      from " ~ jev_relation('hook_runs') ~ " where invocation_id = " ~ inv) -%}
  {%- set hooks = h.columns[0].values()[0] | int -%}
  {%- if hooks == 0 -%}{{ return('') }}{%- endif -%}
  {%- set r = run_query("select count(*), coalesce(sum(pack_tokens), 0), coalesce(sum(pack_rows), 0),
        coalesce(sum(greatest(attempts - 1, 0)), 0),
        coalesce(sum(greatest(size(filter(retry_statuses, s -> s = 429)), 0)), 0),
        count_if(error is not null),
        coalesce((unix_micros(max(finished_at)) - unix_micros(min(started_at))) / 1e6, 0),
        max(answered_model)
      from " ~ jev_relation('requests') ~ " where invocation_id = " ~ inv) -%}
  {%- set u = run_query("select count_if(p is null) from " ~ jev_relation('judgments')
        ~ " where invocation_id = " ~ inv).columns[0].values()[0] | int -%}
  {%- set dups = run_query("select count(*) from (select key from " ~ jev_relation('judgments')
        ~ " where p is not null group by key having count(*) > 1)").columns[0].values()[0] | int -%}
  {%- set out = jev_summary_lines({
        "tested": h.columns[1].values()[0] | int,
        "missing": h.columns[2].values()[0] | int,
        "inserted": h.columns[3].values()[0] | int,
        "oversized": h.columns[4].values()[0] | int,
        "unjudged": u,
        "packs": r.columns[0].values()[0] | int,
        "tokens": r.columns[1].values()[0] | int,
        "pack_rows": r.columns[2].values()[0] | int,
        "retries": r.columns[3].values()[0] | int,
        "throttled": r.columns[4].values()[0] | int,
        "error_packs": r.columns[5].values()[0] | int,
        "span": r.columns[6].values()[0] | float,
        "answered": r.columns[7].values()[0] or h.columns[6].values()[0],
        "mode": h.columns[5].values()[0],
        "dups": dups,
        "budget": var('jev_pack_token_budget'),
        "price": var('jev_price_per_mtok_usd')
      }) -%}
  {%- do log(out.line1, info=True) -%}
  {%- do log(out.line2, info=True) -%}
  {%- if not out.ok -%}
    {{ exceptions.raise_compiler_error("jev: once-per-row VIOLATED: " ~ out.line2) }}
  {%- endif -%}
  {{ return('') }}
{% endmacro %}
