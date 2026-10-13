"""Seventeen real workflow nodes and explicit labelled conditional edges."""
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph

from . import settings
from .models import create_agents, resolve_configuration, resolved_model
from .nodes import AnalysisState, Nodes, current_errors
from .tool_bridge import run_stat_tool


def entry_route(s):
    return "followup" if s.get("request_kind") == "followup" else "new_analysis"


def plan_route(s):
    return "error" if current_errors(s) else s["plan_route"]


def diagnostic_route(s):
    return "error" if current_errors(s) else s["diagnostic_route"]


def correction_route(s):
    return "error" if current_errors(s) else "user_stop" if s.get("user_requested_stop") else "recheck_data"


def review_route(s):
    if current_errors(s):
        return "error"
    if s["program_check"]["passed"] and s["review_verdict"]["passed"]:
        return "review_passed"
    return "revise_once" if s.get("revision_count", 0) < settings.MAX_REPORT_REVISIONS else "fail_after_revision"


def followup_route(s):
    return "error" if current_errors(s) else s["followup_route"]


ROLES = {
    "plan_analysis": "Analysis Agent A planning",
    "prepare_data_summary": "Python descriptive tool",
    "llm_diagnostics": "Analysis Agent A semantic diagnosis",
    "stat_diagnostics": "Python statistical diagnostic tool",
    "merge_diagnostics": "Program evidence merge and Analysis Agent A explanation",
    "request_clarification": "Human input via interrupt",
    "apply_corrections": "Program applies confirmed corrections",
    "run_statistical_test": "Python SciPy statistical tool",
    "build_stats_block": "Program protected statistics",
    "draft_report": "Analysis Agent A drafting",
    "check_report": "Program numeric and content validation",
    "review_report": "Review Agent B evidence review",
    "revise_report": "Analysis Agent A bounded revision",
    "deliver_report": "Program delivers validated report",
    "issue_notice": "Program stops with issues",
    "save_session": "Program session memory",
    "handle_followup": "Analysis Agent A followup routing",
}


def build_graph(agent_a=None, agent_b=None, *, mode="mock", checkpointer=None, tool_runner=run_stat_tool):
    """Compile once; run and visualize this same returned graph. Mock is explicit and offline."""
    if (agent_a is None) != (agent_b is None):
        raise ValueError("Supply both agents, or neither.")
    if agent_a is None:
        configuration = {"mode": "mock"} if mode.lower() == "mock" else resolve_configuration()
        if mode.lower() == "real":
            configuration["mode"] = "real"
        agent_a, agent_b, _ = create_agents(configuration)
    if not agent_a.is_mock or not agent_b.is_mock:
        if agent_a.is_mock != agent_b.is_mock:
            raise ValueError("Do not silently mix a real model and a mock stand-in.")
        if resolved_model(agent_a.model_name) == resolved_model(agent_b.model_name):
            raise ValueError("Model A and Model B must be different underlying models.")
    nodes = Nodes(agent_a, agent_b, tool_runner)
    builder = StateGraph(AnalysisState)
    for name, role in ROLES.items():
        builder.add_node(name, nodes.guarded(name), metadata={"role": role})
    builder.add_conditional_edges(START, entry_route, {"new_analysis": "plan_analysis", "followup": "handle_followup"})
    builder.add_conditional_edges("plan_analysis", plan_route, {"ready": "prepare_data_summary", "revise_plan_once": "plan_analysis", "stop": "issue_notice", "error": "issue_notice"})
    builder.add_edge("prepare_data_summary", "llm_diagnostics")
    builder.add_edge("prepare_data_summary", "stat_diagnostics")
    builder.add_edge(["llm_diagnostics", "stat_diagnostics"], "merge_diagnostics")
    builder.add_conditional_edges("merge_diagnostics", diagnostic_route, {"proceed": "run_statistical_test", "needs_clarification": "request_clarification", "stop": "issue_notice", "error": "issue_notice"})
    builder.add_edge("request_clarification", "apply_corrections")
    builder.add_conditional_edges("apply_corrections", correction_route, {"recheck_data": "prepare_data_summary", "user_stop": "issue_notice", "error": "issue_notice"})
    for source, target in (("run_statistical_test", "build_stats_block"), ("build_stats_block", "draft_report"),
                           ("draft_report", "check_report"), ("check_report", "review_report"), ("revise_report", "check_report")):
        builder.add_edge(source, target)
    builder.add_conditional_edges("review_report", review_route, {"review_passed": "deliver_report", "revise_once": "revise_report", "fail_after_revision": "issue_notice", "error": "issue_notice"})
    builder.add_conditional_edges("handle_followup", followup_route, {"new_confidence_level": "run_statistical_test", "re_explain": "draft_report", "new_question": "plan_analysis", "stop": "issue_notice", "error": "issue_notice"})
    builder.add_edge("deliver_report", "save_session")
    builder.add_edge("issue_notice", "save_session")
    builder.add_edge("save_session", END)
    return builder.compile(checkpointer=checkpointer if checkpointer is not None else InMemorySaver())
