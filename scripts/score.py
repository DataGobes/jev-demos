"""Build, score, guard and log demo 06's benchmark.

    uv run python scripts/score.py --preregister                      # once, before pass 1
    uv run python scripts/score.py --run --judge databricks-gpt-oss-20b --scope pilot --pass 0 \
        --mode live --append                                          # confirm-first: billed
    uv run python scripts/score.py --measure --append                 # usage lags ~2 h
    uv run python scripts/score.py --usage                            # endpoint usage so far

`--run` checks the pre-registration (live appends) and the ground-truth files, builds the models
(no judging), checks the keys against the tables and the $15 budget for an LLM judge, then runs
`dbt build --select +tag:semantic tag:baseline` with the judge (judging) and scores what dbt stored,
on judged rows only. `--append` writes the entry to docs/eval-results.md (live only). A live LLM
run must `--append` and always ends in an entry: the result, or a refused entry that keeps its spend
in the guard.
"""

import argparse
import csv
import hashlib
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from jevdbx import budget, evallog, keys, metrics, pricing
from jevdbx.databricks import Result, Sql

ROOT = Path(__file__).resolve().parents[1]
EVAL, LOG = ROOT / "eval", ROOT / "docs" / "eval-results.md"
AUDIT = "jev_demo.bench_dbt_test__audit"
JUDGMENTS = "jev_demo.bench.judgments"
JUDGES = ["jev", *budget.PRICES]
# More unjudged (errored) rows than this fraction of a test's in-scope rows: not a result.
UNJUDGED_TOLERANCE = 0.01
# What produces the numbers: pinned by digest at pre-registration (the scorer itself is not: it
# changes no judge input).
FROZEN = ["bench/macros", "bench/models", "bench/seeds", "bench/tests", "bench/dbt_project.yml",
          "eval"]
GROUND_TRUTH = ["banking77_swaps.csv", "abt_buy_pairs.csv", "wanderbricks_polarity.csv",
                "wanderbricks_flips.csv"]
INVOCATION_ID = re.compile(r"^[0-9a-f-]{36}$|^refused-\d{8}T\d{6}Z$")


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


def _q(sql: Sql, text: str) -> Result:
    """Run a read that scoring depends on; a failed statement raises instead of reading as empty."""
    r = sql.run(text)
    if r.state != "SUCCEEDED":
        raise RuntimeError(f"query failed: {r.state}: {(r.error or '')[:300]}")
    return r


def _csv(name: str) -> list[dict]:
    return list(csv.DictReader((EVAL / name).open()))


def row_id(test: str, row: list) -> str:
    if test == "wanderbricks_comment_contradicts_rating":
        return keys.state_id(row[0], float(row[1]))
    return str(row[0])


def universe(sql: Sql, spec: TestSpec) -> set[str]:
    r = _q(sql, f"select {', '.join(spec.id_cols)} from jev_demo.bench.{spec.model}")
    return {row_id(spec.name, row) for row in r.rows}


def positives(sql: Sql, spec: TestSpec) -> set[str]:
    if spec.name == "banking_query_not_about_intent":
        return {s["query_id"] for s in _csv("banking77_swaps.csv")}
    if spec.name == "pairs_describe_same_product":
        return {p["pair_id"] for p in _csv("abt_buy_pairs.csv") if p["label"] == "1"}
    polarity = {p["comment_sha256"]: p["polarity"] for p in _csv("wanderbricks_polarity.csv")}
    r = _q(sql, f"select comment, rating from jev_demo.bench.{spec.model}")
    return {keys.state_id(c, float(x)) for c, x in r.rows
            if keys.contradiction(polarity[keys.comment_hash(c)], float(x))}


