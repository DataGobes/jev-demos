"""Scorecards: stored Jev and regex-baseline test failures on Databricks vs the hidden golden key.

Numbers printed here are the ones that go in the public post, so this module has no invented
fallbacks: a missing table or a missing run is reported, never papered over. A demo-mode run is
always labelled SIMULATED and `--append` refuses it.

    uv run python scripts/score.py --run --fresh --mode demo     # smoke test, no live calls
    uv run python scripts/score.py --run --fresh --mode live --append   # the recorded yardstick run
    uv run python scripts/score.py --run --production --rerun --mode live --append
    uv run python scripts/score.py                               # score what is already stored

Stored failures are read from jev_demo.jaffle_shop_dbt_test__audit.<test>; run provenance (mode,
model, requests, tokens, retries, 429s, errors) from jev_demo.jev.hook_runs and .requests for the
latest invocation of the scored tests. dbt runs only through scripts/dbtw.py.
"""

import argparse
import csv
import datetime as dt
import json
import math
import os
import re
import subprocess
import sys
from dataclasses import dataclass, replace
from pathlib import Path

import yaml
from rich.console import Console

from jevdbx.pricing import cost_usd

ROOT = Path(__file__).resolve().parents[1]
JAFFLE_DIR = ROOT / "jaffle_shop"
GOLDEN_PATH = ROOT / "eval" / "golden_defects.csv"
REFERENCE_PATH = ROOT / "eval" / "demo04_reference.json"
FLIPS_PATH = ROOT / "eval" / "production_flips.csv"
LABELS_PATH = ROOT / "eval" / "production_audit_labels.csv"
AUDIT_SAMPLE_PATH = ROOT / "data" / "production_audit.csv"
DOCS_PATH = ROOT / "docs" / "eval-results.md"

AUDIT_SCHEMA = "jev_demo.jaffle_shop_dbt_test__audit"
LEDGER = "jev_demo.jev"

# yardstick test name -> id column of the underlying model
TESTS = {
    "customers_full_name_is_a_person": "customer_id",
    "returns_comment_matches_reason_code": "return_id",
    "reviews_body_matches_stars": "review_id",
    "tickets_body_has_no_pii": "ticket_id",
}
PROD_TEST = "product_reviews_body_matches_stars"
PROD_ID = "review_id"

PRECISION_MIN = RECALL_MIN = 0.85
PENDING_REASONS = {"audited precision: audit pending", "rerun not checked (use --rerun)"}
_ANSI = re.compile(r"\x1b\[[0-9;]*m")
_DONE = re.compile(r"Done\.\s.*?ERROR=(\d+)")
_ONCE_RE = re.compile(r"once-per-row VIOLATED")
_SAFE = re.compile(r"^[A-Za-z0-9_.-]+$")


# ---------------------------------------------------------------------------------------------
# pure: metrics
# ---------------------------------------------------------------------------------------------


class NotCaptured(ValueError):
    """The scored run's provenance could not be established. Never append such a run."""


@dataclass(frozen=True)
class Metrics:
    flagged: int
    tp: int
    fp: int
    fn: int
    hard_neg_flagged: int
    precision: float
    recall: float
    f1: float


def load_golden(path: str | Path) -> dict[str, dict[int, str]]:
    """`eval/golden_defects.csv` (test_name, id, label, note) -> {test_name: {id: label}}."""
    golden: dict[str, dict[int, str]] = {}
    with open(path, newline="") as f:
        for row in csv.DictReader(f):
            golden.setdefault(row["test_name"], {})[int(row["id"])] = row["label"]
    return golden


def metrics(flagged: set[int], golden: dict[int, str]) -> Metrics:
    """Precision/recall/F1 of `flagged` ids against a test's {id: label} golden key."""
    flagged = set(flagged)
    defects = {i for i, label in golden.items() if label == "defect"}
    hard_negs = {i for i, label in golden.items() if label == "hard_negative"}
    tp = len(flagged & defects)
    fp = len(flagged - defects)
    fn = len(defects - flagged)
    hard_neg_flagged = len(flagged & hard_negs)
    precision = tp / len(flagged) if flagged else 0.0
    recall = tp / len(defects) if defects else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    return Metrics(len(flagged), tp, fp, fn, hard_neg_flagged, precision, recall, f1)


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """Wilson score interval for k successes in n trials (95% by default)."""
    if n <= 0:
        return (0.0, 1.0)
    p = k / n
    denom = 1 + z * z / n
    center = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return (max(0.0, center - half), min(1.0, center + half))


def audited_precision(
    planted_tp: int, unplanted_flagged: int, audit: dict[int, str]
) -> tuple[float, float, float]:
    """Precision of all flagged rows: planted true positives plus the audited sample's share of
    real mismatches extrapolated to every flagged-but-unplanted row. Returns (point, lo, hi);
    the interval is the 95% Wilson interval of that share, scaled to the unplanted flags."""
    bad = {label for label in audit.values() if label not in ("real", "ok")}
    if bad:
        raise ValueError(f"audit label must be 'real' or 'ok', got {sorted(bad)}")
    total = planted_tp + unplanted_flagged
    if total == 0:
        return (0.0, 0.0, 0.0)
    if unplanted_flagged == 0:
        raw = planted_tp / total
        return (raw, raw, raw)
    if not audit:
        raise ValueError("audit labels are required when unplanted rows are flagged")
    real = sum(1 for label in audit.values() if label == "real")
    lo, hi = wilson(real, len(audit))
    share = real / len(audit)

    def at(s: float) -> float:
        return (planted_tp + s * unplanted_flagged) / total

    return (at(share), at(lo), at(hi))


