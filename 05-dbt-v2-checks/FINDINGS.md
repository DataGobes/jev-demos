# Findings: can a dbt v2 check call an LLM judge?

**Question.** Can dbt v2's native checks call a custom or external function, so that a check
can flag column descriptions that don't match their column using an LLM judgment (Jev)?

**Answer.** No, not in a form worth shipping. Checks are pure SQL over parse-time metadata,
run on a private in-memory DuckDB. The only exit to the outside is a DuckDB extension, and the
check is still missing half of what a judge needs:

1. **What the judge would see.** At parse time a check can read the column name, the
   *declared* type and the description, but **not the model's SQL** (neither `raw_code` nor
   `compiled_code` is in the check's `models` view) and **not inferred types or column
   lineage**. The judge's `sql` argument is simply unavailable inside a check.
2. **How it would call out.** No UDF registration, no Python, and Jinja can't execute
   anything at parse. A check *can* load a DuckDB extension and make an HTTP request, but
   only with a constant URL (one call per check, not per column), and every GET went out
   twice. Per-row calls need a third-party community extension that loads unverified code
   into dbt's process on every developer's machine.

**Recommendation: the fallback.** Run the judge next to dbt as a check-shaped CLI
(`desc-judge`) that reads the information schema Parquet after `dbt compile
--generate-info-schema`, judges only changed or uncached columns, and fails CI with rows the
same way a check does. Keep one native check for the part a check *can* do well, the cheap
deterministic gate (`columns_have_descriptions`).

Everything below cites a source file in `dbt-labs/dbt-core` at commit
`56cf8733485e2c97ef1e49682620045fc5726bf8` (2026-09-26), or a command run in this session with
its output. Paths are relative to the dbt-core repo root unless they start with `05-`.

---

## 0. Environment: what ran and what did not

<!-- ENVIRONMENT -->

## 1. How checks are defined, compiled and executed

| Stage | What happens | Evidence |
|---|---|---|
| Define | Every `*.sql` under `check-paths` (default `checks/`) is a check. A package with checks must set `info_schema: version: 1` in `dbt_project.yml`, or parsing fails | `crates/dbt-tasks-sa/src/check.rs:3-5`; `crates/dbt-loader/src/load_packages.rs:537`; `crates/dbt-schemas/src/schemas/project/dbt_project.rs:149`; `crates/dbt-parser/src/resolve/resolve_checks.rs:130-148` |
| Config | `enabled`, `meta`, `tags`, `severity` (default `error`), `selection_filter_on`. Nothing else: no hook, plugin or function config | `crates/dbt-schemas/src/schemas/project/configs/check_config.rs:91-102` |
| Compile | Rendered by Jinja **at parse**, and the rendered text is stored as `compiled_sql`. There is no later compile step for checks. A check has no refs, sources, functions or DAG parents | `resolve_checks.rs:101-105, 234-248` |
| Jinja context | The parse-phase environment: all project macros plus `info_schema('<view>')`, which expands to `dbt.<view>` for an allowlisted view name | `crates/dbt-jinja-utils/src/phases/parse/init.rs:145-195`; `crates/dbt-jinja-utils/src/info_schema.rs:33-94` |
| Execute | After parse and before the task graph, in one runner shared by `dbt check` and `dbt build`: dbt opens an **in-memory vanilla DuckDB through its own DuckDB adapter** (ADBC), registers parse-safe views over the metadata epochs in `target/private/metadata/`, and runs each check's SQL | `check.rs:600-680`; `crates/dbt-tasks-sa/src/check_adapter.rs:1-25, 51-71, 144-202, 218-224` |
| Verdict | 0 rows = `pass`. Rows = `fail` (severity `error`, non-zero exit, `dbt build` stops) or `warn`. SQL that fails to execute = `error`. A selection that leaves nothing to examine = `skipped`, never a vacuous pass | `check.rs:683-742, 68-104` |