def stored_flags(sql: Sql, spec: TestSpec, judge: str, is_llm: bool):
    r = _q(sql, f"select {', '.join(spec.id_cols)}, jev_p, jev_decision, jev_judge, "
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
    r = _q(sql, f"select {', '.join(spec.id_cols)} from {AUDIT}.{spec.baseline}")
    return {row_id(spec.name, row) for row in r.rows}


def judged_scores(flagged: set, unjudged: set, pos: set, uni: set):
    """Scores on judged rows only: an unjudged (errored) row is neither a pass nor a fail."""
    judged = uni - unjudged
    pos_j = pos & judged
    return metrics.score(flagged & judged, pos_j, judged), judged, pos_j


def refuse_reasons(mode: str, judge: str, invocation_ids: set, unjudged_by_test: dict[str, int],
                   rows_by_test: dict[str, int]) -> list[str]:
    if mode != "live":
        return ["SIMULATED runs are never logged"]
    out = []
    if not invocation_ids:
        out.append("no stored failures read")
    elif len(invocation_ids) > 1:
        out.append(f"stored failures from more than one invocation: {sorted(invocation_ids)}")
    for test, n in rows_by_test.items():
        u = unjudged_by_test.get(test, 0)
        if n and u / n > UNJUDGED_TOLERANCE:
            out.append(f"{test}: {u:,} of {n:,} in-scope rows unjudged by {judge} ({u / n:.1%} > "
                       f"{UNJUDGED_TOLERANCE:.0%}); rerun to fill them (errored rows are not "
                       "cached as successes, so a rerun re-calls only those)")
    return out


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
    r = _q(sql, f"select comment, rating from jev_demo.bench.{spec.model} "
                f"where review_rows > 0")
    return {keys.state_id(c, float(x)) for c, x in r.rows}


def false_alarms(flagged: set, natural: set, positives: set) -> tuple[int, int]:
    """Wanderbricks control (spec §2 amendment): flags on natural states the key calls clean."""
    clean = natural - positives
    return (len(flagged & clean), len(clean))


_HOOK_WALL = "coalesce((unix_micros(max(finished_at)) - unix_micros(min(started_at))) / 1e6, 0)"


def run_stats(sql: Sql, invocation: str, is_llm: bool) -> dict:
    """One invocation: overall {requests, judged, wall_s, tokens} (wall = first hook start to last
    hook end; tokens = Jev pack tokens from the ledger, or the LLM's estimated prompt tokens) and
    per_test {judged, wall_s, jev_cost | est_tokens}."""
    inv = invocation.replace("'", "")
    hooks = "jev_demo.bench.hook_runs"
    o = _q(sql, f"select coalesce(sum(missing), 0), {_HOOK_WALL} from {hooks} "
                f"where invocation_id = '{inv}'").rows[0]
    per_test = {t: {"judged": int(n), "wall_s": float(w)} for t, n, w in _q(
        sql, f"select test_name, coalesce(sum(missing), 0), {_HOOK_WALL} from {hooks} "
             f"where invocation_id = '{inv}' group by test_name").rows}
    judged = int(o[0])
    if is_llm:
        for t, est in _q(sql, "select test_name, coalesce(sum(pack_est_tokens), 0) from "
                              f"{JUDGMENTS} where invocation_id = '{inv}' group by test_name").rows:
            per_test.setdefault(t, {"judged": 0, "wall_s": 0.0})["est_tokens"] = int(est)
        for d in per_test.values():
            d.setdefault("est_tokens", 0)
        requests = judged
        tokens = sum(d["est_tokens"] for d in per_test.values())
    else:
        requests = tokens = 0
        for t, n, tok in _q(sql, "select test_name, count(*), coalesce(sum(pack_tokens), 0) from "
                                 f"jev_demo.bench.requests where invocation_id = '{inv}' "
                                 "group by test_name").rows:
            requests += int(n)
            tokens += int(tok)
            per_test.setdefault(t, {"judged": 0, "wall_s": 0.0})["jev_cost"] = \
                pricing.cost_usd(int(tok))
        for d in per_test.values():
            d.setdefault("jev_cost", 0.0)
    return {"requests": requests, "judged": judged, "wall_s": float(o[1]), "tokens": tokens,
            "per_test": per_test}


def window_judged(sql: Sql, judge: str, since: str, until: str | None = None) -> dict[str, int]:
    """States this judge judged per test in [since, until) (UTC, from the hook windows)."""
    until_sql = f" and started_at < timestamp'{until}'" if until else ""
    r = _q(sql, "select test_name, coalesce(sum(missing), 0) from jev_demo.bench.hook_runs "
                f"where judge = '{judge}' and started_at >= timestamp'{since}'{until_sql} "
                "group by test_name")
    return {t: int(n) for t, n in r.rows}


def usage_verdict(m, judged: int) -> tuple[bool, list[str]]:
    """Whether a window's usage (cost, requests, in, out) stands as the run's measured cost: only
    when it covers every row judged now (usage lags; less means it has not all landed)."""
    if m is None:
        return False, []
    n = m[1]
    lines = [f"- usage requests {n:,} vs judged {judged:,}"]
    if judged == 0 or n < judged:
        return False, lines
    if n > 1.05 * judged:
        lines.append(f"- usage check: {n:,} requests for {judged:,} judged rows "
                     "(possible duplicate evaluation)")
        print(f"WARNING: {n:,} requests for {judged:,} judged rows (possible duplicate evaluation)")
    return True, lines


def estimate(judge: str, md: str, judged_per_test: dict[str, int]) -> float:
    """Estimated LLM cost of the rows judged now: tokens/row (pilot-measured, else default)."""
    return sum(budget.project(judge, judged_per_test.get(t, 0),
                              evallog.tokens_per_row(md, judge, t)
                              or budget.DEFAULT_TOKENS_PER_ROW[t]) for t in TESTS)


def llm_cost(sql: Sql, judge: str, md: str, window: tuple[str, str],
             judged_per_test: dict[str, int]):
    """(cost, source, accepted usage or None, usage lines) for one LLM run's window."""
    try:  # tolerant: a failed or empty usage read stays estimated
        r = sql.run(budget.usage_sql(*window))
        m = budget.window_cost(judge, r.rows) if r.state == "SUCCEEDED" else None
    except Exception as e:  # noqa: BLE001
        print(f"usage read failed ({type(e).__name__}); cost stays estimated")
        m = None
    ok, lines = usage_verdict(m, sum(judged_per_test.values()))
    if ok:
        return m[0], "measured", m, lines
    return estimate(judge, md, judged_per_test), "estimated", None, lines


def headline2_lines(per_test: dict, run_cost: float, source: str, is_llm: bool) -> list[str]:
    """Headline 2, per dataset, on rows judged now (cached rows cost nothing and take no time).
    An LLM run's measured/estimated cost is split across tests by estimated tokens."""
    total_est = sum(d["est_tokens"] for d in per_test.values()) if is_llm else 0
    total_judged = sum(d["judged"] for d in per_test.values())
    out = []
    for test, d in per_test.items():
        n, head = d["judged"], (f"- headline 2 · {test} · judged now {d['judged']:,} · "
                                f"wall time {d['wall_s']:.1f} s · cost per 1,000 judged rows ")
        if n == 0:
            out.append(head + "n/a (all cached)")
        elif is_llm:
            share = (d["est_tokens"] / total_est if total_est else n / total_judged)
            out.append(head + f"${1000 * run_cost * share / n:.4f} "
                              f"({source}, split by estimated tokens)")
        else:
            out.append(head + f"${1000 * d['jev_cost'] / n:.4f} (ledger)")
    return out


def refused_md(stamp: str, label: str, judge: str, invs: set, cost: float, reasons: list[str],
               window: tuple[str, str], source: str = "estimated", extra=()) -> str:
    """A billed run that is not a result: logged cost-only so the $15 guard still counts it. The
    invocation is the real one when exactly one, else refused-<stamp> (so --measure can settle
    it from the window and llm_spend can replace the estimate)."""
    inv = (next(iter(invs)) if len(invs) == 1
           else "refused-" + stamp.replace("-", "").replace(":", ""))
    lines = [f"## {stamp} · refused · {label} · {judge}", "",
             f"- not a result: {'; '.join(reasons)}", f"- invocation {inv}",
             f"- window {window[0]} {window[1]} (UTC)", *extra,
             f"- llm cost ${cost:.3f} ({source})"]
    return "\n".join(lines) + "\n"


def _logged(md: str, inv: str) -> bool:
    return re.search(rf"^- invocation {re.escape(inv)}$", md, re.M) is not None


def _iso(t: datetime) -> str:
    return t.strftime("%Y-%m-%dT%H:%M:%S")


def _stamp() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _label(a) -> str:
    return "pilot" if a.scope == "pilot" else f"pass {a.pass_}"


def write_refused(sql: Sql, a, window: tuple[str, str], invs: set, projected: float,
                  reasons: list[str]) -> None:
    """Append the refused entry of a billed live LLM run. Its cost is measured when usage covers
    the rows judged in the window, else max(window estimate, pre-run projection): never $0.
    Reads here are tolerant: the run may have failed because reads fail."""
    md = LOG.read_text()
    invs = {i for i in invs if not _logged(md, i)}  # a stale audit invocation is never reused
    try:
        judged = window_judged(sql, a.judge, *window)
        cost, source, m, extra = llm_cost(sql, a.judge, md, window, judged)
        if m is not None:
            extra = [*extra, f"- tokens in {m[2]:,} out {m[3]:,} (measured)"]
        else:
            cost = max(cost, projected)
    except Exception as e:  # noqa: BLE001
        cost, source = projected, "estimated"
        extra = [f"- cost not read after the build ({type(e).__name__}); the pre-run projection "
                 "stands"]
    evallog.append(LOG, refused_md(_stamp(), _label(a), a.judge, invs, cost, reasons, window,
                                   source, extra))


def dbt(*args: str) -> int:
    return subprocess.run([sys.executable, str(ROOT / "scripts" / "dbtw.py"), *args]).returncode


def unmeasured(md: str) -> list[tuple[str, str, str]]:
    """Logged LLM runs (results and refused) whose cost is still an estimate and has no later
    measured-cost entry: (label, judge, invocation); a refused label reads `refused · <label>`."""
    blocks = re.split(r"\n(?=## )", md)
    measured = set()
    for block in blocks:
        inv = re.search(r"^- invocation (\S+)$", block, re.M)
        if inv and " · measured cost · " in block.splitlines()[0]:
            measured.add(inv[1])
    out = []
    for block in blocks:
        m = re.match(r"## \S+ · (refused · )?(pilot|pass \d+) · (\S+)$", block.splitlines()[0])
        inv = re.search(r"^- invocation (\S+)$", block, re.M)
        if m and inv and "(estimated)" in block and inv[1] not in measured:
            out.append(((m[1] or "") + m[2], m[3], inv[1]))
    return out


def entry_window(md: str, inv: str) -> tuple[str, str] | None:
    """The `- window <t0> <t1>` recorded by the run entry of this invocation, if any."""
    for block in re.split(r"\n(?=## )", md):
        if " · measured cost · " in block.splitlines()[0] or not _logged(block, inv):
            continue
        w = re.search(r"^- window (\S+) (\S+)", block, re.M)
        if w:
            return w[1], w[2]
    return None


def measure(append: bool) -> int:
    """Attribute endpoint usage to logged runs (results and refused) whose cost is still estimated
    (usage lags ~2 h): window = the entry's `- window` line, else the run's hook_runs window ± 5 s;
    exactly one served entity must have been used, and its requests must cover the rows judged."""
    sql = Sql()
    md = LOG.read_text()
    skipped = 0
    for label, judge, inv in unmeasured(md):
        if not INVOCATION_ID.match(inv):
            print(f"{label} · {judge} · {inv!r}: invalid invocation id; skipped")
            skipped += 1
            continue
        window = entry_window(md, inv)
        if window is None and inv.startswith("refused-"):
            print(f"{label} · {judge} · {inv}: no window recorded; cannot attribute usage")
            continue
        if window is None:
            w = _q(sql, "select min(started_at) - interval 5 seconds, max(finished_at) + interval "
                        f"5 seconds from jev_demo.bench.hook_runs where invocation_id = '{inv}'")
            start, end = w.rows[0]
            if start is None or end is None:
                print(f"{label} · {judge} · {inv}: no hook window recorded; cannot attribute usage")
                continue
            window = (str(start), str(end))
        if label.startswith("refused") or inv.startswith("refused-"):
            judged = sum(window_judged(sql, judge, *window).values())
        else:
            judged = int(_q(sql, "select coalesce(sum(missing), 0) from jev_demo.bench.hook_runs "
                                 f"where invocation_id = '{inv}'").rows[0][0])
        r = sql.run(budget.usage_sql(*window))
        m = budget.window_cost(judge, r.rows) if r.state == "SUCCEEDED" else None
        ok, usage_lines = usage_verdict(m, judged)
        if not ok:
            print(f"{label} · {judge} · {inv}: usage not attributable yet "
                  f"({'; '.join(x[2:] for x in usage_lines) or 'no single served entity'}); "
                  "try again later")
            continue
        cost, n, i, o = m
        lines = [f"## {_stamp()} · measured cost · {label} · {judge}", "", f"- invocation {inv}",
                 f"- requests {n:,} · tokens in {i:,} out {o:,}", *usage_lines,
                 f"- llm cost ${cost:.3f} (measured)"]
        if label == "pilot":
            lines += [f"- tokens/row {t} in {i // n} out {o // n} (measured)" for t in TESTS]
        print("\n".join(lines))
        if append:
            evallog.append(LOG, "\n".join(lines) + "\n")
    return 1 if skipped else 0


def _git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True,
                          check=True).stdout