# ---------------------------------------------------------------------------------------------
# pure: run provenance
# ---------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Run:
    """One dbt invocation's provenance, read from hook_runs + requests + judgments."""

    mode: str = "live"  # live | demo
    requested_model: str = ""
    answered_model: str | None = None
    invocation_id: str = ""
    tested: int = 0
    missing: int = 0
    inserted: int = 0
    oversized: int = 0
    unjudged: int = 0
    packs: int = 0
    pack_rows: int = 0
    tokens: int = 0
    est_tokens: int = 0
    retries: int = 0
    throttled: int = 0
    error_packs: int = 0
    span_s: float = 0.0
    dups: int = 0
    budget: int = 0
    dbt_reported_violation: bool = False

    @property
    def simulated(self) -> bool:
        return self.mode == "demo"

    @property
    def live(self) -> bool:
        return self.mode == "live"

    @property
    def judgments(self) -> int:
        """Distinct (test, state) pairs judged: demo 04's 'unique'."""
        return self.tested - self.unjudged

    @property
    def cached_pct(self) -> float:
        return (self.tested - self.missing) * 100 / self.tested if self.tested else 0.0

    @property
    def errors(self) -> int:
        return self.error_packs + self.unjudged

    @property
    def cost_usd(self) -> float:
        return cost_usd(self.tokens)

    @property
    def est_ratio(self) -> float | None:
        """Estimated tokens (what packing budgeted) over actual tokens (what Jev billed)."""
        return self.est_tokens / self.tokens if self.tokens else None

    @property
    def model(self) -> str:
        return self.answered_model or self.requested_model

    @property
    def once_per_row_ok(self) -> bool:
        return (
            not self.dbt_reported_violation
            and self.inserted == self.missing
            and self.pack_rows == self.inserted - self.oversized
            and self.dups == 0
        )


def run_line(run: Run) -> str:
    """The dbt `Jev · N judgments · ...` summary line, rebuilt from the ledger tables."""
    label = "SIMULATED" if run.simulated else "LIVE"
    line = (
        f"Jev · {run.judgments:,} judgments · {run.cached_pct:.0f}% cached · "
        f"{run.packs:,} requests · {run.retries:,} retries ({run.throttled:,}× 429) · "
        f"{run.span_s:.1f} s Jev · ${run.cost_usd:.3f} · {label} {run.model} "
        f"budget={int(run.budget / 1000)}k"
    )
    if run.unjudged > 0:
        line += f" · {run.unjudged:,} unjudged ({run.error_packs:,} failed requests)"
    return line


def dbt_reported_violation(stdout: str) -> bool:
    """Did dbt's own on-run-end check print 'once-per-row VIOLATED'?"""
    return bool(_ONCE_RE.search(re.sub(r"\x1b\[[0-9;]*m", "", stdout)))


GateResults = dict[str, tuple[Metrics, Metrics]]


def _run_reasons(run: Run | None) -> list[str]:
    if run is None:
        return ["summary not captured (run with --run)"]
    reasons = []
    if not run.live:
        reasons.append("run was not LIVE")
    if run.errors:
        reasons.append("run reported errors")
    if not run.once_per_row_ok:
        reasons.append("once-per-row VIOLATED")
    return reasons


def gate(results: GateResults, run: Run | None) -> tuple[bool, list[str]]:
    """Gate: captured, LIVE, error-free, once-per-row, and Jev beats P/R/F1 thresholds on
    every test (demo 04's gate, unchanged)."""
    reasons = _run_reasons(run)
    for name, (jev, baseline) in results.items():
        if jev.precision < PRECISION_MIN:
            reasons.append(f"{name}: Jev precision {jev.precision:.2f} < 0.85")
        if jev.recall < RECALL_MIN:
            reasons.append(f"{name}: Jev recall {jev.recall:.2f} < 0.85")
        if jev.f1 <= baseline.f1:
            reasons.append(
                f"{name}: Jev f1 {jev.f1:.2f} does not beat baseline f1 {baseline.f1:.2f}"
            )
    return (len(reasons) == 0, reasons)


def gate_word(ok: bool, reasons: list[str]) -> str:
    """PASS, PENDING (only evidence still missing: audit labels, rerun check) or FAIL."""
    if ok:
        return "PASS"
    return "PENDING" if reasons and all(r in PENDING_REASONS for r in reasons) else "FAIL"


def refuse_append_if_simulated(run: Run | None) -> None:
    """No simulated number ever goes into docs/eval-results.md."""
    if run is None:
        raise SystemExit("refusing --append: no run provenance found (run with --run)")
    if run.simulated:
        raise SystemExit(
            "refusing --append: this run is SIMULATED (demo mode); "
            "only LIVE runs are recorded in docs/eval-results.md"
        )


def scorecard_title(run: Run | None) -> str:
    if run is None or run.simulated:
        return "SIMULATED backend vs regex baseline"
    return "Jev vs regex baseline"


