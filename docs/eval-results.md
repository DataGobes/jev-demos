# Eval results

Every scored live run of demo 06, newest last, written by `scripts/score.py --run --append`.
SIMULATED runs are never written here. LLM cost lines say `measured` (from
`system.serving.endpoint_usage`) or `estimated` (token assumptions); Jev cost comes from the ledger.

## Pre-registration (frozen before pass 1)

- judges: jev, databricks-gpt-oss-20b, databricks-meta-llama-3-3-70b-instruct, databricks-claude-opus-5; temperature 0; prompt version p1
- prompts and test wording: bench/models/staging/schema.yml and bench/macros/jev_question.sql at commit f731639
- frozen digest 2164b49af36f5e011f940f55ea8e37dc0346d02448d38ed6cd5ebd60a6619fde (sha256 of `git ls-files -s -- bench/macros bench/models bench/seeds bench/tests bench/dbt_project.yml eval`; a live append is refused when it differs or those paths are dirty)
- Banking77: seed 42, sample 2,000 test queries, swaps in sample 150 (75 random + 75 near-miss), families in eval/intent_families.csv
- Abt-Buy: sample = test split; Jaccard threshold 0.2115 fit on train
- wanderbricks: every natural (comment, rating) state (the control: false-alarm rate) + planted ratings in eval/wanderbricks_flips.csv (seed 42); rule in jevdbx.keys.contradiction
- headline 1: per dataset, F1 of Jev vs each LLM (decision level), Wilson 95% for P and R
- headline 2: per dataset, cost per 1,000 rows and wall time per judge
- headline 3: Banking77 recall on random vs near-miss swaps, per judge
- unjudged tolerance 1% of in-scope rows per test (more is not a result; rerun to fill)
- budget margin 1.15 on projections
- dbt compile exit 0

## 2026-10-03T07:37:46Z · pilot · jev

- invocation 206d4056-20c9-4605-a969-ae43dbf4205e
- scope pilot · 150 rows in scope · scored on judged rows (unjudged excluded) · 150 judged now · requests 3 · wall time 46.0 s (first hook start to last hook end)
- tokens in 24,584 (ledger)
- headline 2 · wanderbricks_comment_contradicts_rating · judged now 50 · wall time 43.3 s · cost per 1,000 judged rows $0.0058 (ledger)
- headline 2 · banking_query_not_about_intent · judged now 50 · wall time 42.3 s · cost per 1,000 judged rows $0.0052 (ledger)
- headline 2 · pairs_describe_same_product · judged now 50 · wall time 44.0 s · cost per 1,000 judged rows $0.0097 (ledger)
- banking recall on random swaps 1/1 (1.00, 95% 0.21–1.00)
- banking recall on near_miss swaps 1/2 (0.50, 95% 0.09–0.91)
- wanderbricks false alarms on natural states 0/40 (0.00, 95% 0.00–0.09)

| test | rows | positives | flagged | P (95% CI) | R (95% CI) | F1 | unjudged |
|---|---|---|---|---|---|---|---|
| banking_query_not_about_intent | 50 | 3 | 2 | 1.00 (0.34–1.00) | 0.67 (0.21–0.94) | 0.80 | 0 |
| baseline_banking_keyword | 50 | 3 | 2 | 0.50 (0.09–0.91) | 0.33 (0.06–0.79) | 0.40 | 0 |
| pairs_describe_same_product | 50 | 7 | 6 | 1.00 (0.61–1.00) | 0.86 (0.49–0.97) | 0.92 | 0 |
| baseline_pairs_jaccard | 50 | 7 | 3 | 1.00 (0.44–1.00) | 0.43 (0.16–0.75) | 0.60 | 0 |
| wanderbricks_comment_contradicts_rating | 50 | 9 | 9 | 1.00 (0.70–1.00) | 1.00 (0.70–1.00) | 1.00 | 0 |

## 2026-10-03T07:39:00Z · pilot · databricks-gpt-oss-20b