**Which engine runs the SQL:** DuckDB, not the warehouse. It is the vanilla build
(`Backend::DuckDB`, driver version `1.5.4`), not dbt's extended DuckDB
(`check_adapter.rs:3-8, 46`; `crates/dbt-adbc/src/lib.rs:81`). Its config is hard-coded to
`{type: duckdb, path: ":memory:"}` (`check_adapter.rs:52-54`), so a profile's DuckDB
`extensions:`/`settings:` (`crates/dbt-auth/src/duckdb/init.rs:510-548`) never reach it.
DuckDB receives the check's SQL **unsplit**, as one string (`crates/dbt-adapter/src/adapter/adapter_impl.rs:808-818`).

## 2–3. Example project and a trivial check

<!-- LIVE_RUN -->

## 4. What the Information Schema holds

Two surfaces with one vocabulary. A check reads the **parse-safe views**, a strict subset of
the published tables, "same names, fewer columns"
(`crates/dbt-index-core/src/info_schema/parse_safe.rs:1-35`). The **published information
schema** (`target/info_schema/v1/dbt.<table>.parquet`, written with `--generate-info-schema`)
has everything (`crates/dbt-index-core/src/info_schema/mod.rs:1-8, 91`;
`crates/dbt-clap-core/src/lib.rs:2047`).

Tables (published, `dbt` namespace): `project, packages, project_vars, project_env_vars,
models, seeds, snapshots, functions, analyses, hooks, checks, sources, data_tests, unit_tests,
macros, groups, exposures, metrics, docs_blocks, saved_queries, semantic_models,
semantic_entities, semantic_measures, semantic_dimensions, semantic_relationships,
time_spines, dag_nodes, edges, node_columns, column_lineage, classifiers`, plus `dbt_rt`
runtime tables (`invocations, run_results, freshness, relations, diagnostics, adapter_queries,
node_input_files`) (`crates/dbt-index-core/src/info_schema/schema.rs:80-762`).

The fields the judge needs:

| Needed by the judge | In a check (parse-safe) | In the published information schema |
|---|---|---|
| column name | ✅ `node_columns.column_name` | ✅ |
| description | ✅ `node_columns.description` | ✅ |
| data type | ⚠️ `data_type_declared` only, i.e. what YAML says | ✅ `data_type`, `data_type_inferred`, `data_type_declared`, `data_type_actual` (`schema.rs:556-580`) |
| model SQL | ❌ `models` has neither `raw_code` nor `compiled_code` (`parse_safe.rs:103-137`; `CHANGELOG-dbt.md:379`) | ✅ `models.raw_code`, `models.compiled_code` after compile (`schema.rs:29, 60`) |
| column-level lineage | ❌ `column_lineage` "needs static analysis, so it is empty at parse" (`parse_safe.rs:167`; `info_schema.rs:29-31`) | ✅ `column_lineage` (parent/child node + column, `evolution`) after compile (`schema.rs:583-595`) |

A parse-only information schema has the tables but "lacks compiled code, column types,
column-level lineage and runtime results" (`CHANGELOG-dbt.md:402`, `InfoSchemaIncomplete`
dbt1658). The judge needs `compile` (or `build`) with `--generate-info-schema`.

## 5. Extensibility, tested in order

For each option I tried to express the mock judge,
`judge(column_name, data_type, description, sql) → bool`: false when the description's key
noun (its last non-stopword of 3+ letters) is in neither the column name nor the SQL.

| # | Path | Works inside a check? | Can it reach an external judge? |
|---|---|---|---|
| a | Jinja macros | ✅ project macros are loaded in the parse environment | ❌ they can only write SQL text |
| b | DuckDB macros / UDFs | ✅ `CREATE MACRO …; SELECT …` in the check file; ❌ no way to register a real UDF | ❌ a macro is SQL; it can't leave DuckDB |
| c | DuckDB extensions | ✅ `LOAD` from a file works; `INSTALL` from the network by default | ⚠️ constant-URL HTTP GET only (one call per check); per-row needs an unsigned-by-dbt community extension |
| d | other hooks | ❌ none found for checks | ❌ |

### 5a. Jinja and macros inside a check

