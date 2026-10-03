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

## Pre-registration amendment (2026-10-03T07:50:03Z)

- reason: databricks-claude-opus-5 replaced by databricks-claude-opus-4-8 (user choice 2026-10-03): opus-5, opus-5-5 and sonnet-5-5 fail ai_query over a table with 'not supported for batch inference'; opus-4-8 rejects temperature and runs at its default (no modelParameters); prompts unchanged
- judges: jev, databricks-gpt-oss-20b, databricks-meta-llama-3-3-70b-instruct, databricks-claude-opus-4-8
- frozen paths at commit 4410d17
- frozen digest 7ad33a154159af0847d50dafa42c3d90129ed2a820f2a29c00e90a5c86e16c95 (supersedes the earlier digest; every judge is rerun from the pilot)
- dbt compile exit 0

## 2026-10-03T07:51:19Z · pilot · jev

- invocation 51d18044-37c7-4e15-8bd8-14c778b42bea
- scope pilot · 150 rows in scope · scored on judged rows (unjudged excluded) · 150 judged now · requests 3 · wall time 15.7 s (first hook start to last hook end)
- tokens in 24,584 (ledger)
- headline 2 · wanderbricks_comment_contradicts_rating · judged now 50 · wall time 12.9 s · cost per 1,000 judged rows $0.0058 (ledger)
- headline 2 · banking_query_not_about_intent · judged now 50 · wall time 12.3 s · cost per 1,000 judged rows $0.0052 (ledger)
- headline 2 · pairs_describe_same_product · judged now 50 · wall time 12.0 s · cost per 1,000 judged rows $0.0097 (ledger)
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

## 2026-10-03T07:52:24Z · pilot · databricks-gpt-oss-20b

- invocation 34a0954f-e100-4633-8916-a522b4aa7fa5
- scope pilot · 150 rows in scope · scored on judged rows (unjudged excluded) · 150 judged now · requests 150 · wall time 9.0 s (first hook start to last hook end)
- window 2026-10-03T07:51:46 2026-10-03T07:52:16 (UTC)
- tokens in ~29,467 (estimated)
- headline 2 · wanderbricks_comment_contradicts_rating · judged now 50 · wall time 6.7 s · cost per 1,000 judged rows $0.0802 (estimated, split by estimated tokens)
- headline 2 · banking_query_not_about_intent · judged now 50 · wall time 5.8 s · cost per 1,000 judged rows $0.0772 (estimated, split by estimated tokens)
- headline 2 · pairs_describe_same_product · judged now 50 · wall time 6.7 s · cost per 1,000 judged rows $0.1390 (estimated, split by estimated tokens)
- banking recall on random swaps 1/1 (1.00, 95% 0.21–1.00)
- banking recall on near_miss swaps 1/2 (0.50, 95% 0.09–0.91)
- wanderbricks false alarms on natural states 6/40 (0.15, 95% 0.07–0.29)
- llm cost $0.015 (estimated)

| test | rows | positives | flagged | P (95% CI) | R (95% CI) | F1 | unjudged |
|---|---|---|---|---|---|---|---|
| banking_query_not_about_intent | 50 | 3 | 5 | 0.40 (0.12–0.77) | 0.67 (0.21–0.94) | 0.50 | 0 |
| pairs_describe_same_product | 50 | 7 | 8 | 0.88 (0.53–0.98) | 1.00 (0.65–1.00) | 0.93 | 0 |
| wanderbricks_comment_contradicts_rating | 50 | 9 | 15 | 0.60 (0.36–0.80) | 1.00 (0.70–1.00) | 0.75 | 0 |

## 2026-10-03T07:53:26Z · pilot · databricks-meta-llama-3-3-70b-instruct

- invocation c3c2d232-cf9c-4353-838a-7bab73a7ee31
- scope pilot · 150 rows in scope · scored on judged rows (unjudged excluded) · 150 judged now · requests 150 · wall time 13.0 s (first hook start to last hook end)
- window 2026-10-03T07:52:47 2026-10-03T07:53:18 (UTC)
- tokens in ~29,467 (estimated)
- headline 2 · wanderbricks_comment_contradicts_rating · judged now 50 · wall time 6.0 s · cost per 1,000 judged rows $0.4424 (estimated, split by estimated tokens)
- headline 2 · banking_query_not_about_intent · judged now 50 · wall time 10.6 s · cost per 1,000 judged rows $0.4256 (estimated, split by estimated tokens)
- headline 2 · pairs_describe_same_product · judged now 50 · wall time 8.8 s · cost per 1,000 judged rows $0.7669 (estimated, split by estimated tokens)
- banking recall on random swaps 1/1 (1.00, 95% 0.21–1.00)
- banking recall on near_miss swaps 0/2 (0.00, 95% 0.00–0.66)
- wanderbricks false alarms on natural states 10/40 (0.25, 95% 0.14–0.40)
- llm cost $0.082 (estimated)

