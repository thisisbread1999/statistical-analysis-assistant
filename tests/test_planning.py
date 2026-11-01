"""Meaningful safety and message-protocol tests; no real LLM calls."""
import copy
from pathlib import Path

import pytest
from langchain_core.messages import AIMessage, ToolMessage

from stat_assistant import settings
from stat_assistant.agents import AnalysisAgentA, MockAnalysisAgentA
from stat_assistant.references import retrieve_method_cards
from stat_assistant.runtime import ask_followup, new_run, resume_plan
from stat_assistant.workflow import build_graph
from tests.test_mvp import DATA, DESIGN, QUESTION


@pytest.fixture(autouse=True)
def isolate(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "OUTPUT_DIR", tmp_path / "outputs")


def begin(**options):
    graph = build_graph()
    state = new_run(graph, DATA / "tutoring_scores_clean_synthetic.csv", QUESTION, copy.deepcopy(DESIGN), **options)
    return graph, state


def test_no_computation_before_explicit_approval_and_wrong_digest_cannot_approve():
    graph, state = begin(require_plan_confirmation=True)
    pending = state["__interrupt__"][0].value
    assert pending["kind"] == "plan_approval"
    assert "stat_result" not in state
    assert not any(t["node"] == "run_statistical_test" for t in state["trace"])
    rejected = resume_plan(graph, state["run_id"], {"action": "approve", "plan_id": "wrong"})
    assert rejected.get("__interrupt__") and "stat_result" not in rejected
    delivered = resume_plan(graph, state["run_id"], {"action": "approve", "plan_id": pending["plan_id"]})
    assert delivered["final_status"] == "delivered"
    assert delivered["plan_approval"]["status"] == "approved"


def test_plan_stop_executes_no_statistical_test():
    graph, state = begin(require_plan_confirmation=True)
    stopped = resume_plan(graph, state["run_id"], {"action": "stop"})
    assert stopped["final_status"] == "stopped" and "stat_result" not in stopped


def test_question_change_invalidates_approval_and_requests_a_new_plan():
    graph, state = begin(require_plan_confirmation=True)
    first = state["__interrupt__"][0].value
    revised = resume_plan(graph, state["run_id"], {"action": "change_question", "question": QUESTION + " Please show the mean difference."})
    second = revised["__interrupt__"][0].value
    assert second["kind"] == "plan_approval" and second["plan_id"] != first["plan_id"]
    assert not revised["plan_approval"] and "stat_result" not in revised


def test_approval_is_bound_to_the_original_file(tmp_path):
    data = tmp_path / "input.csv"
    data.write_bytes((DATA / "tutoring_scores_clean_synthetic.csv").read_bytes())
    graph = build_graph()
    state = new_run(graph, data, QUESTION, DESIGN, require_plan_confirmation=True)
    pending = state["__interrupt__"][0].value
    data.write_bytes(data.read_bytes() + b"\n")
    stopped = resume_plan(graph, state["run_id"], {"action": "approve", "plan_id": pending["plan_id"]})
    assert stopped["final_status"] == "stopped" and "stat_result" not in stopped


def test_multi_target_request_requires_selection_then_plan_approval():
    graph = build_graph()
    state = new_run(graph, DATA / "tutoring_scores_clean_synthetic.csv", QUESTION + "; Compare the mean score for tutoring yes versus no.", DESIGN)
    scope = state["__interrupt__"][0].value
    assert scope["kind"] == "scope_selection" and len(scope["tasks"]) == 2
    selected = resume_plan(graph, state["run_id"], {"action": "select", "task_id": scope["tasks"][1]["task_id"]})
    assert selected["__interrupt__"][0].value["kind"] == "plan_approval"
    assert selected["research_question"] == scope["tasks"][1]["question"]
    assert "stat_result" not in selected


def test_filtering_followup_cannot_reuse_unfiltered_statistics():
    graph, state = begin()
    follow = ask_followup(graph, state["run_id"], "Repeat that same analysis only for calendar year 2025.")
    assert follow["final_status"] == "stopped"
    assert not any(t["node"] == "run_statistical_test" and t["request_number"] == 2 for t in follow["trace"])


def test_paired_guidance_is_retrieved_from_real_source_cards():
    cards = retrieve_method_cards("paired mean before after measurements on same subjects")
    assert cards[0]["method"] == "paired_t_test"
    assert all(card["source"].startswith("https://docs.scipy.org/") for card in cards)
    assert "y minus x" in cards[0]["text"]


def test_unmatched_query_does_not_get_arbitrary_method_cards():
    assert retrieve_method_cards("tell me a bedtime story") == []


def test_fresh_subset_question_is_stopped_before_any_computation():
    graph = build_graph()
    state = new_run(graph, DATA / "tutoring_scores_clean_synthetic.csv", QUESTION + " Only for calendar year 2025.", DESIGN)
    assert state["final_status"] == "stopped" and "stat_result" not in state


def test_independent_paired_columns_can_still_answer_a_correlation_question():
    agent = MockAnalysisAgentA()
    design = {"independent_pairs": True, "variables": {"before": {"type": "numeric"}, "after": {"type": "numeric"}}}
    plan = agent.plan("What is the correlation of before and after?", design, ["before", "after"], [])
    assert plan.method == "pearson_correlation"


def test_explicit_paired_contrast_does_not_reverse_when_second_variable_is_mentioned_first():
    agent = MockAnalysisAgentA()
    design = {"independent_pairs": True, "variables": {"drug_1": {"type": "numeric"}, "drug_2": {"type": "numeric"}}}
    plan = agent.plan("Compare mean drug_2 minus drug_1 for the same patients.", design, ["drug_1", "drug_2"], [])
    assert plan.x == "drug_1" and plan.y == "drug_2"