def simulated_banner(run: Run | None) -> str | None:
    if run is None:
        return (
            "SIMULATED — no run provenance found: numbers are not from a recorded live run"
        )
    if run.simulated:
        return (
            "SIMULATED — demo mode (noul_pack_demo): Jev columns are wiring checks "
            "(hash noise), not model results"
        )
    return None


# ---------------------------------------------------------------------------------------------
# pure: SQL and command builders
# ---------------------------------------------------------------------------------------------


def _lit(value: str) -> str:
    if not _SAFE.match(value):
        raise ValueError(f"not a safe literal: {value!r}")
    return f"'{value}'"


def _in_list(names: list[str]) -> str:
    return ", ".join(_lit(n) for n in names)


def fresh_sql(mode: str, tests: list[str]) -> str:
    """Forget this mode's judgments for the tests, so the next run judges every state again."""
    return (
        f"delete from {LEDGER}.judgments where mode = {_lit(mode)} "
        f"and test_name in ({_in_list(tests)})"
    )


def dbt_args(production: bool) -> list[str]:
    """dbt arguments (scripts/dbtw.py adds --profiles-dir and --target)."""
    if production:
        return ["build", "--vars", "{production: true}",
                "--select", "+tag:production", "tag:production_baseline"]
    # A fresh schema needs stg_orders (relationships tests), so build the whole yardstick.
    return ["build", "--exclude", "tag:production", "tag:production_baseline"]


def flagged_query(table: str, id_col: str, judged_only: bool = False) -> str:
    """Ids of a stored-failure table. Jev tables also hold unjudged rows (jev_p NULL); those are
    not flagged, they are unjudged, so `judged_only` leaves them out."""
    q = f"select {id_col} from {AUDIT_SCHEMA}.{table}"
    return q + " where jev_p is not null" if judged_only else q


def latest_invocation_sql(tests: list[str]) -> str:
    return (
        f"select invocation_id from {LEDGER}.hook_runs "
        f"where test_name in ({_in_list(tests)}) order by recorded_at desc limit 1"
    )


# ---------------------------------------------------------------------------------------------
# pure: demo 04 reference, audit labels, production metrics
# ---------------------------------------------------------------------------------------------


def load_demo04_reference(path: Path = REFERENCE_PATH) -> dict:
    return json.loads(Path(path).read_text())


def read_audit_labels(path: Path) -> dict[int, str] | None:
    """eval/production_audit_labels.csv (id, label: real|ok), or None if it does not exist."""
    path = Path(path)
    if not path.exists():
        return None
    labels: dict[int, str] = {}
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            labels[int(row["id"])] = row["label"].strip()
    bad = {label for label in labels.values() if label not in ("real", "ok")}
    if bad:
        raise ValueError(f"{path}: label must be 'real' or 'ok', got {sorted(bad)}")
    return labels


def labels_from_audit_sample(path: Path) -> tuple[int, int, dict[int, str]] | None:
    """data/production_audit.csv (id, stars, body, label) -> (labelled, total, {id: label})."""
    path = Path(path)
    if not path.exists():
        return None
    labels: dict[int, str] = {}
    total = 0
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            total += 1
            label = (row.get("label") or "").strip()
            if label:
                labels[int(row["id"])] = label
    return len(labels), total, labels


@dataclass(frozen=True)
class AuditLabels:
    labels: dict[int, str] | None
    source: str | None  # "sample" (data/production_audit.csv) | "labels" (committed file)
    pending: str | None  # why the audit is pending, if it is


def resolve_audit_labels(labels_path: Path, sample_path: Path) -> AuditLabels:
    """The labels to score with. The hand-labelled sample wins when it is newer than the
    committed labels file (a relabelled sample must not be shadowed by stale labels)."""
    labels_path, sample_path = Path(labels_path), Path(sample_path)
    have_labels = labels_path.exists()
    sample = labels_from_audit_sample(sample_path)
    newer = sample is not None and (
        not have_labels or sample_path.stat().st_mtime > labels_path.stat().st_mtime)
    if newer:
        labelled, total, found = sample
        if total == 0 or labelled < total:
            return AuditLabels(None, None, f"{labelled} of {total} rows labelled in "
                                           f"{sample_path.name}")
        bad = {v for v in found.values() if v not in ("real", "ok")}
        if bad:
            raise ValueError(f"{sample_path.name}: label must be 'real' or 'ok', got {sorted(bad)}")
        return AuditLabels(found, "sample", None)
    if have_labels:
        return AuditLabels(read_audit_labels(labels_path), "labels", None)
    return AuditLabels(None, None, f"{sample_path.name} not found "
                                   "(run scripts/audit_sample.py, label it)")


def write_audit_labels(labels: dict[int, str], path: Path) -> None:
    """The committed labels file: id and label only (no review text)."""
    with open(path, "w", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["id", "label"])
        for i in sorted(labels):
            w.writerow([i, labels[i]])


def audit_for(flagged: set[int], planted: set[int], audit: dict[int, str]) -> dict[int, str]:
    """The labels that are about rows still flagged-but-unplanted."""
    unplanted = flagged - planted
    return {i: label for i, label in audit.items() if i in unplanted}


