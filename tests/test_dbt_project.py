import json
from pathlib import Path

import pytest
import yaml

from tests.dbt_helpers import JAFFLE, dbt, render

DEMO4_SCHEMA = Path.home() / "Projects/jev-demo-4/jaffle_shop/models/staging/schema.yml"
SENTENCE = "The customer's `comment` describes a different main reason"


def _jev_blocks(schema_path):
    out = {}
    for model in yaml.safe_load(Path(schema_path).read_text())["models"]:
        for col in model.get("columns", []):
            for t in col.get("data_tests", []):
                if isinstance(t, dict) and "jev_expect" in t:
                    out[t["jev_expect"]["name"]] = (model["name"], col["name"], t["jev_expect"])
    return out


@pytest.mark.skipif(not DEMO4_SCHEMA.exists(), reason="demo 04 checkout not present")
def test_jev_expect_blocks_identical_to_demo04():
    ours = _jev_blocks(JAFFLE / "models/staging/schema.yml")
    assert ours == _jev_blocks(DEMO4_SCHEMA) and len(ours) == 4


def test_profiles_never_require_databricks_variables():
    profiles = yaml.safe_load((JAFFLE / "profiles.yml").read_text())["jaffle_shop"]["outputs"]
    assert "auth_type" not in profiles["dev"]
    for target in ("dev", "notebook"):
        assert "DBT_ENV_SECRET_DATABRICKS_TOKEN" in profiles[target]["token"]
    for out in profiles.values():
        for value in out.values():
            if isinstance(value, str) and "env_var(" in value:
                assert "'unset'" in value, value


@pytest.mark.slow
def test_parse_succeeds():
    res = dbt("parse")
    assert res.returncode == 0, res.stdout + res.stderr


@pytest.mark.slow
def test_post_hook_and_vars_configured():
    res = dbt("parse")
    assert res.returncode == 0, res.stdout + res.stderr
    manifest = json.loads((JAFFLE / "target/manifest.json").read_text())
    node = manifest["nodes"]["model.jaffle_shop.stg_reviews"]
    assert any("jev_judge()" in h["sql"] for h in node["config"]["post-hook"])


@pytest.mark.slow
def test_question_rewrites_columns_and_normalizes_criteria():
    q = json.loads(render("jev_render_question", {
        "fails_if": "The `body` contradicts `stars`",
        "criteria": {True: "yes `body`", "false": "no"},
    }))
    assert q == {"instructions": "The `record.body` contradicts `record.stars`",
                 "criteria": {"true": "yes `record.body`", "false": "no"}}


@pytest.mark.slow
def test_key_escapes_quotes_and_includes_mode_and_model():
    key = render("jev_render_key", {"column_name": "comment", "context": ["reason_code"],
                                    "fails_if": SENTENCE + " than `reason_code`."})
    assert key.startswith("sha2(concat_ws(chr(31), 'jev-1.13.0', 'live', 'nested', ")
    assert "customer\\'s" in key  # single quote escaped for Spark SQL
    assert "to_json(named_struct('comment', " in key and "'reason_code', " in key
    demo = render("jev_render_key", {"column_name": "c", "context": [], "fails_if": "x"},
                  env={"JEV_MODE": "demo"})
    assert "'demo', 'nested'" in demo


@pytest.mark.slow
@pytest.mark.parametrize("args,msg", [
    ({"fails_if": ""}, "non-empty sentence"),
    ({"fails_if": "x", "criteria": {"maybe": "?"}}, "keys must be true/false"),
])
def test_question_validation(args, msg):
    res = dbt("run-operation", "jev_render_question", "--args", json.dumps(args))
    assert res.returncode != 0 and msg in res.stdout + res.stderr


@pytest.mark.slow
def test_bad_mode_is_rejected():
    key = dbt("run-operation", "jev_render_key", "--args",
              '{"column_name": "c", "context": [], "fails_if": "x"}', env={"JEV_MODE": "maybe"})
    assert key.returncode != 0 and "must be 'live' or 'demo'" in key.stdout + key.stderr


