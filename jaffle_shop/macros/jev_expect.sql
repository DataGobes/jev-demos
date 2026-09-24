{#-
  Semantic test: fails on rows where Jev judges `fails_if` to be true with p >= threshold.
  State sent to Jev is a JSON object of the tested column plus `context` columns.
-#}
{% test jev_expect(model, column_name, fails_if, context=[], threshold=0.5, criteria=none) %}
  {%- if fails_if is not string or not (fails_if | trim) -%}
    {{ exceptions.raise_compiler_error("jev_expect: `fails_if` must be a non-empty sentence") }}
  {%- endif -%}
  {%- if threshold is not number or threshold <= 0 or threshold > 1 -%}
    {{ exceptions.raise_compiler_error("jev_expect: `threshold` must be in (0, 1], got " ~ threshold) }}
  {%- endif -%}
  {%- set question = {"instructions": fails_if} -%}
  {%- if criteria is not none -%}
    {%- set normalized = {} -%}
    {%- for key, value in criteria.items() -%}
      {%- set k = (key | string | lower) -%}
      {%- if k not in ["true", "false"] -%}
        {{ exceptions.raise_compiler_error("jev_expect: `criteria` keys must be true/false, got " ~ key) }}
      {%- endif -%}
      {%- do normalized.update({k: value}) -%}
    {%- endfor -%}
    {%- do question.update({"criteria": normalized}) -%}
  {%- endif -%}
  {%- set fields = [column_name] + context -%}

with judged as materialized (
  select
    *,
    jev_noul(
      case when {{ column_name }} is null then null
           else to_json(struct_pack({% for f in fields %}{{ f }} := {{ f }}{{ ", " if not loop.last else "" }}{% endfor %}))
      end,
      '{{ tojson(question) | replace("'", "''") }}'
    ) as jev_p
  from {{ model }}
)
select * from judged where jev_p >= {{ threshold }}
{% endtest %}