@dataclass(frozen=True)
class ProductionMetrics:
    flagged: int
    planted: int
    planted_tp: int
    unplanted_flagged: int
    recall: float
    raw_precision: float
    jev_raw: Metrics  # Jev vs the planted flips only
    baseline: Metrics  # the regex baseline vs the planted flips only, same data
    audit_n: int
    audited_precision: float | None  # None: audit pending
    audit_lo: float | None
    audit_hi: float | None
    audited_f1: float | None


def production_metrics(
    flagged: set[int],
    planted: set[int],
    baseline_flagged: set[int],
    audit: dict[int, str] | None,
) -> ProductionMetrics:
    key = {i: "defect" for i in planted}
    jev = metrics(flagged, key)
    base = metrics(baseline_flagged, key)
    unplanted = len(flagged - planted)
    point = lo = hi = f1 = None
    if audit:
        point, lo, hi = audited_precision(jev.tp, unplanted, audit)
        f1 = 2 * point * jev.recall / (point + jev.recall) if (point + jev.recall) else 0.0
    return ProductionMetrics(
        flagged=len(flagged), planted=len(planted), planted_tp=jev.tp, unplanted_flagged=unplanted,
        recall=jev.recall, raw_precision=jev.precision, jev_raw=jev, baseline=base,
        audit_n=len(audit or {}), audited_precision=point, audit_lo=lo, audit_hi=hi,
        audited_f1=f1,
    )


def production_gate(
    m: ProductionMetrics, run: Run | None, rerun_requests: int | None
) -> tuple[bool, list[str]]:
    """Recall >= 0.85, audited precision >= 0.85, F1 above the lexicon baseline, 0 errors,
    once-per-row OK and a rerun with 0 requests. Without the rerun check (or the audit labels) the
    gate is PENDING, never PASS."""
    reasons = _run_reasons(run)
    if m.recall < RECALL_MIN:
        reasons.append(f"recall on planted flips {m.recall:.2f} < 0.85")
    if m.audited_precision is None:
        reasons.append("audited precision: audit pending")
    elif m.audited_precision < PRECISION_MIN:
        reasons.append(
            f"audited precision {m.audited_precision:.2f} < 0.85 "
            f"(95% CI {m.audit_lo:.2f}–{m.audit_hi:.2f})"
        )
    if m.jev_raw.f1 <= m.baseline.f1:
        reasons.append(
            f"Jev f1 {m.jev_raw.f1:.2f} does not beat baseline f1 {m.baseline.f1:.2f}"
        )
    if rerun_requests is None:
        reasons.append("rerun not checked (use --rerun)")
    elif rerun_requests:
        reasons.append(f"rerun made {rerun_requests} requests (expected 0)")
    return (len(reasons) == 0, reasons)


# ---------------------------------------------------------------------------------------------
# Databricks reads
# ---------------------------------------------------------------------------------------------


def _query(sql, statement: str, what: str):
    res = sql.run(statement)
    if res.state != "SUCCEEDED":
        err = res.error or res.state
        if "TABLE_OR_VIEW_NOT_FOUND" in err:
            print(
                f"Missing {what}. Run first: uv run python scripts/score.py --run "
                "(or scripts/dbtw.py build ...)",
                file=sys.stderr,
            )
            raise SystemExit(2)
        raise SystemExit(f"could not read {what}: {err}")
    return res


def load_flagged(sql, table: str, id_col: str, judged_only: bool = False) -> set[int]:
    res = _query(sql, flagged_query(table, id_col, judged_only), f"{AUDIT_SCHEMA}.{table}")
    return {int(r[0]) for r in res.rows}


def latest_invocation(sql, tests: list[str]) -> str | None:
    res = _query(sql, latest_invocation_sql(tests), f"{LEDGER}.hook_runs")
    return res.rows[0][0] if res.rows else None


def load_budget() -> int:
    vars_ = yaml.safe_load((JAFFLE_DIR / "dbt_project.yml").read_text()).get("vars", {})
    return int(vars_.get("jev_pack_token_budget", 0))


def require_new_invocation(before: str | None, after: str | None) -> str:
    """The run we scored must be one this command started, not an older invocation."""
    if after is None or after == before:
        raise NotCaptured("no new invocation in hook_runs after the dbt build "
                          "(the build judged nothing, or hook_runs was not written)")
    return after


def table_unjudged(sql, tests: list[str]) -> int:
    """Rows with jev_p NULL, counted directly in each stored-failure table."""
    total = 0
    for test in tests:
        res = _query(sql, f"select count_if(jev_p is null) from {AUDIT_SCHEMA}.{test}",
                     f"{AUDIT_SCHEMA}.{test}")
        total += int(res.rows[0][0])
    return total


def unjudged_consistent(ledger_states: int, table_rows: int) -> bool:
    """Ledger unjudged counts states, tables count rows (rows repeat states): both are zero
    together, and rows can't be fewer than the failed states."""
    return (ledger_states == 0) == (table_rows == 0) and table_rows >= ledger_states


