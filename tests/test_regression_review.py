"""Regression warning requirements through actual report nodes; no live models.

These report-node tests start with real deterministic tool outputs. They test
the reporting contract directly, rather than simulate human verification or
make decisions about the benchmark fixtures' existing IQR verification flags.
"""
import copy
import csv
from pathlib import Path

import pytest

from stat_assistant.agents import MockAnalysisAgentA, MockReviewAgentB
from stat_assistant.nodes import Nodes
from stat_assistant.tools import execute


BOUNDARY = Path(__file__).resolve().parents[1] / "examples" / "benchmark_v2" / "boundary"


def mock_call(agent, method, *args, **kwargs):
    return getattr(agent, method)(*args, **kwargs)


def report_state(path):
    """Build the real statistics/block/draft/check/delivery pipeline directly."""
    design = {"id_column": None, "independent": True,
              "independence": "Independent observations: TEST fixture metadata.",
              "assignment": "Observational synthetic TEST fixture; not randomized.",
              "typical_outcome": "y",
              "variables": {"x": {"type": "numeric"}, "y": {"type": "numeric"}}}
    question = "Fit simple regression of y on x."
    a, b = MockAnalysisAgentA(), MockReviewAgentB()
    nodes = Nodes(a, b, lambda task, request, tag: execute(task, request))
    plan = a.plan(question, design, ["x", "y"], []).model_dump()
    assert plan["method"] == "simple_linear_regression"
    request = {"data_path": str(path), "data_version": "v1", "id_column": None,
               "roles": {"x": "x", "y": "y"}, "method": plan["method"],
               "excluded_ids": [], "conf_level": .95, "alpha": .05}
    state = {"run_id": "TEST-regression-report", "request_number": 1,
             "research_question": question, "data_path": str(path), "data_version": "v1",
             "analysis_plan": plan, "design_info": design, "conf_level": .95,
             "excluded_ids": [], "correction_log": [],
             "stat_diagnostics": execute("diagnostics", request),
             "stat_result": execute("run_test", request)}
    assert state["stat_diagnostics"]["n_blocking"] == 0
    assert state["stat_result"]["status"] == "ok"
    state.update(nodes.build_stats_block(state, mock_call))
    state.update(nodes.draft_report(state, mock_call))
    state.update(nodes.check_report(state, mock_call))
    assert state["program_check"]["passed"], state["program_check"]["problems"]
    state.update(nodes.deliver_report(state, mock_call))
    return nodes, state


@pytest.mark.parametrize("filename,expected_codes", [
    ("regression_heteroscedastic.csv", {"influential_observations", "heteroscedasticity"}),
    ("regression_influential.csv", {"influential_observations"}),
])
def test_actual_warning_limitations_are_required_in_mock_draft_and_checked(filename, expected_codes):
    path = BOUNDARY / filename
    before = path.read_bytes()
    nodes, state = report_state(path)
    diagnostic = state["stat_result"]["regression_diagnostics"]
    codes = {row["code"] for row in diagnostic["warnings"]}
    assert codes == expected_codes
    block = state["stats_block"]
    assert block["regression_diagnostics"] == diagnostic
    assert expected_codes <= block["required_limitations"].keys()
    # The reporting layer must not manufacture warning limitations for an
    # absent diagnostic warning or hide actual warnings from Model A.
    diagnostic_limitations = {"influential_observations", "high_leverage", "heteroscedasticity"}
    assert block["required_limitations"].keys() & diagnostic_limitations == expected_codes
    written = [row["limitation_id"] for row in state["report_draft"]["limitations"]]
    assert len(written) == len(set(written))
    assert set(written) == set(block["required_limitations"])
    for code in expected_codes:
        omission = copy.deepcopy(state["report_draft"])
        omission["limitations"] = [row for row in omission["limitations"] if row["limitation_id"] != code]
        checked = nodes.check_report({**state, "report_draft": omission}, mock_call)["program_check"]
        assert checked["passed"] is False
        assert any(row["check"] == "required_sections" and code in row["detail"]
                   for row in checked["problems"])
    assert state["final_status"] == "delivered"
    assert state["stat_result"]["n_included"] == diagnostic["n"] == 60
    assert state["stat_result"]["excluded_ids"] == []
    assert path.read_bytes() == before


@pytest.mark.parametrize("filename", ["regression_heteroscedastic.csv", "regression_influential.csv"])
def test_delivered_report_displays_protected_diagnostics_and_warnings(filename):
    _, state = report_state(BOUNDARY / filename)
    diagnostic = state["stat_result"]["regression_diagnostics"]
    report = state["final_report"]
    bp = diagnostic["breusch_pagan"]
    assert "Regression diagnostics (screening flags; no automatic record deletion):" in report
    assert f"Maximum Cook's distance = {diagnostic['max_cooks_distance']:.6g};" in report
    assert f"Maximum leverage = {diagnostic['max_leverage']:.6g};" in report
    assert f"screening threshold = {diagnostic['thresholds']['cooks_distance']:.6g}." in report
    assert f"Koenker studentized Breusch–Pagan test: LM = {bp['lm_statistic']:.6g}; p = {bp['p_value']:.6g}." in report
    assert "Influential record IDs: " + ", ".join(diagnostic["influential_ids"]) in report
    assert "High-leverage record IDs: none flagged" in report
    for warning in diagnostic["warnings"]:
        assert "Diagnostic warning: " + warning["message"] in report
    for code in {row["code"] for row in diagnostic["warnings"]}:
        assert state["stats_block"]["required_limitations"][code] in report
    assert "slope = " + state["stats_block"]["values"]["slope"] in report
    assert "Distribution checks (descriptive only" in report


@pytest.mark.parametrize("rows,unavailable_line", [
    ([(0, 0), (0, 1), (0, -1), (0, 2), (1, 3)], "Maximum Cook's distance = unavailable;"),
    ([(x, 4+3*x+error) for x, error in enumerate([1, -1, -1, 1, 1, -1, -1, 1])],
     "Koenker studentized Breusch–Pagan test: LM = unavailable; p = unavailable."),
])
def test_unavailable_diagnostics_are_rendered_and_require_a_limitation(tmp_path, rows, unavailable_line):
    path = tmp_path / "unavailable_regression.csv"
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["x", "y"])
        writer.writerows(rows)
    nodes, state = report_state(path)
    diagnostic = state["stat_result"]["regression_diagnostics"]
    assert any(row["code"].endswith("_unavailable") for row in diagnostic["warnings"])
    key = "regression_diagnostics_unavailable"
    assert key in state["stats_block"]["required_limitations"]
    assert key in {row["limitation_id"] for row in state["report_draft"]["limitations"]}
    omission = copy.deepcopy(state["report_draft"])
    omission["limitations"] = [row for row in omission["limitations"] if row["limitation_id"] != key]
    checked = nodes.check_report({**state, "report_draft": omission}, mock_call)["program_check"]
    assert checked["passed"] is False
    assert any(row["check"] == "required_sections" and key in row["detail"] for row in checked["problems"])
    report = state["final_report"]
    assert unavailable_line in report
    assert "distance = None" not in report and "LM = None" not in report and "p = None" not in report
    assert "distance = nan" not in report and "LM = nan" not in report
    assert state["stats_block"]["required_limitations"][key] in report
    assert state["stat_result"]["n_included"] == len(rows)