def frozen_digest() -> str:
    """sha256 of `git ls-files -s` over FROZEN: blob ids of everything that produces the numbers."""
    return hashlib.sha256(_git("ls-files", "-s", "--", *FROZEN).encode()).hexdigest()


def frozen_dirty() -> bool:
    return bool(_git("status", "--porcelain", "--", *FROZEN).strip())


def prereg_reasons(md: str) -> list[str]:
    """Why a live append cannot count: no pre-registration, or the frozen paths moved since."""
    if not evallog.has_preregistration(md):
        return ["no pre-registration in docs/eval-results.md (run --preregister first)"]
    out = []
    if frozen_dirty():
        out.append("frozen paths have uncommitted changes: " + " ".join(FROZEN))
    m = re.search(r"^- frozen digest ([0-9a-f]{64})\b", md, re.M)
    if m is None:
        out.append("the pre-registration records no frozen digest")
    elif (d := frozen_digest()) != m[1]:
        out.append(f"frozen paths changed since pre-registration (digest {d[:12]}… != "
                   f"{m[1][:12]}…)")
    return out


def missing_ground_truth() -> list[str]:
    missing = [f"eval/{n}" for n in GROUND_TRUTH if not (EVAL / n).is_file()]
    return [f"ground truth missing: {', '.join(missing)}"] if missing else []