def load_run(sql, invocation_id: str, budget: int, tests: list[str]) -> Run:
    """Provenance of one dbt invocation, for exactly the scored `tests`. Raises NotCaptured if
    the invocation's hook_runs do not cover every test or carry no valid mode."""
    inv = _lit(invocation_id)
    names = _in_list(tests)
    h = _query(sql, (
        "select count(distinct test_name), coalesce(sum(tested), 0), coalesce(sum(missing), 0), "
        "coalesce(sum(inserted), 0), coalesce(sum(oversized), 0), max(mode), max(requested_model) "
        f"from {LEDGER}.hook_runs where invocation_id = {inv} and test_name in ({names})"),
        "hook_runs").rows[0]
    if int(h[0]) != len(tests):
        raise NotCaptured(f"invocation {invocation_id} ran {int(h[0])} of {len(tests)} scored "
                          "tests (partial invocation)")
    mode = h[5]
    if mode not in ("live", "demo"):
        raise NotCaptured(f"hook_runs mode is {mode!r}, expected 'live' or 'demo'")
    r = _query(sql, (
        "select count(*), coalesce(sum(pack_tokens), 0), coalesce(sum(pack_est_tokens), 0), "
        "coalesce(sum(pack_rows), 0), coalesce(sum(greatest(attempts - 1, 0)), 0), "
        "coalesce(sum(greatest(size(filter(retry_statuses, s -> s = 429)), 0)), 0), "
        "count_if(error is not null), "
        "coalesce((unix_micros(max(finished_at)) - unix_micros(min(started_at))) / 1e6, 0), "
        f"max(answered_model) from {LEDGER}.requests "
        f"where invocation_id = {inv} and test_name in ({names})"),
        "requests").rows[0]
    j = _query(sql, (
        f"select (select count_if(p is null) from {LEDGER}.judgments "
        f"where invocation_id = {inv} and test_name in ({names})), "
        f"(select count(*) from (select key from {LEDGER}.judgments where p is not null "
        f"and mode = {_lit(mode)} and test_name in ({names}) "
        "group by key having count(*) > 1))"), "judgments").rows[0]
    return Run(
        mode=mode, requested_model=h[6] or "", answered_model=r[8],
        invocation_id=invocation_id, tested=int(h[1]), missing=int(h[2]), inserted=int(h[3]),
        oversized=int(h[4]), unjudged=int(j[0]), packs=int(r[0]), pack_rows=int(r[3]),
        tokens=int(r[1]), est_tokens=int(r[2]), retries=int(r[4]), throttled=int(r[5]),
        error_packs=int(r[6]), span_s=float(r[7]), dups=int(j[1]), budget=budget,
    )


def current_run(sql, tests: list[str], budget: int) -> Run | None:
    """The latest invocation of `tests` as a Run, or None if there is none or it is partial."""
    inv = latest_invocation(sql, tests)
    if inv is None:
        return None
    try:
        return load_run(sql, inv, budget, tests)
    except NotCaptured:
        return None


# ---------------------------------------------------------------------------------------------
# running dbt
# ---------------------------------------------------------------------------------------------


def check_dbt_result(returncode: int, stdout: str, stderr: str) -> str:
    """stdout of a dbt build that exited 0 and whose final line reports ERROR=0; otherwise
    NotCaptured with the output tail."""
    clean = _ANSI.sub("", stdout)
    tail = f"\n--- stdout (tail) ---\n{clean[-4000:]}\n--- stderr (tail) ---\n{stderr[-4000:]}"
    if returncode != 0:
        raise NotCaptured(f"dbt build failed (exit status {returncode}){tail}")
    done = _DONE.findall(clean)
    if not done:
        raise NotCaptured(f"dbt build printed no final 'Done.' line{tail}")
    if int(done[-1]) > 0:
        raise NotCaptured(f"dbt build ended with ERROR={done[-1]}{tail}")
    return stdout


def run_dbt(*, production: bool, mode: str | None) -> str:
    """dbt build via scripts/dbtw.py; returns stdout, or raises NotCaptured (non-zero exit,
    ERROR=n > 0 on dbt's final line, or no final line)."""
    env = {**os.environ, "DBT_SEND_ANONYMOUS_USAGE_STATS": "false"}
    if mode is not None:
        env["JEV_MODE"] = mode
    cmd = [sys.executable, str(ROOT / "scripts" / "dbtw.py"), *dbt_args(production)]
    result = subprocess.run(cmd, cwd=ROOT, env=env, capture_output=True, text=True)
    return check_dbt_result(result.returncode, result.stdout, result.stderr)


def warehouse_name(sql, configured: str) -> str:
    """The warehouse's name for the log: a configured id is resolved, never written."""
    if not re.fullmatch(r"[0-9a-f]{12,}", configured):
        return configured
    for w in sql.client.warehouses.list():
        if w.id == configured:
            return w.name
    raise SystemExit("cannot resolve the configured warehouse id to a warehouse name; "
                     "set JEV_WAREHOUSE to the warehouse name")


def _effective_mode(arg: str | None) -> str:
    mode = (arg or os.environ.get("JEV_MODE") or "live").lower()
    if mode not in ("live", "demo"):
        raise SystemExit(f"JEV_MODE must be live or demo, got {mode!r}")
    return mode


# ---------------------------------------------------------------------------------------------
# printing
# ---------------------------------------------------------------------------------------------


def _hard_neg_flagged_ids(flagged: set[int], golden: dict[int, str]) -> list[int]:
    return sorted(i for i in flagged if golden.get(i) == "hard_negative")


def _defects_missed_ids(flagged: set[int], golden: dict[int, str]) -> list[int]:
    return sorted(i for i, label in golden.items() if label == "defect" and i not in flagged)