| test | rows | positives | flagged | P (95% CI) | R (95% CI) | F1 | unjudged |
|---|---|---|---|---|---|---|---|
| banking_query_not_about_intent | 50 | 3 | 4 | 0.25 (0.05–0.70) | 0.33 (0.06–0.79) | 0.29 | 0 |
| pairs_describe_same_product | 50 | 7 | 10 | 0.70 (0.40–0.89) | 1.00 (0.65–1.00) | 0.82 | 0 |
| wanderbricks_comment_contradicts_rating | 50 | 9 | 19 | 0.47 (0.27–0.68) | 1.00 (0.70–1.00) | 0.64 | 0 |

## 2026-10-03T07:54:32Z · pilot · databricks-claude-opus-4-8

- invocation 2ca6d810-90f2-40d8-a4df-85e0986cea00
- scope pilot · 150 rows in scope · scored on judged rows (unjudged excluded) · 150 judged now · requests 150 · wall time 16.4 s (first hook start to last hook end)
- window 2026-10-03T07:53:48 2026-10-03T07:54:23 (UTC)
- tokens in ~29,467 (estimated)
- headline 2 · wanderbricks_comment_contradicts_rating · judged now 50 · wall time 8.9 s · cost per 1,000 judged rows $6.4540 (estimated, split by estimated tokens)
- headline 2 · banking_query_not_about_intent · judged now 50 · wall time 8.1 s · cost per 1,000 judged rows $6.2088 (estimated, split by estimated tokens)
- headline 2 · pairs_describe_same_product · judged now 50 · wall time 16.4 s · cost per 1,000 judged rows $11.1873 (estimated, split by estimated tokens)
- banking recall on random swaps 1/1 (1.00, 95% 0.21–1.00)
- banking recall on near_miss swaps 2/2 (1.00, 95% 0.34–1.00)
- wanderbricks false alarms on natural states 0/40 (0.00, 95% 0.00–0.09)
- llm cost $1.192 (estimated)

| test | rows | positives | flagged | P (95% CI) | R (95% CI) | F1 | unjudged |
|---|---|---|---|---|---|---|---|
| banking_query_not_about_intent | 50 | 3 | 6 | 0.50 (0.19–0.81) | 1.00 (0.44–1.00) | 0.67 | 0 |
| pairs_describe_same_product | 50 | 7 | 7 | 1.00 (0.65–1.00) | 1.00 (0.65–1.00) | 1.00 | 0 |
| wanderbricks_comment_contradicts_rating | 50 | 9 | 9 | 1.00 (0.70–1.00) | 1.00 (0.70–1.00) | 1.00 | 0 |

## 2026-10-03T07:55:55Z · pass 1 · jev

- invocation 6d60ee9d-f993-4b63-b546-132c3b7b3df2
- scope sample · 4,161 rows in scope · scored on judged rows (unjudged excluded) · 4,006 judged now · requests 25 · wall time 19.4 s (first hook start to last hook end)
- tokens in 701,218 (ledger)
- headline 2 · wanderbricks_comment_contradicts_rating · judged now 195 · wall time 12.8 s · cost per 1,000 judged rows $0.0057 (ledger)
- headline 2 · banking_query_not_about_intent · judged now 1,950 · wall time 16.6 s · cost per 1,000 judged rows $0.0051 (ledger)
- headline 2 · pairs_describe_same_product · judged now 1,861 · wall time 14.9 s · cost per 1,000 judged rows $0.0099 (ledger)
- banking recall on random swaps 44/75 (0.59, 95% 0.47–0.69)
- banking recall on near_miss swaps 18/75 (0.24, 95% 0.16–0.35)
- wanderbricks false alarms on natural states 0/205 (0.00, 95% 0.00–0.02)

