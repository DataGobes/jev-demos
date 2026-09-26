{#-
  Probe 5a: the mock judge as a Jinja macro. It can only *write SQL*: checks render at parse
  with the parse-phase adapter, which answers every query with an empty table
  (dbt-adapter/src/adapter/mod.rs:357), so no Jinja here can fetch data or call out.

  Renders a DuckDB boolean: true when the description's key noun (its last word of 3+ letters
  that is not a stopword) appears in the column name. Must stay in step with
  src/desc_judge/judges.py::key_noun.
-#}
{% macro mock_judge_key_noun(description) -%}
list_filter(
    string_split(regexp_replace(lower({{ description }}), '[^a-z0-9 ]', ' ', 'g'), ' '),
    w -> length(w) >= 3 and not list_contains(
        ['the','and','for','with','from','into','per','was','were','are','this','that','its','their','which'], w)
)[-1]
{%- endmacro %}

{% macro mock_judge_matches(column_name, description) -%}
coalesce(contains(lower({{ column_name }}), {{ mock_judge_key_noun(description) }}), true)
{%- endmacro %}