def _mode_budget(run: Run | None) -> str:
    if run is None:
        return "run not captured"
    return f"{run.mode}/budget={int(run.budget / 1000)}k"


def _print_gate(console: Console, ok: bool, reasons: list[str]) -> None:
    word = gate_word(ok, reasons)
    colour = {"PASS": "green", "PENDING": "yellow", "FAIL": "red"}[word]
    console.print(f"[bold {colour}]GATE {word}[/bold {colour}]")
    for reason in reasons:
        console.print(f"[{colour}]- {reason}[/{colour}]")


def _reference_lines(ref: dict, key: str) -> tuple[str, dict]:
    r = ref["runs"][key]
    return (
        f"demo 04 {key} ({r['logged_at']}): "
        f"{r['unique_states']:,} unique states · {r['requests']:,} requests · "
        f"{r['wall_s']:.1f} s · ${r['cost_usd']:.3f}",
        r,
    )


def print_report(console: Console, results: GateResults, run: Run | None, ref: dict) -> None:
    from rich.table import Table

    banner = simulated_banner(run)
    if banner is not None:
        console.print(f"[bold yellow]{banner}[/bold yellow]")

    table = Table(title=scorecard_title(run))
    table.add_column("test", no_wrap=True)
    table.add_column("defects", justify="right")
    table.add_column("Jev P", justify="right")
    table.add_column("Jev R", justify="right")
    table.add_column("Jev hard-neg", justify="right")
    table.add_column("regex P", justify="right")
    table.add_column("regex R", justify="right")
    table.add_column("regex hard-neg", justify="right")
    for name, (jev, baseline) in results.items():
        table.add_row(
            name, str(jev.tp + jev.fn), f"[bold]{jev.precision:.2f}[/bold]",
            f"[bold]{jev.recall:.2f}[/bold]", f"[bold]{jev.hard_neg_flagged}[/bold]",
            f"{baseline.precision:.2f}", f"{baseline.recall:.2f}", str(baseline.hard_neg_flagged))
    console.print(table)

    key = ref["compare_to"]
    line04, r04 = _reference_lines(ref, key)
    cmp = Table(title=f"vs demo 04 ({key})")
    cmp.add_column("test", no_wrap=True)
    cmp.add_column("Jev P/R", justify="right")
    cmp.add_column("04 P/R", justify="right")
    cmp.add_column("regex F1", justify="right")
    cmp.add_column("04 F1 (from P/R)", justify="right")
    for name, (jev, baseline) in results.items():
        t = r04["tests"].get(name)
        cmp.add_row(
            name, f"{jev.precision:.2f}/{jev.recall:.2f}",
            f"{t['jev']['precision']:.2f}/{t['jev']['recall']:.2f}" if t else "-",
            f"{baseline.f1:.2f}", f"{t['baseline']['f1_derived']:.2f}" if t else "-")
    console.print(cmp)

    if run is None:
        console.print("summary: not captured (use --run)")
    else:
        console.print(run_line(run))
        console.print(
            f"this run: {run.judgments:,} unique states · {run.packs:,} requests · "
            f"{run.span_s:.1f} s · ${run.cost_usd:.3f}   |   {line04}")
        console.print(
            f"once-per-row {'OK' if run.once_per_row_ok else 'VIOLATED'}: {run.inserted:,} inserted"
            f" = {run.missing:,} missing · packs sum {run.pack_rows:,} (+{run.oversized:,} too"
            f" long) · {run.dups:,} duplicate keys")
    ok, reasons = gate(results, run)
    _print_gate(console, ok, reasons)


def print_production_report(
    console: Console, m: ProductionMetrics, run: Run | None, rerun_requests: int | None
) -> None:
    from rich.table import Table

    banner = simulated_banner(run)
    if banner is not None:
        console.print(f"[bold yellow]{banner}[/bold yellow]")
    table = Table(title="Production: Amazon Fine Food Reviews, planted rating flips"
                  if run and not run.simulated
                  else "SIMULATED production run vs regex baseline")
    table.add_column("measure")
    table.add_column("Jev", justify="right")
    table.add_column("regex baseline", justify="right")
    table.add_row("planted flips", f"{m.planted:,}", f"{m.planted:,}")
    table.add_row("flagged", f"{m.flagged:,}", f"{m.baseline.flagged:,}")
    table.add_row("recall on planted flips", f"[bold]{m.recall:.3f}[/bold]",
                  f"{m.baseline.recall:.3f}")
    table.add_row("raw precision vs flips only", f"{m.raw_precision:.3f}",
                  f"{m.baseline.precision:.3f}")
    table.add_row("F1 vs flips only (same data)", f"{m.jev_raw.f1:.3f}", f"{m.baseline.f1:.3f}")
    if m.audited_precision is None:
        table.add_row("audited precision", "audit pending", "-")
    else:
        table.add_row(
            f"audited precision (n={m.audit_n}, 95% Wilson)",
            f"[bold]{m.audited_precision:.3f}[/bold] ({m.audit_lo:.3f}–{m.audit_hi:.3f})", "-")
        table.add_row("audited F1", f"{m.audited_f1:.3f}", "-")
    console.print(table)
    console.print(f"flagged = {m.planted_tp:,} planted + {m.unplanted_flagged:,} unplanted")
    if run is None:
        console.print("summary: not captured (use --run)")
    else:
        console.print(run_line(run))
        console.print(
            f"once-per-row {'OK' if run.once_per_row_ok else 'VIOLATED'} · {run.errors:,} errors"
            f" · {run.tokens:,} tokens (est/actual {run.est_ratio or 0:.2f})")
    if rerun_requests is None:
        console.print("rerun: not checked (use --rerun)")
    else:
        console.print(f"rerun: {rerun_requests:,} requests (expected 0)")
    ok, reasons = production_gate(m, run, rerun_requests)
    _print_gate(console, ok, reasons)