- invocation 9f57db48-bc3d-4e46-a9e9-9c2330bc5ea1
- scope pilot · 150 rows in scope · scored on judged rows (unjudged excluded) · 150 judged now · requests 150 · wall time 11.3 s (first hook start to last hook end)
- window 2026-10-03T07:38:16 2026-10-03T07:38:49 (UTC)
- tokens in ~29,467 (estimated)
- headline 2 · wanderbricks_comment_contradicts_rating · judged now 50 · wall time 8.6 s · cost per 1,000 judged rows $0.0802 (estimated, split by estimated tokens)
- headline 2 · banking_query_not_about_intent · judged now 50 · wall time 7.4 s · cost per 1,000 judged rows $0.0772 (estimated, split by estimated tokens)
- headline 2 · pairs_describe_same_product · judged now 50 · wall time 11.3 s · cost per 1,000 judged rows $0.1390 (estimated, split by estimated tokens)
- banking recall on random swaps 1/1 (1.00, 95% 0.21–1.00)
- banking recall on near_miss swaps 1/2 (0.50, 95% 0.09–0.91)
- wanderbricks false alarms on natural states 5/40 (0.12, 95% 0.05–0.26)
- llm cost $0.015 (estimated)

| test | rows | positives | flagged | P (95% CI) | R (95% CI) | F1 | unjudged |
|---|---|---|---|---|---|---|---|
| banking_query_not_about_intent | 50 | 3 | 5 | 0.40 (0.12–0.77) | 0.67 (0.21–0.94) | 0.50 | 0 |
| pairs_describe_same_product | 50 | 7 | 8 | 0.88 (0.53–0.98) | 1.00 (0.65–1.00) | 0.93 | 0 |
| wanderbricks_comment_contradicts_rating | 50 | 9 | 14 | 0.64 (0.39–0.84) | 1.00 (0.70–1.00) | 0.78 | 0 |

## 2026-10-03T07:40:06Z · pilot · databricks-meta-llama-3-3-70b-instruct

- invocation a531f22c-8390-42b8-9689-f1e0eba08016
- scope pilot · 150 rows in scope · scored on judged rows (unjudged excluded) · 150 judged now · requests 150 · wall time 11.3 s (first hook start to last hook end)
- window 2026-10-03T07:39:22 2026-10-03T07:39:57 (UTC)
- tokens in ~29,467 (estimated)
- headline 2 · wanderbricks_comment_contradicts_rating · judged now 50 · wall time 8.8 s · cost per 1,000 judged rows $0.4424 (estimated, split by estimated tokens)
- headline 2 · banking_query_not_about_intent · judged now 50 · wall time 8.3 s · cost per 1,000 judged rows $0.4256 (estimated, split by estimated tokens)
- headline 2 · pairs_describe_same_product · judged now 50 · wall time 9.6 s · cost per 1,000 judged rows $0.7669 (estimated, split by estimated tokens)
- banking recall on random swaps 1/1 (1.00, 95% 0.21–1.00)
- banking recall on near_miss swaps 0/2 (0.00, 95% 0.00–0.66)
- wanderbricks false alarms on natural states 8/40 (0.20, 95% 0.10–0.35)
- llm cost $0.082 (estimated)

| test | rows | positives | flagged | P (95% CI) | R (95% CI) | F1 | unjudged |
|---|---|---|---|---|---|---|---|
| banking_query_not_about_intent | 50 | 3 | 3 | 0.33 (0.06–0.79) | 0.33 (0.06–0.79) | 0.33 | 0 |
| pairs_describe_same_product | 50 | 7 | 10 | 0.70 (0.40–0.89) | 1.00 (0.65–1.00) | 0.82 | 0 |
| wanderbricks_comment_contradicts_rating | 50 | 9 | 17 | 0.53 (0.31–0.74) | 1.00 (0.70–1.00) | 0.69 | 0 |

## 2026-10-03T07:40:52Z · refused · pilot · databricks-claude-opus-5

- not a result: dbt exited 1; invocation a531f22c-8390-42b8-9689-f1e0eba08016 is already in the log (stale stored failures)
- invocation refused-20261003T074052Z
- window 2026-10-03T07:40:27 2026-10-03T07:40:46 (UTC)
- llm cost $1.192 (estimated)
