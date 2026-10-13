"""Independent numerical references for descriptive, row-linked OLS checks."""
import csv
import json

import numpy as np
import pytest
from scipy import stats

from stat_assistant.tools import execute


def regression_request(tmp_path, x, y, *, ids=True, excluded=()):
    path = tmp_path / "regression.csv"
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["id", "x", "y"] if ids else ["x", "y"])
        writer.writerows((f"P{i}", a, b) if ids else (a, b)
                         for i, (a, b) in enumerate(zip(x, y)))
    return {"data_path": str(path), "data_version": "diagnostics-v1",
            "method": "simple_linear_regression", "roles": {"x": "x", "y": "y"},
            "id_column": "id" if ids else None, "excluded_ids": list(excluded)}


def clean_data():
    x = np.arange(20, dtype=float)
    error = np.array([.5, -1, .8, -.5, 1.2, -.8, .6, -1.1, .2, -.4])
    return x, 2 + 3*x + np.r_[error, error[::-1]]


def matrix_reference(x, y):
    """Full design-matrix fit, independent of the tool's centered OLS."""
    design = np.column_stack([np.ones(len(x)), x])
    coefficients = np.linalg.lstsq(design, y, rcond=None)[0]
    fitted = design @ coefficients
    residual = y - fitted
    mse = residual @ residual / (len(x) - design.shape[1])
    hat = design @ np.linalg.inv(design.T @ design) @ design.T
    return design, fitted, residual, mse, hat


def test_clean_diagnostics_match_hat_matrix_and_deleted_prediction_reference(tmp_path):
    x, y = clean_data()
    req = regression_request(tmp_path, x, y)
    before = (tmp_path / "regression.csv").read_bytes()
    output = execute("run_test", req)
    diagnostic_output = execute("diagnostics", req)
    diagnostic = output["regression_diagnostics"]
    assert diagnostic == diagnostic_output["regression_diagnostics"]
    assert diagnostic["n"] == output["n_included"] == 20
    assert diagnostic["parameter_count"] == 2
    assert diagnostic["thresholds"] == {"cooks_distance": .2, "leverage": .2}
    design, fitted, residual, mse, hat = matrix_reference(x, y)
    assert [row["leverage"] for row in diagnostic["observations"]] == pytest.approx(np.diag(hat))
    assert sum(row["leverage"] for row in diagnostic["observations"]) == pytest.approx(2)
    deleted_cooks = []
    for index, row in enumerate(diagnostic["observations"]):
        included = np.arange(len(x)) != index
        deleted_coefficient = np.linalg.lstsq(design[included], y[included], rcond=None)[0]
        perturbation = fitted - design @ deleted_coefficient
        deleted_cooks.append(perturbation @ perturbation / (2*mse))
        assert row["record_id"] == f"P{index}" and row["row_number"] == index + 1
        assert row["cooks_distance"] == pytest.approx(deleted_cooks[-1], rel=1e-10, abs=1e-13)
    assert diagnostic["max_cooks_distance"] == pytest.approx(max(deleted_cooks))
    assert diagnostic["max_leverage"] == pytest.approx(max(np.diag(hat)))
    assert diagnostic["high_leverage_ids"] == diagnostic["influential_ids"] == []
    assert diagnostic["warnings"] == []
    assert {row["check"] for row in diagnostic_output["distribution_checks"]} == {"shapiro_wilk", "spread_check"}
    assert (tmp_path / "regression.csv").read_bytes() == before
    json.dumps(output, allow_nan=False)


def test_influential_observation_warns_but_ordinary_ols_keeps_all_rows(tmp_path):
    x, y = clean_data()
    x, y = np.r_[x, 80], np.r_[y, 2+3*80+40]
    req = regression_request(tmp_path, x, y)
    output = execute("run_test", req)
    diagnostic_output = execute("diagnostics", req)
    diagnostic = output["regression_diagnostics"]
    assert output["status"] == "ok" and output["n_included"] == len(x)
    assert req["excluded_ids"] == output["excluded_ids"] == []
    assert diagnostic_output["n_blocking"] == 0
    assert diagnostic["high_leverage_ids"] == ["P20"]
    assert "P20" in diagnostic["influential_ids"]
    assert {row["code"] for row in diagnostic["warnings"]} == {"influential_observations", "high_leverage"}
    design, fitted, _, mse, hat = matrix_reference(x, y)
    deleted_coefficient = np.linalg.lstsq(design[:-1], y[:-1], rcond=None)[0]
    perturbation = fitted-design @ deleted_coefficient
    assert diagnostic["observations"][-1]["leverage"] == pytest.approx(hat[-1, -1])
    assert diagnostic["observations"][-1]["cooks_distance"] == pytest.approx(perturbation @ perturbation / (2*mse))
    # Only the pre-existing IQR flags ask for human verification.
    assert {row["check"] for row in diagnostic_output["findings"]} == {"boxplot_flag"}
    reference = stats.linregress(x, y)
    assert output["slope"] == pytest.approx(reference.slope)
    assert output["intercept"] == pytest.approx(reference.intercept)
    assert output["slope_se"] == pytest.approx(reference.stderr)
    assert output["p_value"] == pytest.approx(reference.pvalue)
    critical = stats.t.ppf(.975, len(x)-2)
    assert output["ci_lower"] == pytest.approx(reference.slope-critical*reference.stderr)
    assert output["ci_upper"] == pytest.approx(reference.slope+critical*reference.stderr)
    verified_exclusion = execute("run_test", {**req, "excluded_ids": ["P20"], "data_version": "diagnostics-v2"})
    assert verified_exclusion["n_included"] == len(x)-1
    assert "P20" not in {row["record_id"] for row in verified_exclusion["regression_diagnostics"]["observations"]}
    assert verified_exclusion["regression_diagnostics"]["high_leverage_ids"] == []
    assert verified_exclusion["data_version"] == "diagnostics-v2"


