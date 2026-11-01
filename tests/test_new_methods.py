"""Paired inference and exact 2x2 references, boundaries, and protected reports."""
import copy
import csv
import json
import math

import pytest
from scipy import stats

from stat_assistant import settings
from stat_assistant.methods import METHODS, direction_of, hypotheses, protected_values
from stat_assistant.report import check_report, format_stats_block
from stat_assistant.tool_bridge import run_stat_tool
from stat_assistant.tools import execute


def request(tmp_path, method, rows, **changes):
    path = tmp_path / "input.csv"
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(("id", "before", "after"))
        writer.writerows((f"P{i}", x, y) for i, (x, y) in enumerate(rows))
    result = {"data_path": str(path), "data_version": "new-method-v1", "method": method,
              "roles": {"x": "before", "y": "after"}, "id_column": "id",
              "excluded_ids": [], "conf_level": .95, "alpha": .05}
    result.update(changes)
    return result


def paired_request(tmp_path, before=(10, 12, 13, 15, 18), after=(12, 13, 17, 18, 20), **changes):
    return request(tmp_path, "paired_t_test", zip(before, after), **changes)


def fisher_request(tmp_path, table=((1, 9), (11, 3)), **changes):
    rows = [(x, y) for x, counts in zip(("A", "B"), table)
            for y, count in zip(("No", "Yes"), counts) for _ in range(count)]
    # Reverse the physical row order to ensure ordering is not first-occurrence based.
    return request(tmp_path, "fisher_exact", reversed(rows), **changes)


def test_paired_t_matches_hand_difference_calculation_and_scipy(tmp_path):
    req = paired_request(tmp_path)
    result = execute("run_test", req)
    assert result["status"] == "ok"
    # Hand reference: d=[2,1,4,3,2], mean=2.4, sample variance=1.3, df=4.
    se = math.sqrt(1.3 / 5)
    expected_t = 2.4 / se
    half = stats.t.ppf(.975, 4) * se
    assert result["n"] == result["n_pairs"] == result["n_included"] == 5
    assert result["mean_difference"] == pytest.approx(2.4)
    assert result["sd_difference"] == pytest.approx(math.sqrt(1.3))
    assert result["t_statistic"] == pytest.approx(expected_t)
    assert result["df"] == 4
    assert result["ci_lower"] == pytest.approx(2.4 - half)
    assert result["ci_upper"] == pytest.approx(2.4 + half)
    scipy_reference = stats.ttest_rel([12, 13, 17, 18, 20], [10, 12, 13, 15, 18])
    assert result["p_value"] == pytest.approx(scipy_reference.pvalue)
    assert result["p_value"] == pytest.approx(2 * stats.t.sf(expected_t, 4))
    assert result["alternative"] == "two-sided"


def test_reversing_pair_roles_reverses_estimate_interval_and_t_only(tmp_path):
    req = paired_request(tmp_path)
    first = execute("run_test", req)
    reverse = execute("run_test", {**req, "roles": {"x": "after", "y": "before"}})
    assert reverse["mean_difference"] == pytest.approx(-first["mean_difference"])
    assert reverse["t_statistic"] == pytest.approx(-first["t_statistic"])
    assert reverse["ci_lower"] == pytest.approx(-first["ci_upper"])
    assert reverse["ci_upper"] == pytest.approx(-first["ci_lower"])
    assert reverse["p_value"] == pytest.approx(first["p_value"])


def test_paired_uses_differences_not_constant_marginal_variance(tmp_path):
    req = paired_request(tmp_path, [5, 5, 5, 5], [6, 8, 7, 9])
    assert execute("run_test", req)["status"] == "ok"
    diagnostics = execute("diagnostics", req)
    checks = diagnostics["distribution_checks"]
    assert len(checks) == 1
    assert checks[0]["role"] == "paired_difference"
    assert checks[0]["shapiro_wilk_p"] == pytest.approx(stats.shapiro([1, 3, 2, 4]).pvalue)


