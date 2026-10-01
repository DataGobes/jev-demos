"""The planned production sample is 50,000 rows (47,500 + 2,500). These are plans, not results."""

import re
from pathlib import Path

ROOT = Path(__file__).parents[1]
SPEC = ROOT / "docs" / "superpowers" / "specs" / "2026-09-30-jev-dbt-databricks-design.md"
CURRENT = [
    "README.md", "CLAUDE.md", "docs/eval-results.md", "scripts/record.sh", "scripts/score.py",
    "scripts/fetch_reviews.py", "notebooks/jev_semantic_tests.py", "src/jevdbx/evallog.py",
]
STALE = re.compile(r"100k|100,000|95,000|~?100 ?000|\b5,000 rows|\+5,000|95_000|100_000")


def test_current_files_state_no_100k_plan():
    hits = []
    for rel in CURRENT:
        for n, line in enumerate((ROOT / rel).read_text().splitlines(), 1):
            if STALE.search(line):
                hits.append(f"{rel}:{n}: {line.strip()}")
    assert hits == []


def test_spec_carries_the_dated_amendment_and_no_unamended_100k():
    text = SPEC.read_text()
    assert ("Amended 2026-10-01: 50,000 rows (47,500 + 2,500), chosen by the user after an "
            "offline dry estimate") in text
    for n, line in enumerate(text.splitlines(), 1):
        if STALE.search(line):
            assert "Amended 2026-10-01" in line or "was ~100k" in line, f"spec:{n}: {line}"


def test_readme_labels_the_offline_estimate_and_the_measured_file_facts():
    text = " ".join((ROOT / "README.md").read_text().split())
    assert "50,000 sampled rows → 46,511 distinct states" in text
    assert "10.8–11.1M input tokens ≈ $0.45–0.47 (±15%)" in text
    assert "0 rows over the per-row token limit" in text
    assert "offline estimate, 2026-10-01" in text and "ESTIMATE" in text
    assert "568,454 reviews" in text and "mean 475 / median 346 chars" in text
    assert ("The SNAP page states no licence and asks for the citation; SNAP's Kaggle upload "
            "lists CC0. The data is downloaded locally and never committed.") in text
    assert "Kaggle lists it as CC0" not in text
