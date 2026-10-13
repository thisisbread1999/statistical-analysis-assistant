"""Real graph execution with clearly labelled deterministic agent stand-ins."""
import copy
import csv
from pathlib import Path

import pytest

from stat_assistant import settings
from stat_assistant.agents import MockAnalysisAgentA, MockReviewAgentB
from stat_assistant.workflow import ROLES, build_graph
from stat_assistant.nodes import _design_problems
from stat_assistant.runtime import ask_followup, collect_answers, config_for, new_run, resume_answers
from stat_assistant.schemas import ReviewIssue, ReviewVerdict


DESIGN = {"id_column": "student_id", "independence": "Independent observations, explicitly stated by the user.",
          "assignment": "Voluntary participation, not randomized.",
          "variables": {"score": {"type": "numeric", "range": [0, 100]},
                        "tutoring": {"type": "categorical", "levels": ["yes", "no"]}}}
QUESTION = "Is the mean score different between tutoring groups?"
DATA = Path(__file__).resolve().parents[1] / "examples"


@pytest.fixture(autouse=True)
def isolated_output(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "OUTPUT_DIR", tmp_path / "outputs")


def run(graph=None, name="clean", **kwargs):
    graph = graph or build_graph()
    return graph, new_run(graph, DATA / f"tutoring_scores_{name}_synthetic.csv", QUESTION,
                         copy.deepcopy(DESIGN), **kwargs)


def test_actual_graph_has_seventeen_nodes_and_labelled_routes():
    graph = build_graph()
    assert len(ROLES) == 17
    mermaid = graph.get_graph().draw_mermaid()
    for label in ("revise_plan_once", "needs_clarification", "review_passed", "new_confidence_level"):
        assert label in mermaid
    for name, role in ROLES.items():
        assert graph.get_graph().nodes[name].metadata["role"] == role


def test_clean_execution_parallel_join_and_protected_numbers():
    _, s = run()
    assert s["final_status"] == "delivered", s.get("errors")
    assert not s["errors"]
    assert s["stat_result"]["var_equal"] is False
    assert s["program_check"]["passed"]
    assert "MOCK" in s["final_report"]
    assert "Python" in s["final_report"]
    branch = [t for t in s["trace"] if t["node"] in ("llm_diagnostics", "stat_diagnostics")]
    assert len(branch) == 2 and branch[0]["step"] == branch[1]["step"]
    assert branch[0]["data_version"] == branch[1]["data_version"]
    assert all(c["request_number"] == 1 and c["mode"] == "MOCK" for c in s["model_calls"])


@pytest.mark.parametrize("name", ["no_difference", "unequal_variance"])
def test_other_v1_data_remain_supported(name):
    _, s = run(name=name)
    assert s["final_status"] == "delivered"
    if name == "no_difference":
        assert s["stats_block"]["decision"] == "do_not_reject_H0"


def test_design_independent_is_not_substring_dependent():
    assert not _design_problems({"independence": "independent observations"})
    for text in ("dependent observations", "not independent", "clustered observations", "uncertain if independent", ""):
        assert _design_problems({"independence": text})


def test_unknown_independence_stops_before_model_call():
    s = new_run(build_graph(), DATA / "tutoring_scores_clean_synthetic.csv", QUESTION,
                {**DESIGN, "independence": "unknown"})
    assert s["final_status"] == "stopped"
    assert not s["model_calls"]
    assert "Independence" in s["final_report"]


def test_messy_data_interrupt_invalid_input_reinterrupt_and_user_stop():
    graph, s = run(name="messy")
    assert s["__interrupt__"]
    assert not s.get("stat_result")
    rid = s["clarification_requests"][0]["request_id"]
    invalid = [{"request_id": rid, "action": "correct", "new_value": "999", "reason": "TEST answer"}]
    s = resume_answers(graph, s["run_id"], invalid)
    assert s["__interrupt__"][0].value["previous_rejections"]
    assert s["clarification_rounds"] == 0
    s = resume_answers(graph, s["run_id"], [{"request_id": rid, "action": "stop", "reason": ""}])
    assert s["final_status"] == "stopped"
    assert s["user_requested_stop"]
    assert not s["correction_log"]


