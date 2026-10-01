"""Build, score, guard and log demo 06's benchmark.

    uv run python scripts/score.py --preregister                      # once, before pass 1
    uv run python scripts/score.py --run --judge databricks-gpt-oss-20b --scope pilot --pass 0 \
        --mode live --append                                          # confirm-first: billed
    uv run python scripts/score.py --usage                            # measured LLM spend so far

`--run` builds the models (no judging), counts the states, checks the $15 budget for an LLM
judge, then runs `dbt build --select +tag:semantic tag:baseline` with the judge (judging), and
scores what dbt stored. `--append` writes the entry to docs/eval-results.md (live only).
"""

import argparse
import csv
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from jevdbx import budget, evallog, keys, metrics
from jevdbx.databricks import Sql

ROOT = Path(__file__).resolve().parents[1]
EVAL, LOG = ROOT / "eval", ROOT / "docs" / "eval-results.md"
AUDIT = "jev_demo.bench_dbt_test__audit"
JUDGMENTS = "jev_demo.bench.judgments"
JUDGES = ["jev", *budget.PRICES]


@dataclass(frozen=True)
class TestSpec:
    name: str
    model: str
    id_cols: list[str]
    state_cols: list[str]
    baseline: str | None


TESTS = {
    "banking_query_not_about_intent": TestSpec(
        "banking_query_not_about_intent", "stg_banking_queries", ["query_id"],
        ["query", "intent"], "baseline_banking_keyword"),
    "pairs_describe_same_product": TestSpec(
        "pairs_describe_same_product", "stg_product_pairs", ["pair_id"],
        ["left_record", "right_record"], "baseline_pairs_jaccard"),
    "wanderbricks_comment_contradicts_rating": TestSpec(
        "wanderbricks_comment_contradicts_rating", "stg_wanderbricks_reviews",
        ["comment", "rating"], ["comment", "rating"], None),
}


def state_expr(cols: list[str]) -> str:
    # Must equal jev_state_expr as rendered by dbt-databricks (backtick quoting; offline dbt
    # renders with double quotes, so this is the Databricks form, not the offline one).
    return "to_json(named_struct(" + ", ".join(f"'{c}', `{c}`" for c in cols) + "))"


def _csv(name: str) -> list[dict]:
    return list(csv.DictReader((EVAL / name).open()))


def row_id(test: str, row: list) -> str:
    if test == "wanderbricks_comment_contradicts_rating":
        return keys.state_id(row[0], float(row[1]))
    return str(row[0])


def universe(sql: Sql, spec: TestSpec) -> set[str]:
    r = sql.run(f"select {', '.join(spec.id_cols)} from jev_demo.bench.{spec.model}")
    return {row_id(spec.name, row) for row in r.rows}


def positives(sql: Sql, spec: TestSpec) -> set[str]:
    if spec.name == "banking_query_not_about_intent":
        return {s["query_id"] for s in _csv("banking77_swaps.csv")}
    if spec.name == "pairs_describe_same_product":
        return {p["pair_id"] for p in _csv("abt_buy_pairs.csv") if p["label"] == "1"}
    polarity = {p["comment_sha256"]: p["polarity"] for p in _csv("wanderbricks_polarity.csv")}
    r = sql.run(f"select comment, rating from jev_demo.bench.{spec.model}")
    return {keys.state_id(c, float(x)) for c, x in r.rows
            if keys.contradiction(polarity[keys.comment_hash(c)], float(x))}


def stored_flags(sql: Sql, spec: TestSpec, judge: str, is_llm: bool):
    r = sql.run(f"select {', '.join(spec.id_cols)}, jev_p, jev_decision, jev_judge, "
                f"jev_invocation_id from {AUDIT}.{spec.name}")
    flagged, unjudged, invs = set(), set(), set()
    for row in r.rows:
        rid = row_id(spec.name, row)
        p, decision, j, inv = row[-4], row[-3], row[-2], row[-1]
        invs.add(inv)
        if j != judge:
            continue
        if p is None and decision is None:
            unjudged.add(rid)
        elif (decision in ("true", True)) if is_llm else p is not None:
            flagged.add(rid)
    return flagged, unjudged, invs


def baseline_flags(sql: Sql, spec: TestSpec) -> set[str]:
    r = sql.run(f"select {', '.join(spec.id_cols)} from {AUDIT}.{spec.baseline}")
    return {row_id(spec.name, row) for row in r.rows}


