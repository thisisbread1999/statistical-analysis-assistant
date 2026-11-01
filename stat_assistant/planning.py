"""Bounded request scoping and human approval of an executable analysis plan."""
from __future__ import annotations

import hashlib
import json
import re

from langgraph.types import interrupt

from .references import retrieve_method_cards
from .schemas import RequestScope


def simple_scope(question: str) -> dict:
    """Conservative, explicitly rule-based mock scoping; not an LLM evaluation."""
    parts = re.split(r"\s*;\s*(?=(?:compare|test|fit|estimate|calculate|run|examine)\b)|\s+(?:and|also)\s+(?=(?:compare|test|fit|estimate|calculate|run|examine)\b)|[；](?=比较|检验|分析)|同时(?=比较|检验|分析)",
                     question.strip(), flags=re.I)
    parts = [part.strip() for part in parts if part.strip()]
    too_many = len(parts) > 4
    parts = parts[:4]
    ambiguous = bool(re.search(r"\b(?:regression between|not (?:chosen|decided)|not decided whether)\b", question, re.I)) and not re.search(
        r"\b(?:predictor|outcome|predict|dependent|response)\b", question, re.I)
    ambiguous = ambiguous or bool(re.search(r"not decided whether|outcome (?:unspecified|not chosen)|which .* outcome", question, re.I))
    return {"tasks": [{"task_id": f"task_{i + 1}", "question": part} for i, part in enumerate(parts)],
            "needs_clarification": ambiguous or too_many,
            "clarification_question": "More than four targets were found. Only the first four are shown; narrow the request to one target." if too_many else
                "Specify the predictor and outcome before confirming the question." if ambiguous else ""}


def plan_identity(plan: dict, question: str, data_fingerprint: str) -> str:
    payload = json.dumps({"plan": plan, "question": question, "data_fingerprint": data_fingerprint},
                         sort_keys=True, ensure_ascii=False, allow_nan=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def unsupported_scope_reason(question: str) -> str | None:
    if re.search(r"\b(?:filter|subset|last year|calendar year|only (?:for|in|students|looked))\b|仅(?:看|分析)|筛选|去年", question, re.I):
        return "Filtering is not supported. Supply a new filtered CSV and confirm its study design."
    return None


class PlanningNodes:
    def scope_request(self, s, call):
        from .nodes import _design_problems
        problems = _design_problems(s["design_info"])
        if problems:
            return {"scope_route": "stop", "stop_reasons": problems}
        question = s["research_question"]
        scope_problem = unsupported_scope_reason(question)
        if scope_problem:
            return {"scope_route": "stop", "stop_reasons": [scope_problem]}
        # In the mock path and custom test doubles this is deliberately not a model call.
        scope = call(self.a, "scope", question, s["design_info"]) if hasattr(self.a, "scope") else simple_scope(question)
        scope = RequestScope.model_validate(scope).model_dump()
        ids = [task["task_id"] for task in scope["tasks"]]
        if len(ids) != len(set(ids)):
            raise ValueError("The request planner returned duplicate task ids.")
        return {"request_scope": scope,
                "scope_route": "choose" if len(ids) > 1 or scope["needs_clarification"] else "single"}

    def request_scope_confirmation(self, s, call):
        scope = s["request_scope"]
        if s.get("scope_selection_count", 0) >= 3:
            return {"scope_route": "stop", "stop_reasons": ["The question-selection limit was reached; start a new, more specific request."]}
        while True:
            decision = interrupt({"kind": "scope_selection", "tasks": scope["tasks"],
                                  "message": scope["clarification_question"] or
                                  "This request contains several targets. Choose one analysis for this run; run the others separately.",
                                  "original_question": s["research_question"]})
            if not isinstance(decision, dict):
                continue
            if decision.get("action") == "stop":
                return {"scope_route": "stop", "stop_reasons": ["The user stopped before choosing an analysis target."]}
            task = next((t for t in scope["tasks"] if t["task_id"] == decision.get("task_id")), None)
            question = decision.get("question") or (task or {}).get("question", "")
            if decision.get("action") == "select" and task and isinstance(question, str) and 0 < len(question.strip()) <= 10_000:
                # Re-scope user edits; selecting one task must not hide another multi-target request.
                return {"research_question": question.strip(), "followup_focus": question.strip(), "selected_task_id": task["task_id"],
                        "scope_route": "single", "require_plan_confirmation": True,
                        "scope_selection_count": s.get("scope_selection_count", 0) + 1}

    def retrieve_method_guidance(self, s, call):
        return {"retrieved_references": retrieve_method_cards(s["research_question"])}

    def approve_analysis_plan(self, s, call):
        if not s.get("require_plan_confirmation"):
            return {"approval_route": "approved", "plan_approval": {"status": "not_requested_programmatic_run"}}
        from .nodes import fingerprint
        digest = plan_identity(s["analysis_plan"], s["research_question"], s["data_fingerprint"])
        steps = ["Check variable meanings and study design alongside Python data checks",
                 "Ask you to resolve any flagged records; retain the original input",
                 f"Execute the approved {s['analysis_plan']['method']} Python tool",
                 "Generate an explanation, check its numbers, and request the other model's review",
                 "Revise once if needed, then deliver or stop with an explanation"]
        while True:
            decision = interrupt({"kind": "plan_approval", "plan_id": digest, "question": s["research_question"],
                                  "plan": s["analysis_plan"], "steps": steps,
                                  "references": s.get("retrieved_references", [])})
            if not isinstance(decision, dict):
                continue
            if decision.get("action") == "stop":
                return {"approval_route": "stop", "stop_reasons": ["The user declined the proposed analysis plan."]}
            if decision.get("action") == "change_question" and isinstance(decision.get("question"), str) and decision["question"].strip():
                if s.get("scope_revision_count", 0) >= 2:
                    return {"approval_route": "stop", "stop_reasons": ["The plan-change limit was reached; start a new request."]}
                return {"approval_route": "replan", "research_question": decision["question"].strip()[:10_000],
                        "followup_focus": decision["question"].strip()[:10_000],
                        "scope_revision_count": s.get("scope_revision_count", 0) + 1,
                        "plan_revision_count": 0, "plan_feedback": [], "plan_approval": {}}
            if decision.get("action") == "approve" and decision.get("plan_id") == digest:
                if plan_identity(s["analysis_plan"], s["research_question"], fingerprint(s["data_path"])) != digest:
                    raise ValueError("The data or plan changed during approval; start again on a stable version.")
                return {"approval_route": "approved", "plan_approval": {"status": "approved", "plan_id": digest,
                        "question": s["research_question"], "method": s["analysis_plan"]["method"],
                        "approved_plan": s["analysis_plan"]}}
