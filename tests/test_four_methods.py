"""Numerical references and safety checks for the Python statistical tools."""
import csv
import hashlib
import json
import math
from pathlib import Path

import numpy as np
import pytest
from scipy import stats

from stat_assistant.tools import StatToolError, execute
from stat_assistant.tool_bridge import run_stat_tool


def write_csv(tmp_path, rows, fields=("student_id", "tutoring", "score")):
    path = tmp_path / "input.csv"
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(fields)
        writer.writerows(rows)
    return path


def request(path, method="welch_t_test", **changes):
    result = {"data_path": str(path), "data_version": "test-v1", "excluded_ids": [],
              "id_column": "student_id", "method": method,
              "roles": {"outcome": "score", "group": "tutoring"},
              "group_labels": ["yes", "no"], "valid_ranges": {"score": [0, 100]},
              "valid_levels": {"tutoring": ["yes", "no"]}, "conf_level": .95, "alpha": .05}
    result.update(changes)
    return result


def numeric_request(tmp_path, x, y, method="pearson_correlation", **changes):
    path = write_csv(tmp_path, [(f"P{i}", a, b) for i, (a, b) in enumerate(zip(x, y))], ("id", "x", "y"))
    return request(path, method, roles={"x": "x", "y": "y"}, id_column="id", valid_ranges={}, valid_levels={}, **changes)


@pytest.fixture
def welch_request(tmp_path):
    x, y = [10, 12, 14, 16, 20], [8, 9, 11, 12, 13, 15]
    path = write_csv(tmp_path, [(f"A{i}", "yes", v) for i, v in enumerate(x)] + [(f"B{i}", "no", v) for i, v in enumerate(y)])
    return request(path), np.array(x), np.array(y)


def test_welch_matches_independent_formula_and_reverse(welch_request):
    req, x, y = welch_request
    output = execute("run_test", req)
    a, b = np.var(x, ddof=1)/len(x), np.var(y, ddof=1)/len(y)
    se, difference = math.sqrt(a+b), np.mean(x)-np.mean(y)
    df = (a+b)**2 / (a*a/(len(x)-1)+b*b/(len(y)-1))
    critical = stats.t.ppf(.975, df)
    assert output["status"] == "ok"
    assert output["mean_difference"] == pytest.approx(difference)
    assert output["t_statistic"] == pytest.approx(difference/se)
    assert output["df"] == pytest.approx(df)
    assert output["ci_lower"] == pytest.approx(difference-critical*se)
    assert output["ci_upper"] == pytest.approx(difference+critical*se)
    assert output["p_value"] == pytest.approx(2*stats.t.sf(abs(difference/se), df))
    reverse = execute("run_test", {**req, "group_labels": ["no", "yes"]})
    assert reverse["mean_difference"] == pytest.approx(-output["mean_difference"])
    assert reverse["ci_lower"] == pytest.approx(-output["ci_upper"])
    assert reverse["p_value"] == pytest.approx(output["p_value"])
    interval99 = execute("run_test", {**req, "conf_level": .99})
    assert interval99["ci_lower"] < output["ci_lower"]
    assert interval99["ci_upper"] > output["ci_upper"]
    assert interval99["p_value"] == output["p_value"]


def test_pearson_reference_and_fisher99(tmp_path):
    x, y = np.array([1, 2, 3, 4, 5, 6]), np.array([2, 1, 4, 3, 7, 8])
    req = numeric_request(tmp_path, x, y, method="pearson")
    output = execute("run_test", req)
    xc, yc = x-np.mean(x), y-np.mean(y)
    r = np.dot(xc, yc)/math.sqrt(np.dot(xc, xc)*np.dot(yc, yc))
    assert output["method"] == "pearson_correlation"
    assert output["r"] == pytest.approx(r)
    t = r*math.sqrt(4/(1-r*r))
    assert output["t_statistic"] == pytest.approx(t)
    assert output["p_value"] == pytest.approx(2*stats.t.sf(abs(t), 4))
    output99 = execute("run_test", {**req, "conf_level": .99})
    half = stats.norm.ppf(.995)/math.sqrt(3)
    assert output99["ci_lower"] == pytest.approx(np.tanh(np.arctanh(r)-half))
    assert output99["ci_upper"] == pytest.approx(np.tanh(np.arctanh(r)+half))
    assert output99["ci_lower"] < output["ci_lower"]


@pytest.mark.parametrize("sign", [1, -1])
def test_perfect_pearson_is_explicit_and_strict_json(tmp_path, sign):
    output = execute("run_test", numeric_request(tmp_path, [1, 2, 3, 4, 5], [sign*v+10 for v in [1, 2, 3, 4, 5]]))
    assert output["status"] == "ok"
    assert output["r"] == sign
    assert output["ci_lower"] == output["ci_upper"] == sign
    assert output["p_value"] == 0 and output["t_statistic"] is None
    assert output["perfect_correlation"] and output["t_statistic_note"]
    json.dumps(output, allow_nan=False)