def test_explicit_test_answers_create_new_version_and_preserve_source(tmp_path):
    graph, s = run(name="messy")
    before = Path(s["original_data_path"]).read_bytes()
    answers = []
    for r in s["clarification_requests"]:
        answer = {"request_id": r["request_id"], "reason": "TEST FIXTURE: verified synthetic source"}
        if r["check"] == "missing_value":
            answer["action"] = "exclude"
        elif r["check"] == "out_of_range":
            answer.update(action="correct", new_value="85")
        elif r["check"] == "invalid_label":
            answer.update(action="correct", new_value="yes")
        else:
            answer["action"] = "verify"
        answers.append(answer)
    s = resume_answers(graph, s["run_id"], answers)
    # Valid corrections may reveal additional plausible outliers; these also need a fixture answer.
    if s.get("__interrupt__"):
        answers = [{"request_id": r["request_id"], "action": "verify", "reason": "TEST FIXTURE: genuine value"}
                   for r in s["clarification_requests"]]
        s = resume_answers(graph, s["run_id"], answers)
    assert s["final_status"] == "delivered", s.get("errors")
    assert s["data_version"] != "v1"
    assert s["stat_result"]["n_included"] == 78
    assert Path(s["original_data_path"]).read_bytes() == before
    assert "missing_data" in s["stats_block"]["required_limitations"]
    assert all(e["reason"] and e["source"] == "explicit user answer" for e in s["correction_log"])
    # Renaming/copying the same corrected dataset does not erase its correction provenance.
    copied = tmp_path / "renamed_corrected.csv"
    copied.write_bytes(Path(s["data_path"]).read_bytes())
    alias = ask_followup(graph, s["run_id"], QUESTION, data_path=copied)
    assert alias.get("__interrupt__")
    assert alias["correction_log"] == s["correction_log"]
    resume_answers(graph, s["run_id"], [{"request_id": alias["clarification_requests"][0]["request_id"], "action": "stop", "reason": ""}])
    # Changing metadata must trigger fresh checks without erasing actual correction provenance.
    metadata = {**DESIGN, "assignment": "Voluntary participation, confirmed observational study."}
    audit = ask_followup(graph, s["run_id"], "Please explain more simply", design_info=metadata)
    assert audit.get("__interrupt__")
    assert audit["correction_log"] == s["correction_log"]
    audit = resume_answers(graph, s["run_id"], [{"request_id": audit["clarification_requests"][0]["request_id"], "action": "stop", "reason": ""}])
    # A different question must reconsider old exclusions and verification, while retaining corrected cells.
    new = ask_followup(graph, s["run_id"], QUESTION)
    assert new["excluded_ids"] == [] and new["verified_ids"] == []
    assert new.get("__interrupt__")
    with open(new["data_path"], newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert next(row for row in rows if row["student_id"] == "S006")["score"] == "85"


def test_external_change_to_previous_file_does_not_reuse_stale_result(tmp_path):
    data = tmp_path / "original.csv"
    data.write_bytes((DATA / "tutoring_scores_clean_synthetic.csv").read_bytes())
    graph = build_graph()
    old = new_run(graph, data, QUESTION, DESIGN)
    data.write_text(data.read_text(encoding="utf-8").replace("74.9", "74.8"), encoding="utf-8")
    new = ask_followup(graph, old["run_id"], "Please explain simply")
    assert new["final_status"] == "stopped"
    assert "edited externally" in new["final_report"]
    assert not any(t["node"] == "draft_report" and t["request_number"] == 2 for t in new["trace"])


def test_data_change_during_statistical_test_stops_before_drafting(tmp_path):
    from stat_assistant.tool_bridge import run_stat_tool

    data = tmp_path / "changing_during_test.csv"
    data.write_bytes((DATA / "tutoring_scores_clean_synthetic.csv").read_bytes())

    def tool_that_simulates_external_edit(task, request, tag):
        result = run_stat_tool(task, request, tag)
        if task == "run_test":
            data.write_text(data.read_text(encoding="utf-8").replace("74.9", "74.8"), encoding="utf-8")
        return result

    state = new_run(build_graph(tool_runner=tool_that_simulates_external_edit), data, QUESTION, DESIGN)
    assert state["final_status"] == "stopped"
    assert state["errors"][-1]["node"] == "run_statistical_test"
    assert "while the statistical test was running" in state["final_report"]
    assert not state.get("stat_result")
    assert not any(c["node"] == "draft_report" for c in state["model_calls"])


def test_replacement_dataset_origin_is_saved_and_restored_for_followup(tmp_path):
    graph, previous = run()
    replacement = tmp_path / "new_dataset.csv"
    replacement.write_text(Path(previous["data_path"]).read_text(encoding="utf-8").replace("74.9", "74.8"), encoding="utf-8")
    state = ask_followup(graph, previous["run_id"], "Report a 99% confidence interval", data_path=replacement)
    assert state["final_status"] == "delivered", state.get("errors")
    assert state["original_data_path"] == str(replacement)
    assert state["session_memory"]["last_success"]["original_data_path"] == str(replacement)
    assert not state["correction_log"]
    # Simulate transient request state carrying the old path; the successful analysis restores its source.
    graph.update_state(config_for(state["run_id"]), {"original_data_path": previous["original_data_path"]})
    followup = ask_followup(graph, state["run_id"], "Explain this simply")
    assert followup["final_status"] == "delivered"
    assert followup["original_data_path"] == str(replacement)


@pytest.mark.parametrize("kind", ["causal_claim", "wrong_number"])
def test_fault_is_revised_once_and_explicitly_labelled(kind):
    _, s = run(test_fault={"kind": kind})
    assert s["final_status"] == "delivered"
    assert s["revision_count"] == 1
    assert "TEST INPUT" in s["final_report"]
    assert s["program_check"]["passed"]
    assert "caused an improvement" not in s["rendered_draft"]["interpretation"]


class PersistentFailureB(MockReviewAgentB):
    def review(self, evidence):
        return ReviewVerdict(passed=False, issues=[ReviewIssue(severity="critical", category="unsupported_claim",
            offending_sentence="TEST FIXTURE", evidence="TEST FIXTURE: repeated critical review failure",
            suggested_correction="TEST FIXTURE: repair the issue")], summary="TEST FIXTURE")


def test_second_review_failure_stops_bounded_loop():
    _, s = run(build_graph(MockAnalysisAgentA(), PersistentFailureB()))
    assert s["final_status"] == "stopped"
    assert s["revision_count"] == 1
    assert sum(t["node"] == "review_report" for t in s["trace"]) == 2
    assert not s["session_memory"].get("last_success")


def test_minor_review_notes_do_not_force_revision():
    class MinorB(MockReviewAgentB):
        def review(self, evidence):
            return ReviewVerdict(passed=False, issues=[ReviewIssue(severity="minor", category="other",
                offending_sentence="TEST", evidence="Optional wording", suggested_correction="Optional")], summary="TEST")
    _, s = run(build_graph(MockAnalysisAgentA(), MinorB()))
    assert s["final_status"] == "delivered" and s["revision_count"] == 0


def test_reviewer_false_without_issues_stops_instead_of_becoming_passed():
    class UnableToReviewB(MockReviewAgentB):
        def review(self, evidence):
            return ReviewVerdict(passed=False, issues=[], summary="TEST FIXTURE: unable to evaluate the report.")
    _, s = run(build_graph(MockAnalysisAgentA(), UnableToReviewB()))
    assert s["final_status"] == "stopped"
    assert s["errors"][-1]["node"] == "review_report"
    assert "inconsistent verdict" in s["final_report"]
    assert not s["session_memory"].get("last_success")
    assert not any(t["node"] == "deliver_report" for t in s["trace"])


def test_model_error_guard_in_parallel_and_followup_new_request_recovers():
    graph, good = run()
    failed = ask_followup(graph, good["run_id"], "Please explain more simply", test_fault={"kind": "model_failure", "node": "draft_report"})
    assert failed["final_status"] == "stopped"
    assert failed["errors"][-1]["request_number"] == 2
    recovered = ask_followup(graph, good["run_id"], "Please explain more simply")
    assert recovered["final_status"] == "delivered"
    assert recovered["request_number"] == 3
    assert recovered["errors"][-1]["request_number"] == 2
    _, parallel_failure = run(test_fault={"kind": "model_failure", "node": "llm_diagnostics"})
    assert parallel_failure["final_status"] == "stopped"
    assert any(t["node"] == "stat_diagnostics" and t["status"] == "completed" for t in parallel_failure["trace"])


def test_failed_first_analysis_cannot_be_reexplained_as_success():
    graph, s = run(test_fault={"kind": "model_failure", "node": "draft_report"})
    s = ask_followup(graph, s["run_id"], "Please explain simply")
    assert s["final_status"] == "stopped"
    assert "earlier successful" in s["final_report"]


def test_model_call_cap_is_per_request_and_counts_calls():
    graph, good = run()
    limited = ask_followup(graph, good["run_id"], "Explain simply", max_model_calls=1)
    assert limited["final_status"] == "stopped"
    assert sum(c["request_number"] == 2 for c in limited["model_calls"]) == 1
    assert "model-call limit" in limited["final_report"]
    recovered = ask_followup(graph, good["run_id"], "Explain simply", max_model_calls=3)
    assert recovered["final_status"] == "delivered"
    assert sum(c["request_number"] == 3 for c in recovered["model_calls"]) == 3


def test_followup_ci_recomputes_interval_and_reexplain_reuses_result():
    graph, old = run()
    new = ask_followup(graph, old["run_id"], "Report a 99% confidence interval")
    assert new["final_status"] == "delivered", new.get("errors")
    assert new["conf_level"] == .99
    assert new["stat_result"]["ci_upper"] > old["stat_result"]["ci_upper"]
    assert new["stat_result"]["p_value"] == old["stat_result"]["p_value"]
    nodes = [t["node"] for t in new["trace"] if t["request_number"] == 2]
    assert "run_statistical_test" in nodes and "stat_diagnostics" not in nodes
    explained = ask_followup(graph, old["run_id"], "Explain this simply")
    assert explained["final_status"] == "delivered"
    assert explained["stat_result"] == new["stat_result"]
    assert not any(t["node"] == "run_statistical_test" and t["request_number"] == 3 for t in explained["trace"])


def test_changed_data_rechecks_before_same_analysis_followup(tmp_path):
    graph, old = run()
    changed = tmp_path / "changed.csv"
    changed.write_text(Path(old["data_path"]).read_text(encoding="utf-8").replace("74.9", "999"), encoding="utf-8")
    new = ask_followup(graph, old["run_id"], "Report a 99% confidence interval", data_path=changed)
    assert new["__interrupt__"]
    assert not any(t["node"] == "run_statistical_test" and t["request_number"] == 2 for t in new["trace"])


def test_plan_revision_once_then_stop():
    class BadPlanA(MockAnalysisAgentA):
        def plan(self, *args):
            result = super().plan(*args)
            result.outcome = "not_a_column"
            return result
    _, s = run(build_graph(BadPlanA(), MockReviewAgentB()))
    assert s["final_status"] == "stopped"
    assert s["plan_revision_count"] == 1
    assert sum(t["node"] == "plan_analysis" for t in s["trace"]) == 2


def test_malformed_model_schema_routes_to_issue_notice():
    class InvalidSchemaA(MockAnalysisAgentA):
        def plan(self, *args):
            return {"method": "welch_t_test"}
    _, s = run(build_graph(InvalidSchemaA(), MockReviewAgentB()))
    assert s["final_status"] == "stopped"
    assert s["errors"][0]["type"] == "ValidationError"


def test_collect_answers_reprompts_without_inventing_confirmation():
    graph, s = run(name="messy")
    item = next(r for r in s["clarification_requests"] if r["check"] == "out_of_range")
    typed = iter(["correct", "999", "TEST source", "correct", "85", "TEST checked source"])
    answers = collect_answers([item], input_fn=lambda _: next(typed))
    assert answers == [{"request_id": item["request_id"], "action": "correct", "new_value": "85", "reason": "TEST checked source"}]
    assert graph.get_state(config_for(s["run_id"])).values["clarification_rounds"] == 0


def test_same_real_model_and_mixed_mock_real_are_rejected():
    a, b = MockAnalysisAgentA(), MockReviewAgentB()
    a.is_mock = b.is_mock = False
    a.model_name = b.model_name = "ollama:identical"
    with pytest.raises(ValueError, match="different underlying"):
        build_graph(a, b)
    b.is_mock = True
    with pytest.raises(ValueError, match="mix"):
        build_graph(a, b)


@pytest.mark.parametrize("method,question", [
    ("welch_t_test", "Is mean score different between tutoring groups?"),
    ("pearson_correlation", "What is the correlation of study hours and score?"),
    ("chi_square_independence", "Are tutoring and passed associated?"),
    ("simple_linear_regression", "Regress score on study hours."),
])
def test_four_methods_execute_through_the_actual_graph(tmp_path, method, question):
    data = tmp_path / "four_methods.csv"
    with data.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["student_id", "tutoring", "study_hours", "score", "passed"])
        for i in range(100):
            x = i % 10 + 1
            writer.writerow([f"T{i}", "yes" if i % 2 else "no", x,
                             45 + 2 * x + [-4, -2, 0, 2, 4][(i // 10) % 5],
                             "yes" if i % 4 < 2 else "no"])
    design = copy.deepcopy(DESIGN)
    design["typical_outcome"] = "score"
    design["variables"].update(study_hours={"type": "numeric"}, passed={"type": "categorical", "levels": ["yes", "no"]})
    graph = build_graph()
    state = new_run(graph, data, question, design)
    assert state["final_status"] == "delivered", state.get("errors")
    assert state["stat_result"]["method"] == method
    if method == "chi_square_independence":
        assert state["stat_result"]["yates_correction"] is False
        follow = ask_followup(graph, state["run_id"], "Report a 99% confidence interval")
        assert follow["final_status"] == "stopped" and "not implemented" in follow["final_report"]


def test_subset_followup_is_explicitly_unsupported():
    graph, old = run()
    result = ask_followup(graph, old["run_id"], "What if I only looked at the last year?")
    assert result["final_status"] == "stopped"
    assert "Filtering is not supported" in result["final_report"]