@pytest.mark.parametrize("before,after,check", [
    ([1], [2], "too_few_pairs"),
    ([1, 2, 3], [2, 3, 4], "no_difference_variation"),
    ([1, 2, 3], [1, 2, 3], "no_difference_variation"),
    ([0, 0, 0], [1, 1 + 2e-16, 1], "no_difference_variation"),
    ([-1e308, 0], [1e308, 1], "numeric_instability"),
    ([0, 0], [1e200, -1e200], "numeric_instability"),
    ([0, 0, 0], [0, 4.5e-162, 4.5e-162], "numeric_instability"),
])
def test_paired_degenerate_or_unrepresentable_differences_do_not_produce_inference(tmp_path, before, after, check):
    result = execute("run_test", paired_request(tmp_path, before, after))
    assert result["status"] == "out_of_scope"
    assert check in {finding["check"] for finding in result["method_findings"]}
    assert "p_value" not in result
    json.dumps(result, allow_nan=False)


@pytest.mark.parametrize("bad", ["", "NA", "bad-number", "nan", "inf"])
def test_paired_incomplete_or_invalid_pair_blocks_entire_test(tmp_path, bad):
    req = paired_request(tmp_path, [1, 2, 3], [3, bad, 7])
    result = execute("run_test", req)
    assert result["status"] == "blocked"
    assert result["problem_ids"] == ["P1"]
    assert "p_value" not in result
    # Exclusion is possible only when explicitly requested, and removes the whole pair.
    explicit = execute("run_test", {**req, "excluded_ids": ["P1"]})
    assert explicit["status"] == "ok"
    assert explicit["n_pairs"] == 2
    assert explicit["mean_difference"] == pytest.approx(3)


def test_paired_minimum_two_pairs_has_valid_df_and_no_shapiro_claim(tmp_path):
    req = paired_request(tmp_path, [1, 2], [2, 5])
    result = execute("run_test", req)
    assert result["status"] == "ok"
    assert result["df"] == 1
    assert result["t_statistic"] == pytest.approx(2)
    assert result["p_value"] == pytest.approx(.2951672353008664)
    assert execute("diagnostics", req)["distribution_checks"][0]["shapiro_wilk_p"] is None


def test_fisher_known_reference_sorted_orientation_and_no_interval(tmp_path):
    req = fisher_request(tmp_path, valid_levels={"before": ["B", "A"], "after": ["Yes", "No"]})
    result = execute("run_test", req)
    assert result["status"] == "ok"
    assert result["observed"] == {"row_labels": ["A", "B"], "col_labels": ["No", "Yes"], "counts": [[1, 9], [11, 3]]}
    assert result["odds_ratio"] == pytest.approx(1 / 33)
    assert result["odds_ratio_status"] == "finite"
    assert result["p_value"] == pytest.approx(.0027594561852200836)
    assert result["p_value"] == pytest.approx(stats.fisher_exact([[1, 9], [11, 3]], alternative="two-sided").pvalue)
    assert result["alternative"] == "two-sided"
    assert result["n"] == 24
    assert "ci_lower" not in result and "ci_upper" not in result
    assert "a*d/(b*c)" in result["odds_ratio_orientation"]


@pytest.mark.parametrize("table,ratio,status", [
    ([[0, 3], [2, 1]], 0, "finite"),
    ([[2, 0], [1, 3]], None, "infinite"),
    ([[1, 0], [0, 1]], None, "infinite"),
])
def test_fisher_accepts_sparse_zero_cells_with_honest_json_safe_odds_ratio(tmp_path, table, ratio, status):
    req = fisher_request(tmp_path, table)
    result = execute("run_test", req)
    assert result["status"] == "ok"
    assert result["odds_ratio"] == ratio
    assert result["odds_ratio_status"] == status
    assert result["p_value"] == pytest.approx(stats.fisher_exact(table).pvalue)
    json.dumps(result, allow_nan=False)
    assert execute("diagnostics", req)["method_findings"] == []


@pytest.mark.parametrize("rows", [[], [("A", "No"), ("A", "Yes")],
                                  [("A", "No"), ("B", "Yes"), ("C", "No")]])
def test_fisher_requires_exactly_two_observed_levels_each(tmp_path, rows):
    result = execute("run_test", request(tmp_path, "fisher_exact", rows))
    assert result["status"] == "out_of_scope"
    assert "requires_two_by_two" in {finding["check"] for finding in result["method_findings"]}


def test_fisher_missing_label_blocks_and_chi_square_does_not_auto_switch(tmp_path):
    req = fisher_request(tmp_path, [[1, 0], [0, 1]])
    chi = execute("run_test", {**req, "method": "chi_square_independence"})
    assert chi["status"] == "out_of_scope"
    assert "expected_counts_too_small" in {finding["check"] for finding in chi["method_findings"]}
    missing = request(tmp_path, "fisher_exact", [("A", "No"), ("B", "Yes"), ("A", "")])
    assert execute("run_test", missing)["status"] == "blocked"