| test | rows | positives | flagged | P (95% CI) | R (95% CI) | F1 | unjudged |
|---|---|---|---|---|---|---|---|
| banking_query_not_about_intent | 2,000 | 150 | 73 | 0.85 (0.75–0.91) | 0.41 (0.34–0.49) | 0.56 | 0 |
| baseline_banking_keyword | 2,000 | 150 | 394 | 0.23 (0.19–0.27) | 0.60 (0.52–0.67) | 0.33 | 0 |
| pairs_describe_same_product | 1,916 | 206 | 174 | 0.94 (0.89–0.96) | 0.79 (0.73–0.84) | 0.86 | 0 |
| baseline_pairs_jaccard | 1,916 | 206 | 270 | 0.30 (0.24–0.35) | 0.39 (0.32–0.46) | 0.34 | 0 |
| wanderbricks_comment_contradicts_rating | 245 | 31 | 30 | 1.00 (0.89–1.00) | 0.97 (0.84–0.99) | 0.98 | 0 |

## 2026-10-03T07:57:42Z · pass 1 · databricks-gpt-oss-20b

- invocation f51c9e10-4204-448b-ae55-8686c3296f61
- scope sample · 4,161 rows in scope · scored on judged rows (unjudged excluded) · 4,006 judged now · requests 4,006 · wall time 56.9 s (first hook start to last hook end)
- window 2026-10-03T07:56:18 2026-10-03T07:57:34 (UTC)
- tokens in ~865,801 (estimated)
- headline 2 · wanderbricks_comment_contradicts_rating · judged now 195 · wall time 11.2 s · cost per 1,000 judged rows $0.0753 (estimated, split by estimated tokens)
- headline 2 · banking_query_not_about_intent · judged now 1,950 · wall time 32.9 s · cost per 1,000 judged rows $0.0740 (estimated, split by estimated tokens)
- headline 2 · pairs_describe_same_product · judged now 1,861 · wall time 56.9 s · cost per 1,000 judged rows $0.1315 (estimated, split by estimated tokens)
- banking recall on random swaps 71/75 (0.95, 95% 0.87–0.98)
- banking recall on near_miss swaps 54/75 (0.72, 95% 0.61–0.81)
- wanderbricks false alarms on natural states 6/205 (0.03, 95% 0.01–0.06)
- llm cost $0.404 (estimated)

| test | rows | positives | flagged | P (95% CI) | R (95% CI) | F1 | unjudged |
|---|---|---|---|---|---|---|---|
| banking_query_not_about_intent | 2,000 | 150 | 225 | 0.56 (0.49–0.62) | 0.83 (0.77–0.88) | 0.67 | 0 |
| pairs_describe_same_product | 1,916 | 206 | 245 | 0.80 (0.74–0.84) | 0.95 (0.91–0.97) | 0.86 | 0 |
| wanderbricks_comment_contradicts_rating | 245 | 31 | 37 | 0.84 (0.69–0.92) | 1.00 (0.89–1.00) | 0.91 | 0 |

## 2026-10-03T08:00:51Z · pass 1 · databricks-meta-llama-3-3-70b-instruct

- invocation 35113ac0-f8f2-4a03-8a40-beaf802d3ac1
- scope sample · 4,161 rows in scope · scored on judged rows (unjudged excluded) · 4,006 judged now · requests 4,006 · wall time 141.3 s (first hook start to last hook end)
- window 2026-10-03T07:58:03 2026-10-03T08:00:43 (UTC)
- tokens in ~865,801 (estimated)
- headline 2 · wanderbricks_comment_contradicts_rating · judged now 195 · wall time 21.8 s · cost per 1,000 judged rows $0.4178 (estimated, split by estimated tokens)
- headline 2 · banking_query_not_about_intent · judged now 1,950 · wall time 121.9 s · cost per 1,000 judged rows $0.4106 (estimated, split by estimated tokens)
- headline 2 · pairs_describe_same_product · judged now 1,861 · wall time 141.3 s · cost per 1,000 judged rows $0.7296 (estimated, split by estimated tokens)
- banking recall on random swaps 51/75 (0.68, 95% 0.57–0.77)
- banking recall on near_miss swaps 21/75 (0.28, 95% 0.19–0.39)
- wanderbricks false alarms on natural states 19/205 (0.09, 95% 0.06–0.14)
- llm cost $2.240 (estimated)

| test | rows | positives | flagged | P (95% CI) | R (95% CI) | F1 | unjudged |
|---|---|---|---|---|---|---|---|
| banking_query_not_about_intent | 2,000 | 150 | 139 | 0.52 (0.44–0.60) | 0.48 (0.40–0.56) | 0.50 | 0 |
| pairs_describe_same_product | 1,916 | 206 | 375 | 0.54 (0.49–0.59) | 0.98 (0.94–0.99) | 0.69 | 0 |
| wanderbricks_comment_contradicts_rating | 245 | 31 | 50 | 0.60 (0.46–0.72) | 0.97 (0.84–0.99) | 0.74 | 0 |