def refuse_reasons(mode: str, judge: str, invocation_ids: set, errors: int) -> list[str]:
    if mode != "live":
        return ["SIMULATED runs are never logged"]
    if len(invocation_ids) != 1:
        return [f"stored failures from more than one invocation: {sorted(invocation_ids)}"]
    return []


def entry_md(stamp, label, judge, invocation, rows, cost, cost_source, tokens_per_row,
             extra: list[str]) -> str:
    lines = [f"## {stamp} · {label} · {judge}", "", f"- invocation {invocation}", *extra]
    if judge != "jev":
        lines.append(f"- llm cost ${cost:.3f} ({cost_source})")
        for test, (tin, tout) in tokens_per_row.items():
            lines.append(f"- tokens/row {test} in {tin} out {tout} (measured)")
    lines += ["", "| test | rows | positives | flagged | P (95% CI) | R (95% CI) | F1 | unjudged |",
              "|---|---|---|---|---|---|---|---|"]
    for r in rows:
        lines.append(r)
    return "\n".join(lines) + "\n"


def _row(test, s: metrics.Scores, n, pos, unjudged) -> str:
    plo, phi = metrics.wilson(s.tp, s.tp + s.fp)
    rlo, rhi = metrics.wilson(s.tp, s.tp + s.fn)
    return (f"| {test} | {n:,} | {pos:,} | {s.tp + s.fp:,} "
            f"| {s.precision:.2f} ({plo:.2f}–{phi:.2f}) "
            f"| {s.recall:.2f} ({rlo:.2f}–{rhi:.2f}) | {s.f1:.2f} | {unjudged:,} |")


def swap_recall(flagged: set, scope_ids: set, swaps: list[dict]) -> dict[str, tuple[int, int]]:
    """Banking77 recall per swap type (headline 3): (caught, planted) within the scope."""
    out: dict[str, tuple[int, int]] = {}
    for kind in ("random", "near_miss"):
        ids = {s["query_id"] for s in swaps if s["swap_type"] == kind} & scope_ids
        out[kind] = (len(ids & flagged), len(ids))
    return out


def natural_ids(sql: Sql, spec: TestSpec) -> set[str]:
    r = sql.run(f"select comment, rating from jev_demo.bench.{spec.model} where review_rows > 0")
    return {keys.state_id(c, float(x)) for c, x in r.rows}


def false_alarms(flagged: set, natural: set, positives: set) -> tuple[int, int]:
    """Wanderbricks control (spec §2 amendment): flags on natural states the key calls clean."""
    clean = natural - positives
    return (len(flagged & clean), len(clean))


def run_stats(sql: Sql, invocation: str, is_llm: bool) -> dict:
    """Requests, wall time (the hook windows) and, for Jev, the ledger cost of one invocation."""
    inv = invocation.replace("'", "")
    w = sql.run("select coalesce(sum(missing), 0), coalesce(sum(unix_micros(finished_at) - "
                f"unix_micros(started_at)) / 1e6, 0) from jev_demo.bench.hook_runs "
                f"where invocation_id = '{inv}'")
    calls, wall = int(w.rows[0][0]), float(w.rows[0][1])
    if is_llm:
        return {"requests": calls, "wall_s": wall, "jev_cost": None}
    r = sql.run("select count(*), coalesce(sum(pack_tokens), 0) from jev_demo.bench.requests "
                f"where invocation_id = '{inv}'")
    from jevdbx.pricing import cost_usd
    return {"requests": int(r.rows[0][0]), "wall_s": wall, "jev_cost": cost_usd(int(r.rows[0][1]))}


def dbt(*args: str) -> int:
    return subprocess.run([sys.executable, str(ROOT / "scripts" / "dbtw.py"), *args]).returncode


def unmeasured(md: str) -> list[tuple[str, str, str]]:
    """Logged LLM runs whose cost is still an estimate and has no later measured-cost entry."""
    blocks = re.split(r"\n(?=## )", md)
    measured = set()
    for block in blocks:
        inv = re.search(r"^- invocation (\S+)$", block, re.M)
        if inv and " · measured cost · " in block.splitlines()[0]:
            measured.add(inv[1])
    out = []
    for block in blocks:
        m = re.match(r"## \S+ · (pilot|pass \d+) · (\S+)$", block.splitlines()[0])
        inv = re.search(r"^- invocation (\S+)$", block, re.M)
        if m and inv and "(estimated)" in block and inv[1] not in measured:
            out.append((m[1], m[2], inv[1]))
    return out