@pytest.mark.slow
def test_compiled_test_sql_reads_judgments():
    res = dbt("compile", "--select", "reviews_body_matches_stars")
    assert res.returncode == 0, res.stdout + res.stderr
    sql = next((JAFFLE / "target/compiled").rglob("reviews_body_matches_stars.sql")).read_text()
    assert "jev_demo.jev.judgments" in sql and "judged.p >= 0.8" in sql
    assert "except (__jev_key)" in sql and "where judged.p is null or" in sql


PRODUCTION_SCHEMA = JAFFLE / "models/production/schema.yml"


def test_production_jev_expect_arguments_equal_demo04_and_ours():
    block = _jev_blocks(PRODUCTION_SCHEMA)["product_reviews_body_matches_stars"]
    model, column, expect = block
    assert (model, column) == ("stg_product_reviews", "body")
    ours = _jev_blocks(JAFFLE / "models/staging/schema.yml")["reviews_body_matches_stars"][2]
    assert expect["arguments"] == ours["arguments"]
    assert expect["config"] == {"severity": "warn", "store_failures": True, "tags": ["production"]}
    if DEMO4_SCHEMA.exists():
        assert expect["arguments"] == _jev_blocks(DEMO4_SCHEMA)["reviews_body_matches_stars"][2][
            "arguments"]


def test_production_baseline_is_the_reviews_baseline_with_only_ref_and_config_changed():
    base = (JAFFLE / "tests/baseline/baseline_reviews_body_matches_stars.sql").read_text()
    prod = (JAFFLE / "tests/production_baseline"
            / "baseline_product_reviews_body_matches_stars.sql").read_text()
    config = "{{ config(tags=['baseline'], store_failures=true, severity='warn') }}"
    prod_config = ("{{ config(tags=['production_baseline'], store_failures=true, severity='warn', "
                   "enabled=var('production', false)) }}")
    assert config in base and prod_config in prod
    assert prod.replace(prod_config, config).replace("stg_product_reviews", "stg_reviews") == base


def test_production_model_reads_the_volume_and_joins_summary_and_text():
    sql = (JAFFLE / "models/production/stg_product_reviews.sql").read_text()
    assert "/Volumes/jev_demo" not in sql  # the catalog comes from var('jev_catalog')
    assert "var('jev_catalog')" in sql
    assert "concat_ws('\\n', summary, text) as body" in sql
    assert "tags=['production']" in sql


@pytest.mark.slow
@pytest.mark.parametrize("catalog", [None, "other_cat"])
def test_production_model_volume_path_follows_the_catalog_var(catalog):
    vars_ = {"production": True} | ({"jev_catalog": catalog} if catalog else {})
    res = dbt("compile", "--select", "stg_product_reviews", "--vars", json.dumps(vars_))
    assert res.returncode == 0, res.stdout + res.stderr
    sql = next((JAFFLE / "target/compiled").rglob("stg_product_reviews.sql")).read_text()
    expected = f"/Volumes/{catalog or 'jev_demo'}/production/raw/"
    assert f"read_files('{expected}', format => 'parquet')" in sql


@pytest.mark.slow
def test_production_nodes_exist_only_with_the_production_var():
    def listed(*extra):
        res = dbt("ls", "--resource-type", "all", "--output", "name", *extra)
        assert res.returncode == 0, res.stdout + res.stderr
        return {ln.strip() for ln in res.stdout.splitlines()}

    off = listed()
    assert not [n for n in off if "product_reviews" in n]  # model, its tests and the baseline
    on = listed("--vars", "{production: true}")
    assert {"stg_product_reviews", "product_reviews_body_matches_stars",
            "baseline_product_reviews_body_matches_stars"} <= on
    # tests/production_baseline is already under test-paths ("tests"); listing it again would
    # register the baseline twice and make `production: true` fail with a duplicate resource.
    assert dbt("parse", "--vars", "{production: true}").returncode == 0


def test_production_baseline_lives_under_the_test_path():
    project = yaml.safe_load((JAFFLE / "dbt_project.yml").read_text())
    root = (JAFFLE / project["test-paths"][0]).resolve()
    assert (JAFFLE / "tests/production_baseline").resolve().is_relative_to(root)
    assert project["test-paths"] == ["tests"]