def preflight(sql: Sql) -> list[str]:
    """Keys against the built tables, before any billed build: every wanderbricks comment has a
    polarity label and the Jaccard baseline has exactly one threshold."""
    out = []
    labelled = {p["comment_sha256"] for p in _csv("wanderbricks_polarity.csv")}
    comments = _q(sql, "select distinct comment from jev_demo.bench.stg_wanderbricks_reviews "
                       "where comment is not null").rows
    unlabelled = [c for (c,) in comments if keys.comment_hash(c) not in labelled]
    if unlabelled:
        out.append(f"{len(unlabelled)} of {len(comments)} wanderbricks comments have no polarity "
                   "label in eval/wanderbricks_polarity.csv")
    n = int(_q(sql, "select count(*) from jev_demo.bench.baseline_params "
                    "where name = 'abt_jaccard_threshold'").rows[0][0])
    if n != 1:
        out.append(f"jev_demo.bench.baseline_params has {n} abt_jaccard_threshold rows "
                   "(needs exactly 1)")
    return out


def run(a) -> int:
    is_llm = a.judge != "jev"
    live_llm = is_llm and a.mode == "live"
    if live_llm and not a.append:
        print("refused: live LLM runs must be logged: pass --append")
        return 1
    md = LOG.read_text()
    reasons = missing_ground_truth() if a.mode == "live" else []
    if a.append and a.mode == "live":
        reasons = prereg_reasons(md) + reasons
    if reasons:
        print("refused before any build: " + "; ".join(reasons))
        return 1
    sql = Sql()
    vars_ = json.dumps({"judge": a.judge, "bench_scope": a.scope})
    if dbt("build", "--vars", vars_, "--exclude", "tag:semantic", "tag:baseline") != 0:
        return 1
    if a.mode == "live" and (reasons := preflight(sql)):
        print("refused before the judging build: " + "; ".join(reasons))
        return 1
    projected = 0.0
    if is_llm:
        spent = evallog.llm_spend(md)  # logged runs; measured entries replace estimates
        for test, spec in TESTS.items():
            n = len(universe(sql, spec))
            per_row = (evallog.tokens_per_row(md, a.judge, test)
                       or budget.DEFAULT_TOKENS_PER_ROW[test])
            projected += budget.project(a.judge, n, per_row)
        print(f"budget: spent ${spent:.2f} (logged) + {budget.MARGIN} × projected "
              f"${projected:.2f} = ${spent + budget.MARGIN * projected:.2f} "
              f"of ${budget.CAP_USD:.2f}")
        budget.check(spent, projected)
    if a.fresh:
        _q(sql, f"delete from {JUDGMENTS} where judge = '{a.judge}' and mode = '{a.mode}'")
    t0, t1 = _iso(datetime.now(UTC)), None
    logged: list[bool] = []
    try:  # billed from here: a live LLM run always ends in an entry (result or refused)
        rc = dbt("build", "--vars", vars_, "--select", "+tag:semantic", "tag:baseline")
        t1 = _iso(datetime.now(UTC) + timedelta(seconds=1))  # ceil: the window covers the build
        return finish(sql, a, md, rc, (t0, t1), projected, logged)
    except BaseException as e:
        if live_llm and not logged:
            window = (t0, t1 or _iso(datetime.now(UTC) + timedelta(seconds=1)))
            write_refused(sql, a, window, set(), projected, [f"{type(e).__name__}: {e}"[:300]])
        raise


