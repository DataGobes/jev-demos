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