- **Works for SQL generation.** Checks render in the parse-phase Jinja environment, built
  `.try_with_macros(...)` with the project's macros, with `info_schema()` added as a global
  (`crates/dbt-jinja-utils/src/phases/parse/init.rs:177-195`). The mock judge as a macro:
  `05-dbt-v2-checks/project/macros/mock_judge.sql`, used by
  `project/checks/description_matches_column_jinja.sql`.
- **Cannot call anything.** The adapter in that environment is the parse-phase adapter
  (`init.rs:145-151`, `crates/dbt-adapter/src/adapter/mod.rs:154-174`), and its
  `execute_without_state` returns an empty table for any SQL:
  `Parse(_) => Ok((AdapterResponse::default(), AgateTable::default()))`
  (`crates/dbt-adapter/src/adapter/mod.rs:357`). So `run_query` can't fetch the columns to
  judge, and the Jinja crates contain no process or HTTP code:

  ```
  $ grep -rln "std::process::Command\|process::Command\|reqwest::\|ureq::" \
      dbt-jinja dbt-jinja-ctx dbt-jinja-filters dbt-jinja-utils dbt-jinja-vars | grep -v test
  (no output)
  ```
- **Judge input:** name + declared type + description only. There is no SQL at parse (§4).

### 5b. DuckDB macros or user-defined functions inside a check

- **Macros work.** dbt hands a DuckDB check's SQL to the driver as one string ("BigQuery,
  DuckDB, and lake compute support multi-statement execution… `Bigquery | DuckDB |
  LakeCompute => vec![sql]`", `crates/dbt-adapter/src/adapter/adapter_impl.rs:808-818`), and
  DuckDB 1.5.4 executes every statement and returns the last one's rows. Tested on the same
  engine version through its ADBC entrypoint, one `execute` per probe, as dbt does
  (`05-dbt-v2-checks/probes/probe_adbc.py`):

  ```
  $ uv run python probes/probe_adbc.py
  [OK]    multi_statement_macro: [(True,)]              # create macro judge(...); select judge('order_total','customer email')
  [OK]    multi_statement_macro_returns_last: [(1,)]
  ```
  The mock judge as a DuckDB macro: `project/checks/description_matches_column_macro.sql`.
  Parity with the Python mock is tested (`tests/test_desc_judge.py::test_the_sql_macro_in_the_native_check_agrees_with_the_python_mock`).
- **Real UDFs: no path.** DuckDB registers scalar UDFs through its host-language APIs (Python,
  C, Rust), not SQL. The check runs inside dbt's Rust process, and nothing in `CheckConfig`
  (`check_config.rs:91-102`) or the check runner (`check.rs:615-745`) takes a function to
  register. dbt's own `functions` resource (UDFs) targets the warehouse, and checks are built
  with `functions: vec![]` and no DAG parents (`resolve_checks.rs:234-242`).
- A macro is still SQL. It can encode a rule, not an LLM call.

### 5c. Loading DuckDB extensions

What a check's DuckDB allows is DuckDB's defaults. The config dbt passes is only
`type`/`path` (`check_adapter.rs:52-54`), and the adapter layer sets none of
`enable_external_access`, `allow_community_extensions`, `lock_configuration`:

```
$ grep -rn -i "enable_external_access\|allow_unsigned\|autoinstall\|lock_configuration\|allow_community" \
    crates/dbt-adapter crates/dbt-adbc crates/dbt-tasks-sa crates/dbt-index-core --include=*.rs
(no output, exit=1; the same grep over all of crates/ for the first three settings: no output)

$ uv run python probes/probe_adbc.py      # stock DuckDB 1.5.4, in-memory, via ADBC
[OK]    settings: [('allow_community_extensions', 'true'), ('allow_unsigned_extensions', 'false'),
                   ('autoinstall_known_extensions', 'true'), ('autoload_known_extensions', 'true'),
                   ('enable_external_access', 'true'), ('lock_configuration', 'false')]
[OK]    read_local_file: [(3,)]
[ERROR] install_httpfs: ... Failed to download extension "httpfs" at URL "http://extensions.duckdb.org/v1.5.4/linux_amd64/httpfs.duckdb_extension.gz" (HTTP 403)
[ERROR] install_community_shellfs: ... "http://community-extensions.duckdb.org/v1.5.4/linux_amd64/shellfs.duckdb_extension.gz" (HTTP 403)
```

