"""Notebook helpers. No user decisions are filled in automatically."""
import copy
import uuid
from pathlib import Path

from langgraph.types import Command

from . import settings
from .nodes import fingerprint, validate_answer


def config_for(thread_id):
    return {"configurable": {"thread_id": thread_id}, **settings.RUN_CONFIG}


def _fresh_request(request_number, test_fault, max_model_calls):
    if isinstance(max_model_calls, bool) or not isinstance(max_model_calls, int) or max_model_calls < 1:
        raise ValueError("max_model_calls must be a positive integer.")
    if test_fault:
        if test_fault.get("kind") not in ("causal_claim", "wrong_number", "model_failure"):
            raise ValueError("Unknown TEST INPUT fault.")
        if test_fault["kind"] == "model_failure" and not test_fault.get("node"):
            raise ValueError("A model_failure TEST INPUT must name a node.")
    return {"request_number": request_number, "test_fault": test_fault, "max_model_calls": max_model_calls,
            "revision_count": 0, "plan_revision_count": 0, "plan_feedback": [], "clarification_rounds": 0,
            "clarification_requests": [], "clarification_answers": [], "rejected_answers": [],
            "user_requested_stop": False, "stop_reasons": [], "final_status": "running", "final_report": "",
            "followup_focus": "", "followup_data_changed": False, "followup_design_changed": False,
            "followup_dataset_replaced": False, "program_check": {}, "review_verdict": {},
            "report_draft": {}, "rendered_draft": {}}


def new_run(graph, data_path, question, design_info, *, thread_id=None, test_fault=None,
            max_model_calls=settings.MAX_MODEL_CALLS_PER_REQUEST):
    thread_id = thread_id or uuid.uuid4().hex
    if graph.get_state(config_for(thread_id)).values:
        raise ValueError("This thread already exists; use ask_followup or choose a new thread_id.")
    state = {**_fresh_request(1, test_fault, max_model_calls), "run_id": thread_id, "request_kind": "new_analysis",
             "research_question": question, "design_info": copy.deepcopy(design_info),
             "original_data_path": str(data_path), "data_path": str(data_path), "data_version": "v1",
             "data_fingerprint": fingerprint(data_path), "excluded_ids": [], "verified_ids": [], "correction_log": [],
             "conf_level": settings.DEFAULT_CONF_LEVEL, "session_memory": {}, "errors": [], "trace": [], "model_calls": []}
    return graph.invoke(state, config_for(thread_id))


def ask_followup(graph, thread_id, question, *, data_path=None, design_info=None, test_fault=None,
                 max_model_calls=settings.MAX_MODEL_CALLS_PER_REQUEST):
    snapshot = graph.get_state(config_for(thread_id))
    if snapshot.next:
        raise ValueError("This thread is paused; answer the outstanding clarification before asking a follow-up.")
    previous = snapshot.values
    if not previous:
        raise ValueError("Unknown thread_id; start an analysis with new_run first.")
    state = _fresh_request(previous["request_number"] + 1, test_fault, max_model_calls)
    success = previous.get("session_memory", {}).get("last_success", {})
    state.update(copy.deepcopy({k: v for k, v in success.items() if k != "request_number"}))
    state.update(request_kind="followup", followup_question=question)
    if data_path is not None:
        state["data_path"] = str(data_path)
        state["followup_data_changed"] = fingerprint(data_path) != success.get("data_fingerprint")
        state["followup_dataset_replaced"] = Path(data_path).resolve() != Path(success.get("data_path", data_path)).resolve()
    if design_info is not None:
        state["design_info"] = copy.deepcopy(design_info)
        state["followup_design_changed"] = design_info != success.get("design_info")
    return graph.invoke(state, config_for(thread_id))


def resume_answers(graph, thread_id, answers):
    snapshot = graph.get_state(config_for(thread_id))
    if "request_clarification" not in snapshot.next:
        raise ValueError("This thread is not waiting for clarification answers.")
    return graph.invoke(Command(resume=answers), config_for(thread_id))


def collect_answers(open_items, input_fn=input):
    """Ask again on invalid input; return None in a noninteractive notebook, never invented answers."""
    answers = []
    try:
        for item in open_items:
            print(f"[{item['request_id']}] {item['question']}")
            while True:
                action = input_fn(f"Action ({' / '.join(item['allowed_responses'])}): ").strip().lower()
                answer = {"request_id": item["request_id"], "action": action}
                if action == "correct":
                    answer["new_value"] = input_fn("Verified replacement value: ")
                answer["reason"] = "" if action == "stop" else input_fn("Reason or source: ")
                try:
                    accepted = validate_answer(item, answer)
                except ValueError as exc:
                    print(f"Not accepted: {exc}. Please answer again.")
                    continue
                answers.append(accepted)
                if action == "stop":
                    return [accepted]
                break
    except (EOFError, OSError):
        print("Interactive input is unavailable. The graph remains paused; no decisions were supplied.")
        return None
    return answers