def test_koenker_breusch_pagan_matches_auxiliary_least_squares(tmp_path):
    x = np.linspace(.2, 8, 80)
    y = 3 + 2*x + np.where(np.arange(len(x)) % 2, 1., -1.) * x
    req = regression_request(tmp_path, x, y)
    output = execute("run_test", req)
    diagnostic = output["regression_diagnostics"]
    design, _, residual, _, _ = matrix_reference(x, y)
    squared = residual**2
    auxiliary_coefficient = np.linalg.lstsq(design, squared, rcond=None)[0]
    auxiliary_residual = squared - design @ auxiliary_coefficient
    auxiliary_r_squared = 1 - (auxiliary_residual @ auxiliary_residual) / np.sum((squared-squared.mean())**2)
    expected_lm = len(x)*auxiliary_r_squared
    bp = diagnostic["breusch_pagan"]
    assert bp["lm_statistic"] == pytest.approx(expected_lm, rel=1e-12)
    assert bp["p_value"] == pytest.approx(stats.chi2.sf(expected_lm, 1), rel=1e-12)
    assert bp["df"] == 1 and "Koenker" in bp["method"] and "asymptotic" in bp["note"]
    assert bp["p_value"] < .05
    assert "heteroscedasticity" in {row["code"] for row in diagnostic["warnings"]}
    assert output["n_included"] == len(x) and output["excluded_ids"] == []
    assert output["p_value"] == pytest.approx(stats.linregress(x, y).pvalue)
    assert execute("diagnostics", req)["n_blocking"] == 0
    json.dumps(output, allow_nan=False)


@pytest.mark.parametrize("delta", [0., 1e-8])
def test_unit_or_numerically_unit_leverage_has_explicit_null_cook(tmp_path, delta):
    req = regression_request(tmp_path, [0., delta, 0., delta, 1.], [0., 1., -1., 2., 3.])
    output = execute("run_test", req)
    diagnostic = output["regression_diagnostics"]
    assert output["status"] == "ok" and output["n_included"] == 5
    assert diagnostic["observations"][-1]["leverage"] == pytest.approx(1)
    assert diagnostic["observations"][-1]["cooks_distance"] is None
    assert diagnostic["max_cooks_distance"] is None
    assert diagnostic["high_leverage_ids"] == ["P4"]
    warning = next(row for row in diagnostic["warnings"] if row["code"] == "cooks_distance_unavailable")
    assert "P4" in warning["message"] and "unknown" in warning["message"]
    assert "P4" not in diagnostic["influential_ids"]
    json.dumps(output, allow_nan=False)


def test_constant_squared_residuals_do_not_claim_a_variance_test_result(tmp_path):
    x = np.arange(8, dtype=float)
    y = 4+3*x+np.array([1, -1, -1, 1, 1, -1, -1, 1])
    req = regression_request(tmp_path, x, y)
    output = execute("run_test", req)
    diagnostic = output["regression_diagnostics"]
    assert diagnostic["breusch_pagan"]["lm_statistic"] is None
    assert diagnostic["breusch_pagan"]["p_value"] is None
    assert {row["code"] for row in diagnostic["warnings"]} == {"breusch_pagan_unavailable"}
    assert output["status"] == "ok" and output["n_included"] == 8
    assert execute("diagnostics", req)["n_blocking"] == 0
    json.dumps(output, allow_nan=False)


@pytest.mark.parametrize("scale", [1e-150, 1e150])
def test_diagnostics_remain_finite_under_extreme_outcome_units(tmp_path, scale):
    x, y = clean_data()
    original = execute("run_test", regression_request(tmp_path, x, y))["regression_diagnostics"]
    scaled = execute("run_test", regression_request(tmp_path, x, y*scale))
    diagnostic = scaled["regression_diagnostics"]
    assert scaled["status"] == "ok"
    assert diagnostic["breusch_pagan"]["lm_statistic"] == pytest.approx(original["breusch_pagan"]["lm_statistic"], abs=1e-24)
    assert diagnostic["breusch_pagan"]["p_value"] == pytest.approx(original["breusch_pagan"]["p_value"])
    assert [row["cooks_distance"] for row in diagnostic["observations"]] == pytest.approx(
        [row["cooks_distance"] for row in original["observations"]], rel=1e-10)
    json.dumps(scaled, allow_nan=False)


def test_no_id_source_rows_and_explicit_exclusions_keep_original_numbers(tmp_path):
    x, y = clean_data()
    req = regression_request(tmp_path, x, y, ids=False, excluded=["row 2", "row 6"])
    diagnostic = execute("run_test", req)["regression_diagnostics"]
    original_rows = [i for i in range(1, 21) if i not in {2, 6}]
    assert diagnostic["n"] == 18
    assert [row["row_number"] for row in diagnostic["observations"]] == original_rows
    assert [row["record_id"] for row in diagnostic["observations"]] == [f"row {i}" for i in original_rows]


@pytest.mark.parametrize("x,y", [([0, 0, 0, 0], [1, 2, 1, 3]), ([1, 2, 3, 4], [2, 4, 6, 8])])
def test_unaccepted_fit_defers_regression_diagnostics(tmp_path, x, y):
    req = regression_request(tmp_path, x, y)
    diagnostic = execute("diagnostics", req)
    assert diagnostic["regression_diagnostics"] is None
    assert diagnostic["distribution_checks_run"] is False
    assert execute("run_test", req)["status"] == "out_of_scope"