@pytest.mark.parametrize("method", ["paired_t_test", "fisher_exact"])
def test_new_methods_run_through_existing_recorded_runner(tmp_path, monkeypatch, method):
    monkeypatch.setattr(settings, "OUTPUT_DIR", tmp_path / "audit")
    req = paired_request(tmp_path) if method == "paired_t_test" else fisher_request(tmp_path)
    result = run_stat_tool("run_test", req, "new-method")
    assert result["status"] == "ok"
    audit = list((tmp_path / "audit" / "stat_io").glob("*_result.json"))
    assert len(audit) == 1
    assert json.loads(audit[0].read_text(encoding="utf-8")) == result


def report_fixture(tmp_path, method):
    req = paired_request(tmp_path) if method == "paired_t_test" else fisher_request(tmp_path)
    result = execute("run_test", req)
    spec = METHODS[method]
    block = {"method": method, "method_label": spec.label, "data_version": "v1", "tool_call": result["tool_call"],
             "values": protected_values(method, result, .95), "required_placeholders": list(spec.required),
             "required_limitations": spec.limitation, "direction": direction_of(method, result),
             "decision": result["decision"], "hypotheses": hypotheses(method, req["roles"], []),
             "observed": result.get("observed")}
    if method == "paired_t_test":
        text = ("There were {n} complete pairs. The mean difference is {mean_difference}, "
                "{y_column} minus {x_column}, CI {ci_lower} to {ci_upper}; "
                "t({df}) = {t_statistic}, p = {p_value}. We reject H0.")
    else:
        text = ("There were {n} records. Fisher's two-sided p = {p_value}. The sample odds ratio = {odds_ratio}, "
                "odds of {col_1} versus {col_2} for {row_1} divided by those odds for {row_2}. We reject H0.")
    draft = {"version": "draft1", "interpretation": text, "direction_claim": block["direction"],
             "decision_claim": block["decision"], "limitations": [{"limitation_id": key, "text": value} for key, value in spec.limitation.items()]}
    return block, draft


@pytest.mark.parametrize("method", ["paired_t_test", "fisher_exact"])
def test_new_method_report_contract_renders_and_passes_program_guard(tmp_path, method):
    block, draft = report_fixture(tmp_path, method)
    assert check_report(block, draft)["passed"]
    rendered = format_stats_block(block)
    assert "{" not in rendered
    if method == "paired_t_test":
        assert "after minus before" in rendered
        assert block["direction"] == "positive"
    else:
        assert "sample odds ratio" in rendered
        assert "No odds-ratio confidence interval" in rendered
        assert block["values"]["null_value"] == "1"
        assert block["direction"] == "not_applicable"


def test_report_rejects_swapped_fisher_number_and_invented_interval(tmp_path):
    block, draft = report_fixture(tmp_path, "fisher_exact")
    swapped = copy.deepcopy(draft)
    swapped["interpretation"] = swapped["interpretation"].replace("odds ratio = {odds_ratio}", "odds ratio = {p_value}") + " Stored effect {odds_ratio}."
    assert "field_binding" in {p["check"] for p in check_report(block, swapped)["problems"]}
    draft["interpretation"] += " The odds ratio has a {confidence_level} confidence interval."
    assert "unsupported_interval" in {p["check"] for p in check_report(block, draft)["problems"]}


def test_report_rejects_reversed_paired_difference_orientation(tmp_path):
    block, draft = report_fixture(tmp_path, "paired_t_test")
    draft["interpretation"] = draft["interpretation"].replace("{y_column} minus {x_column}", "{x_column} minus {y_column}")
    assert "difference_orientation" in {p["check"] for p in check_report(block, draft)["problems"]}


def test_fisher_infinite_or_undefined_odds_ratio_protected_text(tmp_path):
    result = execute("run_test", fisher_request(tmp_path, [[2, 0], [1, 3]]))
    assert protected_values("fisher_exact", result, .95)["odds_ratio"] == "infinite"
    # No observed 2x2 table with positive margins can produce 0/0, but the formatter
    # must remain honest if an undefined boundary result is supplied.
    assert protected_values("fisher_exact", {**result, "odds_ratio_status": "undefined"}, .95)["odds_ratio"] == "undefined"