def finish(sql: Sql, a, md: str, rc: int, window: tuple[str, str], projected: float,
           logged: list) -> int:
    """Score what the judging build stored (judged rows only) and log the entry."""
    is_llm = a.judge != "jev"
    rows, invs, extra_lines = [], set(), []
    unjudged_by, rows_by = {}, {}
    for test, spec in TESTS.items():
        uni = universe(sql, spec)
        pos = positives(sql, spec) & uni
        flagged, unjudged, inv = stored_flags(sql, spec, a.judge, is_llm)
        invs |= inv
        s, judged, pos_j = judged_scores(flagged, unjudged, pos, uni)
        unjudged_by[test], rows_by[test] = len(uni - judged), len(uni)
        rows.append(_row(test, s, len(judged), len(pos_j), len(uni - judged)))
        if test == "banking_query_not_about_intent":
            for kind, (k, n) in swap_recall(flagged, judged, _csv("banking77_swaps.csv")).items():
                lo, hi = metrics.wilson(k, n)
                extra_lines.append(f"- banking recall on {kind} swaps {k}/{n} "
                                   f"({k / n if n else 0:.2f}, 95% {lo:.2f}–{hi:.2f})")
        if test == "wanderbricks_comment_contradicts_rating":
            k, n = false_alarms(flagged, natural_ids(sql, spec) & judged, pos_j)
            lo, hi = metrics.wilson(k, n)
            extra_lines.append(f"- wanderbricks false alarms on natural states {k}/{n} "
                               f"({k / n if n else 0:.2f}, 95% {lo:.2f}–{hi:.2f})")
        if spec.baseline and a.judge == "jev":
            name = spec.baseline
            if a.scope == "full" and test == "pairs_describe_same_product":
                name += " (threshold fit on train; train in scope)"
            rows.append(_row(name, metrics.score(baseline_flags(sql, spec), pos, uni),
                             len(uni), len(pos), 0))
    print("\n".join(rows))
    if not a.append:
        return rc
    reasons = refuse_reasons(a.mode, a.judge, invs, unjudged_by, rows_by)
    if rc != 0:
        reasons.append(f"dbt exited {rc}")
    if len(invs) == 1 and _logged(md, next(iter(invs))):
        reasons.append(f"invocation {next(iter(invs))} is already in the log (stale stored "
                       "failures)")
    if reasons:
        if a.mode == "live" and is_llm:  # billed but not a result: the guard must count it
            write_refused(sql, a, window, invs, projected, reasons)
            logged.append(True)
        print("not appended as a result: " + "; ".join(reasons))
        return 1
    inv = next(iter(invs))
    st = run_stats(sql, inv, is_llm)
    extra = [f"- scope {a.scope} · {sum(rows_by.values()):,} rows in scope · scored on judged "
             f"rows (unjudged excluded) · {st['judged']:,} judged now · "
             f"requests {st['requests']:,} · wall time {st['wall_s']:.1f} s "
             "(first hook start to last hook end)"]
    cost, source, tpr = 0.0, "ledger", {}
    if is_llm:
        judged_now = {t: d["judged"] for t, d in st["per_test"].items()}
        cost, source, m, usage_lines = llm_cost(sql, a.judge, md, window, judged_now)
        if m is not None:
            tokens = f"- tokens in {m[2]:,} out {m[3]:,} (measured)"
            if a.scope == "pilot":
                tpr = {t: (m[2] // m[1], m[3] // m[1]) for t in TESTS}
        else:
            est = sum(d["est_tokens"] for d in st["per_test"].values())
            tokens = f"- tokens in ~{est:,} (estimated)"
        extra += [f"- window {window[0]} {window[1]} (UTC)", tokens, *usage_lines]
        run_cost = cost
    else:
        extra.append(f"- tokens in {st['tokens']:,} (ledger)")
        run_cost = sum(d["jev_cost"] for d in st["per_test"].values())
    extra += [*headline2_lines(st["per_test"], run_cost, source, is_llm), *extra_lines]
    evallog.append(LOG, entry_md(_stamp(), _label(a), a.judge, inv, rows, cost, source, tpr,
                                 extra))
    logged.append(True)
    return rc


THRESHOLD = 0.8  # every jev_expect in schema.yml (a test keeps them equal)


def judged_rows(sql: Sql, spec: TestSpec) -> dict[str, dict[str, tuple]]:
    ids = ", ".join(f"m.`{c}`" for c in spec.id_cols)
    r = _q(
        sql, f"select {ids}, j.judge, j.p, j.decision from jev_demo.bench.{spec.model} m "
        # unqualified state columns resolve to m: judgments has no column with those names
        f"join {JUDGMENTS} j on j.state = {state_expr(spec.state_cols)} "
        f"and j.test_name = '{spec.name}' and j.mode = 'live' "
        f"and (j.p is not null or j.decision is not null)")
    out: dict[str, dict[str, tuple]] = {}
    for row in r.rows:
        rid = row_id(spec.name, row[: len(spec.id_cols)])
        judge, p, d = row[len(spec.id_cols):]
        out.setdefault(judge, {})[rid] = (None if p is None else float(p),
                                          None if d is None else d in ("true", True))
    return out


def _flags(judge: str, rows: dict[str, tuple]) -> set[str]:
    if judge == "jev":
        return {i for i, (p, _) in rows.items() if p is not None and p >= THRESHOLD}
    return {i for i, (_, d) in rows.items() if d}


def one_question(sql: Sql, spec: TestSpec) -> None:
    """--compare reads judgments by state: refuse if a test was judged under more than one question
    (a prompt change after pre-registration)."""
    n = int(_q(sql, f"select count(distinct question) from {JUDGMENTS} where test_name = "
                    f"'{spec.name}' and mode = 'live' and (p is not null or decision is not null)"
               ).rows[0][0])
    if n > 1:
        raise RuntimeError(f"{spec.name}: {n} distinct questions among live judgments; "
                           "compare needs one")


def common_universe(per: dict[str, dict], judges: list[str]) -> set[str]:
    """Ids judged (successfully, live) by every judge: the side analyses compare like with like."""
    return set.intersection(*(set(per.get(j, {})) for j in judges))


def side_md(test: str, per_judge: dict, pos: set, uni: set) -> str:
    lines = [f"### {test}", "",
             f"common universe: {len(uni):,} ids judged live by every judge", "",
             "| judge | Brier | reliability (bin: observed, n) | thresholded F1 |",
             "|---|---|---|---|"]
    for judge, rows in per_judge.items():
        ids = sorted(i for i in rows if i in uni and rows[i][0] is not None)
        probs = [rows[i][0] for i in ids]
        labels = [i in pos for i in ids]
        b = f"{metrics.brier(probs, labels):.2f}" if ids else "n/a"  # undefined without data
        rel = "; ".join(f"{lo:.1f}-{hi:.1f}: {rate:.2f}, {n}"
                       for lo, hi, rate, n in metrics.reliability(probs, labels, bins=5) if n)
        thr = {i for i in ids if rows[i][0] >= THRESHOLD}
        f1 = metrics.score(thr, pos, uni).f1
        thr_f1 = "(the decision rule)" if judge == "jev" else f"{f1:.2f}" if ids else "n/a"
        lines.append(f"| {judge} | {b} | {rel} | {thr_f1} |")
    flags = {j: _flags(j, rows) for j, rows in per_judge.items()}
    a = metrics.agreement(flags, pos)
    lines += ["", "agreement on positives: " + " · ".join(
        f"{k.replace('only_', 'only ')} {v}" for k, v in a.items())]
    every = set.intersection(*flags.values()) - pos if flags else set()
    lines.append("possible key errors (flagged by every judge, not in the key): "
                 + (", ".join(sorted(every)[:50]) or "none"))
    return "\n".join(lines) + "\n"


def preregister() -> int:
    md = LOG.read_text()
    if evallog.has_preregistration(md):
        print("pre-registration already present; it is frozen")
        return 1
    reasons = []
    if frozen_dirty():
        reasons.append("frozen paths have uncommitted changes (commit them first): "
                       + " ".join(FROZEN))
    missing = [f"eval/{n}" for n in ("wanderbricks_polarity.csv", "wanderbricks_flips.csv")
               if not (EVAL / n).is_file()]
    if missing:
        reasons.append("ground truth missing: " + ", ".join(missing))
    if reasons:
        print("refused: " + "; ".join(reasons))
        return 1
    rc = dbt("compile", "--select", "tag:semantic")
    if rc != 0:
        print(f"refused: dbt compile exited {rc}")
        return 1
    swaps = _csv("banking77_swaps.csv")
    entry = "\n".join([
        evallog.PREREG, "",
        "- judges: " + ", ".join(JUDGES) + "; temperature 0; prompt version p1",
        "- prompts and test wording: bench/models/staging/schema.yml and "
        "bench/macros/jev_question.sql at commit " + _git("rev-parse", "--short", "HEAD").strip(),
        f"- frozen digest {frozen_digest()} (sha256 of `git ls-files -s -- {' '.join(FROZEN)}`; "
        "a live append is refused when it differs or those paths are dirty)",
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
        f"- unjudged tolerance {UNJUDGED_TOLERANCE:.0%} of in-scope rows per test (more is not a "
        "result; rerun to fill)",
        f"- budget margin {budget.MARGIN} on projections",
        f"- dbt compile exit {rc}", ""])
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
    ap.add_argument("--compare", action="store_true")
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
    if a.compare:
        sql = Sql()
        parts = []
        for test, spec in TESTS.items():
            one_question(sql, spec)
            per = judged_rows(sql, spec)
            missing = [j for j in JUDGES if j not in per]
            if missing:
                print(f"{test}: no live judgments yet for {missing}; nothing compared")
                return 1
            common = common_universe(per, JUDGES)
            per = {j: {i: v for i, v in per[j].items() if i in common} for j in JUDGES}
            parts.append(side_md(test, per, positives(sql, spec) & common, common))
        text = "\n".join(parts)
        print(text)
        if a.append:
            evallog.append(LOG, f"## {datetime.now(UTC).strftime('%Y-%m-%dT%H:%M:%SZ')} · side "
                                f"analyses · {a.scope}\n\n{text}")
        return 0
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