def measure(append: bool) -> int:
    """Attribute endpoint usage to logged runs whose cost is still estimated (usage lags ~2 h):
    window = the run's hook_runs window ± 5 s; exactly one served entity must have been used."""
    sql = Sql()
    for label, judge, inv in unmeasured(LOG.read_text()):
        w = sql.run("select min(started_at) - interval 5 seconds, max(finished_at) + interval 5 "
                    "seconds from jev_demo.bench.hook_runs where invocation_id = "
                    f"'{inv.replace(chr(39), '')}'")
        start, end = w.rows[0]
        r = sql.run(budget.usage_sql(str(start), str(end)))
        m = budget.window_cost(judge, r.rows) if r.state == "SUCCEEDED" else None
        if m is None:
            print(f"{label} · {judge} · {inv}: usage not attributable yet; try again later")
            continue
        cost, n, i, o = m
        lines = [f"## {datetime.now(UTC).strftime('%Y-%m-%dT%H:%M:%SZ')} · measured cost · "
                 f"{label} · {judge}", "", f"- invocation {inv}",
                 f"- requests {n:,} · tokens in {i:,} out {o:,}",
                 f"- llm cost ${cost:.3f} (measured)"]
        if label == "pilot":
            lines += [f"- tokens/row {t} in {i // n} out {o // n} (measured)" for t in TESTS]
        print("\n".join(lines))
        if append:
            evallog.append(LOG, "\n".join(lines) + "\n")
    return 0