def test_replacement_data_followup_can_be_approved_on_its_new_fingerprint(tmp_path):
    graph, state = begin(require_plan_confirmation=True)
    pending = state["__interrupt__"][0].value
    state = resume_plan(graph, state["run_id"], {"action": "approve", "plan_id": pending["plan_id"]})
    revised = tmp_path / "new.csv"
    text = (DATA / "tutoring_scores_clean_synthetic.csv").read_text(encoding="utf-8")
    lines = text.splitlines()
    revised.write_text("\n".join([lines[0], *reversed(lines[1:])]) + "\n", encoding="utf-8")
    follow = ask_followup(graph, state["run_id"], QUESTION, data_path=revised)
    pending = follow["__interrupt__"][0].value
    assert pending["kind"] == "plan_approval"
    delivered = resume_plan(graph, state["run_id"], {"action": "approve", "plan_id": pending["plan_id"]})
    assert delivered["final_status"] == "delivered" and delivered["data_version"] == "v2"


def test_followup_scope_pause_does_not_present_a_previous_plan_as_current():
    graph, state = begin()
    follow = ask_followup(graph, state["run_id"], QUESTION + "; Compare the mean score for tutoring yes versus no.")
    assert follow["__interrupt__"][0].value["kind"] == "scope_selection"
    assert not follow["analysis_plan"] and not follow["plan_approval"] and not follow["retrieved_references"]


class FakeNativeLLM:
    def __init__(self, calls):
        self.calls, self.messages, self.tools = calls, [], []

    def bind_tools(self, tools):
        self.tools = tools
        return self

    def invoke(self, messages):
        self.messages.append(messages)
        return AIMessage(content="", tool_calls=self.calls)


def test_native_tool_selection_has_matching_id_and_result_message():
    plan = MockAnalysisAgentA().plan(QUESTION, DESIGN, ["student_id", "tutoring", "score"], []).model_dump()
    method = plan.pop("method")
    call = {"name": method, "args": plan, "id": "actual-provider-call-123", "type": "tool_call"}
    llm = FakeNativeLLM([call])
    agent = AnalysisAgentA(llm, "FAKE test double")
    selected = agent.plan(QUESTION, DESIGN, ["student_id", "tutoring", "score"], [])
    assert selected["_tool_selection"]["call"]["id"] == call["id"]
    assert {tool["function"]["name"] for tool in llm.tools} >= {"paired_t_test", "fisher_exact"}
    class StructuredRecorder:
        def invoke(self, messages):
            results = [message for message in messages if isinstance(message, ToolMessage)]
            assert len(results) == 1 and results[0].tool_call_id == call["id"]
            assert '"p_value": 0.02' in results[0].content
            return {"recorded": True}
    llm.with_structured_output = lambda *args, **kwargs: StructuredRecorder()
    assert agent._ask(object, "Draft the result", {"_native_tool_exchange": {
        **selected["_tool_selection"], "result": {"status": "ok", "p_value": .02}}}) == {"recorded": True}


def test_native_tools_require_only_fields_used_by_the_selected_method():
    args = {"x": "drug_1", "y": "drug_2", "target_parameter": "mean y minus x",
            "null_hypothesis": "mean difference is zero", "alternative_hypothesis": "mean difference is not zero",
            "method_rationale": "Matched measurements", "design_notes": ["Independent pairs"]}
    llm = FakeNativeLLM([{"name": "paired_t_test", "args": args, "id": "paired-native", "type": "tool_call"}])
    selected = AnalysisAgentA(llm, "FAKE test double").plan("Compare drug_2 minus drug_1", {}, ["drug_1", "drug_2"], [])
    assert selected["outcome"] == "" and selected["group"] == "" and selected["x"] == "drug_1"
    schema = next(tool["function"]["parameters"] for tool in llm.tools if tool["function"]["name"] == "paired_t_test")
    assert "outcome" not in schema["properties"] and "group_1_label" not in schema["required"]
    assert {"x", "y"} <= set(schema["required"])


@pytest.mark.parametrize("calls", [[], [{"name": "shell", "args": {}, "id": "bad", "type": "tool_call"}],
                                   [{"name": "welch_t_test", "args": {}, "id": "a", "type": "tool_call"},
                                    {"name": "fisher_exact", "args": {}, "id": "b", "type": "tool_call"}]])
def test_native_plan_rejects_missing_unknown_or_multiple_calls(calls):
    agent = AnalysisAgentA(FakeNativeLLM(calls), "FAKE test double")
    with pytest.raises(ValueError):
        agent.plan(QUESTION, DESIGN, ["student_id", "tutoring", "score"], [])


def test_browser_production_default_requires_approval(tmp_path):
    from ui_server import Workspace
    from tests.test_ui_server import CONFIGURATION, finish
    workspace = Workspace(runtime_dir=tmp_path / "ui", configuration=CONFIGURATION)
    try:
        result = finish(workspace, {"action": "analyze", "example": "welch", "mode": "mock", "question": QUESTION})
        assert result["status"] == "needs_plan_approval" and not result["stats"]
        pending = result["clarification"]
        result = finish(workspace, {"action": "resume_plan", "session_id": result["session_id"],
                                   "decision": {"action": "approve", "plan_id": pending["plan_id"]}})
        assert result["status"] == "delivered"
    finally:
        workspace.close()