def test_ols_independent_formula_and99(tmp_path):
    x, y = np.array([1, 2, 3, 4, 5, 6]), np.array([2, 4, 5, 4, 5, 8])
    req = numeric_request(tmp_path, x, y, method="linear_regression")
    output = execute("run_test", req)
    design = np.column_stack([np.ones(len(x)), x])
    coefficients = np.linalg.lstsq(design, y, rcond=None)[0]
    residual = y-design@coefficients
    sse = residual@residual
    covariance = sse/4*np.linalg.inv(design.T@design)
    se = math.sqrt(covariance[1, 1])
    assert output["method"] == "simple_linear_regression"
    assert output["slope"] == pytest.approx(coefficients[1])
    assert output["intercept"] == pytest.approx(coefficients[0])
    assert output["slope_se"] == pytest.approx(se)
    assert output["r_squared"] == pytest.approx(1-sse/np.sum((y-np.mean(y))**2))
    assert output["ci_lower"] == pytest.approx(coefficients[1]-stats.t.ppf(.975, 4)*se)
    assert output["p_value"] == pytest.approx(2*stats.t.sf(abs(coefficients[1]/se), 4))
    assert output["regression_diagnostics"] == execute("diagnostics", req)["regression_diagnostics"]
    result99 = execute("run_test", {**req, "conf_level": .99})
    assert result99["ci_upper"] == pytest.approx(coefficients[1]+stats.t.ppf(.995, 4)*se)
    assert result99["ci_upper"] > output["ci_upper"]


@pytest.mark.parametrize("x,y,check", [
    ([1, 2, 3, 4], [2, 4, 6, 8], "zero_residual_variance"),
    ([1, 2, 3, 4], [5, 5, 5, 5], "no_variation"),
    ([1, 1, 1, 1], [2, 4, 3, 8], "no_variation"),
])
def test_degenerate_ols_stops(tmp_path, x, y, check):
    output = execute("run_test", numeric_request(tmp_path, x, y, method="simple_linear_regression"))
    assert output["status"] == "out_of_scope"
    assert check in {f["check"] for f in output["method_findings"]}
    assert "p_value" not in output


def categorical_request(tmp_path, table, method="chi_square"):
    rows = []
    for i, counts in enumerate(table):
        for j, count in enumerate(counts):
            start = len(rows)
            rows.extend([(str(start+k), f"R{i}", f"C{j}") for k in range(count)])
    path = write_csv(tmp_path, rows, ("id", "x", "y"))
    return request(path, method, roles={"x": "x", "y": "y"}, id_column="id", valid_ranges={}, valid_levels={})


def test_chisquare_uncorrected_fixed_reference(tmp_path):
    output = execute("run_test", categorical_request(tmp_path, [[30, 20], [20, 30]]))
    assert output["status"] == "ok"
    assert output["chi_square"] == pytest.approx(4)
    assert output["p_value"] == pytest.approx(0.04550026389635857)
    assert output["cramers_v"] == pytest.approx(.2)
    assert output["yates_correction"] is False
    assert output["expected"]["counts"] == [[25, 25], [25, 25]]


def test_sparse_chisquare_cannot_bypass_method_checks(tmp_path):
    req = categorical_request(tmp_path, [[1, 0], [0, 2]])
    diagnostics = execute("diagnostics", req)
    assert diagnostics["n_blocking"] == 0
    assert diagnostics["method_findings"][0]["check"] == "expected_counts_too_small"
    output = execute("run_test", req)
    assert output["status"] == "out_of_scope" and "p_value" not in output


def test_dirty_data_blocked_preserved_and_exclusions_explicit(tmp_path):
    path = write_csv(tmp_path, [("A", "yes ", "85"), ("B", "yes", "850"),
        ("C", "yes", "NA"), ("D", "yes", "abc"), ("E", "no", "Inf"),
        ("F", "yes", 70), ("G", "yes", 80), ("H", "no", 60), ("I", "no", 75)])
    before, req = path.read_bytes(), request(path)
    summary = execute("summary", req)
    assert {v["label_as_written"] for v in summary["columns"][1]["levels_as_written"]} == {"yes ", "yes", "no"}
    diagnostics = execute("diagnostics", req)
    checks = {f["check"] for f in diagnostics["findings"]}
    assert {"invalid_label", "out_of_range", "missing_value", "non_numeric_value", "non_finite_value"} <= checks
    label = next(f for f in diagnostics["findings"] if f["check"] == "invalid_label")
    assert label["value_as_written"] == "yes " and label["row_number"] == 1
    assert diagnostics["method_checks_run"] is False
    assert execute("run_test", req)["status"] == "blocked"
    assert execute("run_test", {**req, "excluded_ids": ["A", "B", "C", "D", "E"]})["n_included"] == 4
    assert path.read_bytes() == before