def run(a) -> int:
    sql = Sql()
    is_llm = a.judge != "jev"
    vars_ = json.dumps({"judge": a.judge, "bench_scope": a.scope})
    if dbt("build", "--vars", vars_, "--exclude", "tag:semantic", "tag:baseline") != 0:
        return 1
    md = LOG.read_text()
    if is_llm:
        spent = evallog.llm_spend(md)  # logged runs; measured entries replace estimates
        projected = 0.0
        for test, spec in TESTS.items():
            n = len(universe(sql, spec))
            per_row = (evallog.tokens_per_row(md, a.judge, test)
                       or budget.DEFAULT_TOKENS_PER_ROW[test])
            projected += budget.project(a.judge, n, per_row)
        print(f"budget: spent ${spent:.2f} (logged) + projected ${projected:.2f}"
              f" of ${budget.CAP_USD:.2f}")
        budget.check(spent, projected)
    if a.fresh:
        sql.run(f"delete from {JUDGMENTS} where judge = '{a.judge}' and mode = '{a.mode}'")
    t0 = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S")
    rc = dbt("build", "--vars", vars_, "--select", "+tag:semantic", "tag:baseline")
    t1 = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S")
    rows, invs, errors, extra_lines = [], set(), 0, []
    for test, spec in TESTS.items():
        uni, pos = universe(sql, spec), positives(sql, spec) & universe(sql, spec)
        flagged, unjudged, inv = stored_flags(sql, spec, a.judge, is_llm)
        invs |= inv
        errors += len(unjudged)
        rows.append(_row(test, metrics.score(flagged, pos, uni), len(uni), len(pos), len(unjudged)))
        if test == "banking_query_not_about_intent":
            for kind, (k, n) in swap_recall(flagged, uni, _csv("banking77_swaps.csv")).items():
                lo, hi = metrics.wilson(k, n)
                extra_lines.append(f"- banking recall on {kind} swaps {k}/{n} "
                                   f"({k / n if n else 0:.2f}, 95% {lo:.2f}–{hi:.2f})")
        if test == "wanderbricks_comment_contradicts_rating":
            k, n = false_alarms(flagged, natural_ids(sql, spec), pos)
            lo, hi = metrics.wilson(k, n)
            extra_lines.append(f"- wanderbricks false alarms on natural states {k}/{n} "
                               f"({k / n if n else 0:.2f}, 95% {lo:.2f}–{hi:.2f})")
        if spec.baseline and a.judge == "jev":
            rows.append(_row(spec.baseline, metrics.score(baseline_flags(sql, spec), pos, uni),
                             len(uni), len(pos), 0))
    print("\n".join(rows))
    cost, source, tpr = 0.0, "estimated", {}
    if is_llm:
        r = sql.run(budget.usage_sql(t0, t1))
        m = budget.window_cost(a.judge, r.rows) if r.state == "SUCCEEDED" else None
        if m is not None:
            cost, n_req, i, o = m
            source = "measured"
            if a.scope == "pilot":
                tpr = {t: (i // n_req, o // n_req) for t in TESTS}
        else:
            cost = sum(budget.project(a.judge, len(universe(sql, s)),
                                      budget.DEFAULT_TOKENS_PER_ROW[t]) for t, s in TESTS.items())
    if a.append:
        reasons = refuse_reasons(a.mode, a.judge, invs, errors)
        if rc != 0:
            reasons.append(f"dbt exited {rc}")
        if reasons:
            print("not appended: " + "; ".join(reasons))
            return 1
        label = "pilot" if a.scope == "pilot" else f"pass {a.pass_}"
        inv = next(iter(invs))
        st = run_stats(sql, inv, is_llm)
        n_rows = sum(len(universe(sql, s)) for s in TESTS.values())
        run_cost = cost if is_llm else st["jev_cost"]
        extra = [f"- scope {a.scope} · {n_rows:,} rows · requests {st['requests']:,} · "
                 f"wall time {st['wall_s']:.1f} s",
                 f"- cost per 1,000 rows ${1000 * run_cost / n_rows:.4f}"
                 + ("" if is_llm else f" · jev cost ${run_cost:.4f} (ledger)"),
                 *extra_lines]
        evallog.append(LOG, entry_md(datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"), label,
                                     a.judge, inv, rows, cost, source, tpr, extra))
    return rc


def preregister() -> int:
    md = LOG.read_text()
    if evallog.has_preregistration(md):
        print("pre-registration already present; it is frozen")
        return 1
    out = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "dbtw.py"), "compile", "--select", "tag:semantic"],
        capture_output=True, text=True)
    swaps = _csv("banking77_swaps.csv")
    entry = "\n".join([
        evallog.PREREG, "",
        "- judges: " + ", ".join(JUDGES) + "; temperature 0; prompt version p1",
        "- prompts and test wording: bench/models/staging/schema.yml and "
        "bench/macros/jev_question.sql at commit " + subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True,
            cwd=ROOT).stdout.strip(),
        f"- Banking77: seed 42, sample 2,000 test queries, swaps in sample "
        f"{sum(s['in_sample'] == 'True' for s in swaps)} (75 random + 75 near-miss), "
        "families in eval/intent_families.csv",
        "- Abt-Buy: sample = test split; Jaccard threshold "
        + (EVAL / "abt_buy_jaccard.txt").read_text().strip() + " fit on train",
        "- wanderbricks: every natural (comment, rating) state (the control: false-alarm rate) "
        "+ planted ratings in eval/wanderbricks_flips.csv (seed 42); rule in "
        "jevdbx.keys.contradiction",
        "- headline 1: per dataset, F1 of Jev vs each LLM (decision level), Wilson 95% for P and R",
        "- headline 2: per dataset, cost per 1,000 rows and wall time per judge",
        "- headline 3: Banking77 recall on random vs near-miss swaps, per judge",
        f"- dbt compile exit {out.returncode}", ""])
    evallog.append(LOG, entry)
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", action="store_true")
    ap.add_argument("--judge", choices=JUDGES, default="jev")
    ap.add_argument("--scope", choices=["pilot", "sample", "full"], default="sample")
    ap.add_argument("--pass", dest="pass_", type=int, default=1)
    ap.add_argument("--mode", choices=["live", "demo"])
    ap.add_argument("--append", action="store_true")
    ap.add_argument("--fresh", action="store_true")
    ap.add_argument("--preregister", action="store_true")
    ap.add_argument("--usage", action="store_true")
    ap.add_argument("--measure", action="store_true")
    a = ap.parse_args(argv)
    if a.preregister:
        return preregister()
    if a.usage:
        r = Sql().run(budget.usage_sql(budget.SINCE))
        print(f"endpoint usage since {budget.SINCE} by served entity (no names: spec S2):")
        for row in r.rows:
            print("  ", row)
        return 0
    if a.measure:
        return measure(a.append)
    if a.run:
        if a.mode is None:
            ap.error("--run needs --mode live|demo")
        import os
        os.environ["JEV_MODE"] = a.mode
        return run(a)
    if a.append:
        ap.error("--append needs --run")
    ap.error("nothing to do")
    return 2


if __name__ == "__main__":
    sys.exit(main())