def _provenance_lines(run: Run, warehouse: str) -> list[str]:
    ratio = f"{run.est_ratio:.2f}" if run.est_ratio is not None else "n/a"
    return [
        run_line(run),
        "",
        f"- warehouse {warehouse} · budget {run.budget:,} tokens · {run.packs:,} requests · "
        f"{run.retries:,} retries ({run.throttled:,}× 429) · {run.tokens:,} tokens · "
        f"Jev cost ${run.cost_usd:.6f} · est/actual tokens {ratio}",
        f"- once-per-row {'OK' if run.once_per_row_ok else 'VIOLATED'}: {run.inserted:,} inserted"
        f" = {run.missing:,} missing · packs sum {run.pack_rows:,} (+{run.oversized:,} too long)"
        f" · {run.dups:,} duplicate keys · {run.errors:,} errors",
        "",
    ]


def _write(path: Path, lines: list[str]) -> None:
    with open(path, "a") as f:
        f.write("\n".join(lines))


def append_report(
    path: Path,
    results: GateResults,
    detail: dict[str, tuple[list[int], list[int]]],
    run: Run | None,
    warehouse: str,
) -> None:
    refuse_append_if_simulated(run)
    assert run is not None
    ts = dt.datetime.now(dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    ok, reasons = gate(results, run)
    lines = [f"\n## {ts} · {_mode_budget(run)}\n", *_provenance_lines(run, warehouse)]
    lines.append(
        "| test | defects | Jev P | Jev R | Jev hard-neg | regex P | regex R | regex hard-neg |")
    lines.append("|---|---|---|---|---|---|---|---|")
    for name, (jev, baseline) in results.items():
        lines.append(
            f"| {name} | {jev.tp + jev.fn} | {jev.precision:.2f} | {jev.recall:.2f} "
            f"| {jev.hard_neg_flagged} | {baseline.precision:.2f} | {baseline.recall:.2f} "
            f"| {baseline.hard_neg_flagged} |")
    lines.append("")
    gate_line = f"**Gate: {gate_word(ok, reasons)}**"
    if not ok:
        gate_line += " — " + "; ".join(reasons)
    lines += [gate_line, ""]
    for name, (hard_neg_ids, missed_ids) in detail.items():
        lines.append(
            f"- `{name}`: hard negatives flagged = {hard_neg_ids}, defects missed = {missed_ids}")
    lines.append("")
    _write(path, lines)


def append_production_report(
    path: Path, m: ProductionMetrics, run: Run | None, warehouse: str,
    rerun_requests: int | None,
) -> None:
    refuse_append_if_simulated(run)
    assert run is not None
    ts = dt.datetime.now(dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    ok, reasons = production_gate(m, run, rerun_requests)
    if m.audited_precision is None:
        audited = "audited precision pending"
    else:
        audited = (f"audited precision {m.audited_precision:.2f} "
                   f"(95% Wilson {m.audit_lo:.2f}–{m.audit_hi:.2f}, n={m.audit_n})")
    lines = [f"\n## {ts} · production {_mode_budget(run)}\n", *_provenance_lines(run, warehouse)]
    lines += [
        f"- Jev: recall {m.recall:.2f} on {m.planted:,} planted flips · raw precision "
        f"{m.raw_precision:.2f} · {audited}",
        f"- regex baseline (same data): recall {m.baseline.recall:.2f} · raw precision "
        f"{m.baseline.precision:.2f} · F1 {m.baseline.f1:.2f} (Jev raw F1 {m.jev_raw.f1:.2f})",
        f"- flagged {m.flagged:,} = {m.planted_tp:,} planted + {m.unplanted_flagged:,} unplanted",
        "- rerun requests " + ("not run" if rerun_requests is None else str(rerun_requests)),
        "",
    ]
    gate_line = f"**Gate: {gate_word(ok, reasons)}**"
    if not ok:
        gate_line += " — " + "; ".join(reasons)
    lines += [gate_line, ""]
    _write(path, lines)


# ---------------------------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------------------------


def _obtain_run(sql, args, tests: list[str], console: Console, *, production: bool):
    """Optionally (--run) run dbt, then read the provenance of the invocation this run made.

    Returns (run, rerun_requests). `run` is None ("not captured", reason on stderr) unless the
    run was started here, left a new invocation, covers every scored test and is in the
    requested mode. A failing --rerun raises NotCaptured."""
    mode = args.mode
    violated = False
    try:
        if args.run:
            before = latest_invocation(sql, tests)
            if args.fresh:
                res = sql.run(fresh_sql(_effective_mode(mode), tests))
                if res.state != "SUCCEEDED":
                    raise SystemExit(f"--fresh failed: {res.error}")
            violated = dbt_reported_violation(run_dbt(production=production, mode=mode))
            inv = require_new_invocation(before, latest_invocation(sql, tests))
        else:
            inv = latest_invocation(sql, tests)
        run = load_run(sql, inv, load_budget(), tests) if inv else None
        if run is not None:
            if args.run and run.mode != _effective_mode(mode):
                raise NotCaptured(
                    f"hook_runs mode is {run.mode!r} but this run was started in "
                    f"{_effective_mode(mode)!r}")
            rows = table_unjudged(sql, tests)
            if not unjudged_consistent(run.unjudged, rows):
                raise NotCaptured(
                    f"unjudged mismatch: the ledger has {run.unjudged} unjudged states, the "
                    f"stored-failure tables {rows} rows with jev_p NULL")
            if violated:
                run = replace(run, dbt_reported_violation=True)
    except NotCaptured as e:
        print(f"run not captured: {e}", file=sys.stderr)
        return None, None
    rerun_requests = None
    if args.run and args.rerun and run is not None:
        run_dbt(production=production, mode=mode)
        inv2 = require_new_invocation(run.invocation_id, latest_invocation(sql, tests))
        rerun_requests = load_run(sql, inv2, load_budget(), tests).packs
    return run, rerun_requests


def main(argv: list[str] | None = None) -> int:
    from jevdbx.databricks import DEFAULT_WAREHOUSE, Sql

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--run", action="store_true", help="run dbt build (scripts/dbtw.py) first")
    parser.add_argument("--fresh", action="store_true",
                        help="with --run: delete this mode's judgments for the tests first")
    parser.add_argument("--mode", choices=["live", "demo"], default=None, help="set JEV_MODE")
    parser.add_argument("--production", action="store_true", help="score the production run")
    parser.add_argument("--rerun", action="store_true",
                        help="with --run: build again and require 0 requests")
    parser.add_argument("--append", action="store_true",
                        help="with --run: append to docs/eval-results.md (LIVE runs only)")
    args = parser.parse_args(argv)
    if (args.fresh or args.rerun or args.append) and not args.run:
        parser.error("--fresh, --rerun and --append need --run "
                     "(a recorded result must come from the run scored here)")

    console = Console()
    sql = Sql()
    warehouse = (warehouse_name(sql, os.environ.get("JEV_WAREHOUSE", DEFAULT_WAREHOUSE))
                 if args.append else None)
    ref = load_demo04_reference()

    try:
        if args.production:
            return _main_production(console, sql, args, warehouse)
        return _main_yardstick(console, sql, args, warehouse, ref)
    except NotCaptured as e:
        print(f"run not captured: {e}", file=sys.stderr)
        return 1


def _main_production(console: Console, sql, args, warehouse: str | None) -> int:
    if not FLIPS_PATH.exists():
        print(f"Missing {FLIPS_PATH.relative_to(ROOT)}: run scripts/fetch_reviews.py first",
              file=sys.stderr)
        return 2
    with open(FLIPS_PATH, newline="") as f:
        planted = {int(r["id"]) for r in csv.DictReader(f)}
    run, rerun_requests = _obtain_run(sql, args, [PROD_TEST], console, production=True)
    flagged = load_flagged(sql, PROD_TEST, PROD_ID, judged_only=True)
    baseline = load_flagged(sql, f"baseline_{PROD_TEST}", PROD_ID)
    try:
        audit_labels = resolve_audit_labels(LABELS_PATH, AUDIT_SAMPLE_PATH)
    except ValueError as e:
        raise SystemExit(str(e)) from None
    if audit_labels.pending:
        console.print(f"[yellow]audit pending: {audit_labels.pending}[/yellow]")
    audit = (audit_for(flagged, planted, audit_labels.labels)
             if audit_labels.labels is not None else None)
    m = production_metrics(flagged, planted, baseline, audit)
    print_production_report(console, m, run, rerun_requests)
    if args.append:
        append_production_report(DOCS_PATH, m, run, warehouse, rerun_requests)
        console.print(f"Appended run to {DOCS_PATH.relative_to(ROOT)}")
        if audit_labels.source == "sample":
            write_audit_labels(audit_labels.labels, LABELS_PATH)
            console.print(f"wrote {LABELS_PATH.relative_to(ROOT)} (id, label only): commit it")
    return 0


def _main_yardstick(console: Console, sql, args, warehouse: str | None, ref: dict) -> int:
    golden = load_golden(GOLDEN_PATH)
    run, _ = _obtain_run(sql, args, list(TESTS), console, production=False)
    results: GateResults = {}
    detail: dict[str, tuple[list[int], list[int]]] = {}
    for test_name, id_col in TESTS.items():
        gold = golden.get(test_name, {})
        jev_flagged = load_flagged(sql, test_name, id_col, judged_only=True)
        baseline_flagged = load_flagged(sql, f"baseline_{test_name}", id_col)
        results[test_name] = (metrics(jev_flagged, gold), metrics(baseline_flagged, gold))
        detail[test_name] = (
            _hard_neg_flagged_ids(jev_flagged, gold), _defects_missed_ids(jev_flagged, gold))
    print_report(console, results, run, ref)
    if args.append:
        append_report(DOCS_PATH, results, detail, run, warehouse)
        console.print(f"Appended run to {DOCS_PATH.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