The 403s come from this sandbox's egress proxy, not from DuckDB. So I loaded DuckDB's signed
`httpfs` from its PyPI wheel (`duckdb-extension-httpfs==1.5.4`) and pointed it at a mock judge
on 127.0.0.1 (`probes/probe_ext.py`):

```
$ uv run python probes/probe_ext.py
[OK]    load_httpfs_from_file: [(1,)]
[OK]    constant_url_call: [(False,)]            # the mock judge said: 'customer email' does not fit order_total
[ERROR] per_row_url_call: ... Binder Error: Table function "read_json" does not support lateral join column parameters - cannot use column "c.name" in this context.
[ERROR] per_row_scalar_via_subquery: ... Binder Error: Table function "read_json" does not support lateral join column parameters - cannot use column "name" in this context.
mock judge received 2 request(s): ['/judge?name=order_total&description=customer%20email', '/judge?name=order_total&description=customer%20email']
```

What that means:

- A check **can** reach out over HTTP, but only with a URL fixed at render time. Jinja can't
  build per-column URLs (5a: it can't read the metadata), and DuckDB won't take them per row.
  One call per check means the judge would have to fetch the metadata itself, and then the
  check adds nothing.
- The single constant-URL query sent **two identical GETs**. With a real LLM behind it, that
  is double billing, and nothing in the check can stop it. (Same class of problem as demo 04's
  UDF evaluated twice.)
- A per-row call would need a **community extension** with a scalar HTTP or shell function
  (e.g. `http_client`, `shellfs`). `allow_community_extensions` defaults to true, so
  `INSTALL … FROM community` in a check file would likely work on an unsandboxed machine.
  **Not verified here** (download blocked). Either way, that is third-party native code,
  downloaded at check time, running inside dbt's process on every developer's laptop and CI
  runner, and all of it is an unset default rather than a feature. I would not build on it,
  and a hardening change upstream (setting `enable_external_access=false` or
  `lock_configuration=true` on the check database) would break it without notice.

### 5d. Any other hook that could call an external process

- **Check config:** only `enabled, meta, tags, severity, selection_filter_on`
  (`check_config.rs:91-102`).
- **Timing:** checks run after parse and before the task graph exists, so `on-run-start`
  hooks and models haven't run yet ("parse has finished, its metadata epochs are on disk, and
  the task graph has not been built", `check.rs:606-610`). A hook cannot prepare verdicts for a
  check in the same invocation.
- **Python:** there is no Python runtime in the check path. The engine is Rust; its DuckDB
  driver is loaded over ADBC (`crates/dbt-adbc/src/driver.rs:318-462`). The only Python-shaped
  extension point, dbt-duckdb plugins, belongs to dbt-core v1 (`04-dbt-semantic-tests/CLAUDE.md`:
  "dbt Fusion … cannot load the Python adapter plugin").
- **Reading precomputed verdicts:** a check could `read_parquet('/path/verdicts.parquet')`,
  since `enable_external_access` is on (the probe read `/etc/hostname`). That is the fallback with
  an extra step: something outside dbt still has to produce the verdicts first. It is also the
  one shape where a native check adds value; see §7.

## 6. The fallback: `desc-judge`

`05-dbt-v2-checks/src/desc_judge/`: a Python CLI that reads the published information schema
with DuckDB, asks a pluggable judge, and reports like a check.

```
dbt compile --generate-info-schema  ──►  target/info_schema/v1/dbt.{models,node_columns}.parquet
                                                   │  facts.py: one ColumnFacts per model column
                                                   ▼  (name, data_type, description, compiled SQL)
            --state <baseline info_schema/v1> ──►  runner.changed_only   fingerprint diff vs baseline
                                                   │
                                                   ▼  VerdictCache: (judge.id, sha256(name,type,desc,sql))
                                         hits ◄────┤
                                                   ▼  misses, deduplicated by fingerprint, in batches
                                             Judge.judge(batch) → [Verdict]   MockJudge now, JevJudge later
                                                   │
                                                   ▼
                        rows (unique_id, column_name, description, message): 0 rows = pass, else exit 1
```

**Architecture requirements, and how they are met**

| Requirement | How | Where |
|---|---|---|
| Judge is an interface; Mock → Jev is a one-class change | `Judge` protocol: `id` + batched `judge(items) -> list[Verdict]`. Nothing else knows which judge runs. Adding Jev = one class + one `JUDGES` entry | `judges.py` |
| Only evaluate changed columns | `--state <baseline info_schema>` keeps columns whose fingerprint differs from the baseline. This is column-level `state:modified`, which dbt's own doesn't provide: "`description` is still not compared" (`CHANGELOG-dbt.md:394`). `--select` still takes node ids from `dbt ls -s state:modified` | `runner.changed_only`, `cli.py` |
| Cache verdicts on a hash of (name, type, description, sql) | `ColumnFacts.fingerprint` = sha256 of exactly those four. The cache key also carries `judge.id`, so a new judge or prompt never reuses old verdicts. Identical columns are sent once per run | `judges.py`, `cache.py`, `runner.evaluate` |
| Usable in CI | check-shaped output, `--format json`, exit 1 on violations, `--warn` for severity warn, atomic cache file | `cli.py`, `cache.py` |

**Evidence** (all with `MockJudge`, a keyword rule, on the example project's columns):

```
$ uv run pytest -q
...........                                                              [100%]
11 passed

$ uv run desc-judge --info-schema <fixture>/info_schema/v1 --cache c.json      # 1st run
FAIL description_matches_column (4 violations) [judge=mock-v1 in_scope=16 judged=16 cached=0 unchanged=0 undocumented=1]
  unique_id                          column_name   message
  model.desc_checks.customer_orders  order_count   key noun 'euros' is in neither the column name nor the SQL  ('Average basket size in euros')
  model.desc_checks.fct_revenue      revenue_date  key noun 'delivered' is in neither the column name nor the SQL  ('Date the shipment was delivered')
  model.desc_checks.stg_customers    last_name     key noun 'number' is in neither the column name nor the SQL  ('Customer phone number')
  model.desc_checks.stg_orders       order_total   key noun 'email' is in neither the column name nor the SQL  ('Customer email')
exit=1

$ uv run desc-judge --info-schema <fixture>/info_schema/v1 --cache c.json      # 2nd run, nothing changed
FAIL description_matches_column (4 violations) [judge=mock-v1 in_scope=16 judged=0 cached=16 unchanged=0 undocumented=1]
```

What the tests pin (`tests/test_desc_judge.py`): the four WRONG descriptions fail, and the
SUBTLE one (`first_order_date`: "most recent order" on a `min()`) passes the mock. A keyword
rule can't see it, and that is the gap Jev is meant to close. The tests also cover: a second
run judges nothing; a description edit re-judges exactly that column; `--state` scopes to
the 1 changed column of 17; a new judge id re-judges everything; a parse-only schema falls back
to `raw_code` and declared types; and the SQL and Jinja versions of the mock agree with the
Python one.

<!-- FALLBACK_LIVE -->

## 7. Recommendation

**Use the fallback for the judgment, and a native check for the cheap part.**

| | Native check (5b/5c) | Fallback CLI |
|---|---|---|
| Sees model SQL, inferred types, lineage | ❌ parse-safe views only (§4) | ✅ published information schema after compile |
| Calls an LLM per column | ❌ constant URL only; per-row needs a community extension | ✅ any client, batched |
| Changed-only + cache | ❌ checks re-run in full every parse; no state of their own | ✅ `--state` fingerprint diff + verdict cache |
| Cost / latency on every `dbt build` | ❌ would sit in the parse-time gate of every developer's build | ✅ runs once in CI, only on cache misses |
| Relies on documented behaviour | ❌ relies on DuckDB defaults dbt never chose (§5c) | ✅ relies on the published information-schema contract (`info_schema.version: 1`) |
| Shows in `dbt build` / `run_results.json` | ✅ | ❌ separate CI step and exit code |

In CI: `dbt compile --generate-info-schema`, then
`desc-judge --info-schema target/info_schema/v1 --state <main's info_schema/v1> --cache <CI cache>`.
Keep `checks/columns_have_descriptions.sql` as a native check: it is deterministic and free,
and it fails the build before anyone pays for a judgment. The two DuckDB and Jinja mock checks
are there as evidence (5a/5b). Delete them in a real project.

Why the judge doesn't belong inside the check gate even if dbt made it possible: a check runs
on every parse, on every developer's machine, and blocks `dbt build`. An LLM there adds
network, latency, cost and a non-deterministic verdict to a gate whose value is being instant
and repeatable. The judgment is a review step, like a linter in CI, not a build invariant.

Scale notes for the fallback:
- The fingerprint uses the **whole model's** SQL, so editing a model re-judges all its
  columns. Once `column_lineage`/per-column expressions are reliable, the fingerprint can
  narrow to the column's own expression. Only `facts.py` changes.
- The cache is a JSON file, which is fine for thousands of columns. Past ~100k, swap
  `VerdictCache` for a Parquet/DuckDB table with the same `get`/`put`/`save` surface.
- `judge()` gets batches of 32 by default (`--batch-size`). How a Jev judge packs a batch into
  requests is its own business. Demo 04 still defaults to one record per request (`pack: 1`),
  and its gated live runs passed at pack=32 and 64 with the `nested` layout
  (`04-dbt-semantic-tests/jaffle_shop/profiles.yml:12-13`, `docs/pack-layouts.md`). A future
  `JevJudge` should re-run that gate for this question before packing.

## 8. Open questions for dbt-labs/dbt-core#15584

Framed as a use case ("documentation-quality checks that need a judgment, not a rule"), not
as a feature request. Each question points at the line of code it comes from, so maintainers
can answer from the design rather than guess what's being asked.

1. **Is the check database's openness intended?** The check DuckDB runs with stock defaults:
   `enable_external_access=true`, `allow_community_extensions=true`, `autoinstall=true`, no
   `lock_configuration` (`check_adapter.rs:52-54`; nothing in `crates/` sets them). So a check
   can read local files, `INSTALL … FROM community` and make HTTP calls. Is that part of the
   contract, or will the check sandbox be locked down? Either answer is fine; people building on
   checks need to know which.
2. **Will there be a post-compile check tier?** Checks read parse-safe views only, so they can't
   see model SQL, inferred types or `column_lineage` (`parse_safe.rs:103-137, 167`). The code
   mentions an earlier "compile-tier check" (`check.rs:162-164`) and says phase is inferred
   from the rendered check (`nodes.rs:5228`), while the parse-time runner is now "the *only*
   place checks execute" (`check.rs:602`). Is a tier that runs after compile, against the full
   information schema, planned?
3. **Is there an extension point for checks that aren't SQL?** E.g. an external check whose
   command emits rows in the check result shape and flows into the `dbt build` gate and
   `run_results.json`, or a declared input table (`read_parquet` of verdicts written by another
   tool) that is part of the contract instead of relying on `enable_external_access`. dbt-score
   was raised in this discussion as the Python alternative; is interop with such tools in scope?
4. **Can `state:modified` see descriptions?** "`description` is still not compared"
   (`CHANGELOG-dbt.md:394`). For doc-quality checks, a description-only edit is exactly the
   change that matters. Is a `state:modified.descriptions` sub-selector, or column-level state,
   on the table?
5. **Can a check compare against a baseline?** For "only new violations" (ratcheting on a
   legacy project, the exclusion concern raised in this thread), a check would need the deferred
   state's information schema as a second schema, e.g. `info_schema('node_columns', state=true)`.
   Planned?
6. **Where do full violation rows go?** `run_results.json` gets a preview capped at
   `max_preview_rows` (`check.rs:172-185, 533-554`). For CI annotations (one comment per failing
   column), is there, or will there be, a way to get every row, e.g. `--store-failures` for
   checks?