## 2026-10-03T08:02:15Z · pass 2 · jev

- invocation 5530a226-c4b1-4d90-a53d-f82e7b7be4ce
- scope sample · 4,161 rows in scope · scored on judged rows (unjudged excluded) · 4,156 judged now · requests 26 · wall time 17.9 s (first hook start to last hook end)
- tokens in 725,284 (ledger)
- headline 2 · wanderbricks_comment_contradicts_rating · judged now 245 · wall time 12.0 s · cost per 1,000 judged rows $0.0057 (ledger)
- headline 2 · banking_query_not_about_intent · judged now 2,000 · wall time 15.2 s · cost per 1,000 judged rows $0.0051 (ledger)
- headline 2 · pairs_describe_same_product · judged now 1,911 · wall time 11.1 s · cost per 1,000 judged rows $0.0099 (ledger)
- banking recall on random swaps 44/75 (0.59, 95% 0.47–0.69)
- banking recall on near_miss swaps 19/75 (0.25, 95% 0.17–0.36)
- wanderbricks false alarms on natural states 0/205 (0.00, 95% 0.00–0.02)

| test | rows | positives | flagged | P (95% CI) | R (95% CI) | F1 | unjudged |
|---|---|---|---|---|---|---|---|
| banking_query_not_about_intent | 2,000 | 150 | 76 | 0.83 (0.73–0.90) | 0.42 (0.34–0.50) | 0.56 | 0 |
| baseline_banking_keyword | 2,000 | 150 | 394 | 0.23 (0.19–0.27) | 0.60 (0.52–0.67) | 0.33 | 0 |
| pairs_describe_same_product | 1,916 | 206 | 173 | 0.94 (0.90–0.97) | 0.79 (0.73–0.84) | 0.86 | 0 |
| baseline_pairs_jaccard | 1,916 | 206 | 270 | 0.30 (0.24–0.35) | 0.39 (0.32–0.46) | 0.34 | 0 |
| wanderbricks_comment_contradicts_rating | 245 | 31 | 30 | 1.00 (0.89–1.00) | 0.97 (0.84–0.99) | 0.98 | 0 |

## 2026-10-03T08:04:03Z · pass 2 · databricks-gpt-oss-20b

- invocation 1c720a38-9aff-4e61-a516-fdb68de0cda1
- scope sample · 4,161 rows in scope · scored on judged rows (unjudged excluded) · 4,156 judged now · requests 4,156 · wall time 57.5 s (first hook start to last hook end)
- window 2026-10-03T08:02:38 2026-10-03T08:03:55 (UTC)
- tokens in ~895,268 (estimated)
- headline 2 · wanderbricks_comment_contradicts_rating · judged now 245 · wall time 13.0 s · cost per 1,000 judged rows $0.0753 (estimated, split by estimated tokens)
- headline 2 · banking_query_not_about_intent · judged now 2,000 · wall time 32.8 s · cost per 1,000 judged rows $0.0741 (estimated, split by estimated tokens)
- headline 2 · pairs_describe_same_product · judged now 1,911 · wall time 57.5 s · cost per 1,000 judged rows $0.1318 (estimated, split by estimated tokens)
- banking recall on random swaps 72/75 (0.96, 95% 0.89–0.99)
- banking recall on near_miss swaps 53/75 (0.71, 95% 0.60–0.80)
- wanderbricks false alarms on natural states 5/205 (0.02, 95% 0.01–0.06)
- llm cost $0.419 (estimated)

| test | rows | positives | flagged | P (95% CI) | R (95% CI) | F1 | unjudged |
|---|---|---|---|---|---|---|---|
| banking_query_not_about_intent | 2,000 | 150 | 226 | 0.55 (0.49–0.62) | 0.83 (0.77–0.88) | 0.66 | 0 |
| pairs_describe_same_product | 1,916 | 206 | 244 | 0.80 (0.74–0.84) | 0.95 (0.91–0.97) | 0.87 | 0 |
| wanderbricks_comment_contradicts_rating | 245 | 31 | 36 | 0.86 (0.71–0.94) | 1.00 (0.89–1.00) | 0.93 | 0 |