def test_duplicate_id_and_missing_id_are_not_silently_fixed(tmp_path):
    path = write_csv(tmp_path, [("DUP", "yes", 50), ("DUP", "yes", 70), ("", "no", 55), ("Z", "no", 65)])
    diagnostics = execute("diagnostics", request(path))
    duplicates = [f for f in diagnostics["findings"] if f["check"] == "duplicate_id"]
    assert len(duplicates) == 2 and {f["row_number"] for f in duplicates} == {1, 2}
    assert next(f for f in diagnostics["findings"] if f["check"] == "missing_id")["record_id"] == "row 3"
    excluded = execute("summary", {**request(path), "excluded_ids": ["DUP"]})
    assert excluded["n_rows_in_analysis_set"] == 2


def test_shapiro_is_descriptive_and_outliers_are_not_dropped(tmp_path):
    x, y = [1]*8 + [2, 3, 4, 90], [2]*8 + [3, 4, 5, 80]
    path = write_csv(tmp_path, [(f"A{i}", "yes", v) for i, v in enumerate(x)] + [(f"B{i}", "no", v) for i, v in enumerate(y)])
    req = request(path)
    diagnostics = execute("diagnostics", req)
    assert diagnostics["n_verify"] > 0
    assert all(d["shapiro_wilk_p"] < .05 for d in diagnostics["distribution_checks"])
    output = execute("run_test", req)
    assert output["method"] == "welch_t_test" and output["n_included"] == 24


def test_extra_group_is_not_dropped(tmp_path):
    path = write_csv(tmp_path, [("A", "yes", 70), ("B", "yes", 80), ("C", "no", 60), ("D", "no", 65), ("E", "maybe", 75)])
    output = execute("run_test", request(path, valid_levels={}))
    assert output["status"] == "out_of_scope"
    assert "wrong_number_of_groups" in {f["check"] for f in output["method_findings"]}


@pytest.mark.parametrize("changes", [{"conf_level": 1}, {"alpha": 0}, {"alpha": True},
    {"roles": {"x": "score"}}, {"method": "unknown"}, {"excluded_ids": "A"},
    {"valid_ranges": {"score": [100, 0]}}, {"group_labels": ["yes", "Yes"]},
    {"roles": {"outcome": "score", "group": ["bad"]}}, {"data_path": float("nan")},
    {"data_version": float("inf")}, {"method": ["pearson"]}])
def test_invalid_request_fails_clearly(welch_request, changes):
    req, _, _ = welch_request
    output = execute("run_test", {**req, **changes})
    assert output["status"] == "unsupported_request" and output["problems"]
    json.dumps(output, allow_nan=False)


def test_missing_column_and_bad_csv(tmp_path):
    path = write_csv(tmp_path, [("A", 1)], ("student_id", "other"))
    assert execute("summary", request(path))["status"] == "missing_required_columns"
    path.write_text("id,x,x\nA,1,2\n", encoding="utf-8")
    with pytest.raises(StatToolError, match="duplicate column"):
        execute("summary", request(path))


def test_no_id_column_keeps_source_row_numbers(tmp_path):
    path = write_csv(tmp_path, [(1, 2), (2, 5), (3, 3), (4, 7), (5, "NA")], ("x", "y"))
    req = request(path, "pearson", roles={"x": "x", "y": "y"}, id_column=None, valid_ranges={}, valid_levels={})
    diagnostics = execute("diagnostics", req)
    issue = next(f for f in diagnostics["findings"] if f["check"] == "missing_value")
    assert issue["record_id"] == "row 5" and issue["row_number"] == 5
    output = execute("run_test", {**req, "excluded_ids": ["row 5"]})
    assert output["status"] == "ok" and output["n"] == 4


def test_pearson_small_sample_and_nonfinite_overflow_stop(tmp_path):
    output = execute("run_test", numeric_request(tmp_path, [1, 2, 3], [2, 4, 3]))
    assert output["status"] == "out_of_scope"
    assert output["method_findings"][0]["check"] == "too_few_observations"
    output = execute("run_test", numeric_request(tmp_path, [1e308, 0, 1e308, 0], [2, 4, 3, 5]))
    assert output["status"] == "out_of_scope"
    assert "numeric_instability" in {f["check"] for f in output["method_findings"]}


def test_bridge_audits_strict_json(welch_request, tmp_path, monkeypatch):
    from stat_assistant import settings
    req, _, _ = welch_request
    monkeypatch.setattr(settings, "OUTPUT_DIR", tmp_path / "audit")
    one, two = run_stat_tool("run_test", req, "test/tag"), run_stat_tool("run_test", req, "test/tag")
    files = list((settings.OUTPUT_DIR / "stat_io").glob("*.json"))
    assert len(files) == 4 and one == two
    for path in files:
        json.loads(path.read_text(encoding="utf-8"), parse_constant=lambda v: pytest.fail(f"Invalid JSON {v}"))


def test_historical_csv_files_are_read_only():
    paths = sorted((Path(__file__).resolve().parents[1] / "data").glob("tutoring_scores_*_synthetic.csv"))
    assert len(paths) == 4
    before = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    for path in paths:
        for task in ("summary", "diagnostics", "run_test"):
            execute(task, request(path))
    assert before == {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
