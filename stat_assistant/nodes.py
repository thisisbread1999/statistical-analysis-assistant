"""Workflow nodes: two agents, deterministic Python tools, and explicit human decisions."""
from __future__ import annotations

import copy
import csv
import hashlib
import math
import operator
import re
import threading
import time
import uuid
from pathlib import Path
from typing import Annotated, TypedDict

from langchain_core.runnables import RunnableConfig
from langgraph.errors import GraphBubbleUp
from langgraph.types import interrupt

from . import settings
from .agents import default_question
from .methods import METHODS, NO_METHOD, direction_of, hypotheses, protected_values
from .report import check_report as check_draft, format_stats_block, render
from .schemas import (AnalysisPlan, FollowupDecision, LLMDiagnosticReport, MergeAssessment,
                      ReportDraft, ReviewVerdict)


class AnalysisState(TypedDict, total=False):
    run_id: str
    request_number: int
    request_kind: str
    research_question: str
    followup_question: str
    followup_focus: str
    followup_route: str
    design_info: dict
    original_data_path: str
    data_path: str
    data_version: str
    data_fingerprint: str
    followup_data_changed: bool
    followup_design_changed: bool
    followup_dataset_replaced: bool
    analysis_plan: dict
    plan_feedback: list
    plan_revision_count: int
    plan_route: str
    data_summary: dict
    llm_diagnostics: dict
    stat_diagnostics: dict
    diagnostic_route: str
    diagnostic_assessment: dict
    stop_reasons: list
    clarification_requests: list
    clarification_answers: list
    clarification_rounds: int
    rejected_answers: list
    excluded_ids: list
    verified_ids: list
    correction_log: list
    user_requested_stop: bool
    conf_level: float
    stat_result: dict
    stats_block: dict
    report_draft: dict
    rendered_draft: dict
    program_check: dict
    review_verdict: dict
    revision_count: int
    final_status: str
    final_report: str
    session_memory: dict
    test_fault: dict | None
    max_model_calls: int
    mode: str
    errors: Annotated[list, operator.add]
    model_calls: Annotated[list, operator.add]
    trace: Annotated[list, operator.add]


def fingerprint(path: str) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def current_errors(state: dict) -> list:
    return [e for e in state.get("errors", []) if e["request_number"] == state["request_number"]]


def _read_csv(path):
    with open(path, encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames or len(set(reader.fieldnames)) != len(reader.fieldnames):
            raise ValueError("The CSV must have a nonempty header with unique column names.")
        rows = list(reader)
        if any(None in row or any(v is None for v in row.values()) for row in rows):
            raise ValueError("CSV rows must contain exactly the columns in the header.")
        return list(reader.fieldnames), rows


def _schema(schema, result):
    return schema.model_validate(result).model_dump()


def _design_problems(design):
    text = str(design.get("independence", "")).lower()
    if design.get("independent") is False or re.search(
            r"\b(not independent|non-independent|dependent observations|clustered|repeated|paired)\b", text):
        return ["The stated dependent, paired, repeated or clustered design is not supported."]
    if design.get("independent") is not True and "independent" not in text:
        return ["Independence must be explicitly confirmed by the user; it cannot be inferred from the CSV."]
    if any(s in text for s in ("unknown", "unclear", "not sure", "uncertain")):
        return ["Observation independence is uncertain; confirm the study design before analysis."]
    return []


def tool_request(state):
    plan, design = state["analysis_plan"], state["design_info"]
    variables = design.get("variables", {})
    roles = {k: plan[k] for k in METHODS[plan["method"]].roles}
    return {"data_path": state["data_path"], "data_version": state["data_version"],
            "excluded_ids": state.get("excluded_ids", []), "id_column": design.get("id_column"),
            "method": plan["method"], "roles": roles,
            "group_labels": [plan["group_1_label"], plan["group_2_label"]] if plan["method"] == "welch_t_test" else None,
            "valid_ranges": {**{k: v["range"] for k, v in variables.items() if "range" in v},
                             **design.get("valid_ranges", {})},
            "valid_levels": {**{k: v["levels"] for k, v in variables.items() if "levels" in v},
                             **design.get("valid_levels", {})},
            "conf_level": state.get("conf_level", settings.DEFAULT_CONF_LEVEL), "alpha": settings.ALPHA}


def validate_answer(request, answer):
    """Validate the human answer without changing data or consuming a diagnostic round."""
    if not isinstance(answer, dict):
        raise ValueError("Each answer must be an object.")
    action = str(answer.get("action", "")).strip().lower()
    if action not in request["allowed_responses"]:
        raise ValueError(f"Allowed actions: {request['allowed_responses']}")
    # The selected action is the user's explicit decision. Supporting notes are optional;
    # keep an omitted note empty rather than inventing a rationale or verification source.
    reason = str(answer.get("reason") or "").strip()
    result = {"request_id": request["request_id"], "action": action, "reason": reason}
    if action == "correct":
        value = answer.get("new_value")
        if value is None or isinstance(value, (dict, list, bool)) or not str(value).strip():
            raise ValueError("A nonempty new_value is required for a correction.")
        value = str(value)
        if request.get("field_type") == "numeric":
            try:
                number = float(value)
            except ValueError:
                raise ValueError("The correction must be numeric.") from None
            if not math.isfinite(number):
                raise ValueError("The correction must be finite.")
            bounds = request.get("valid_range")
            if bounds and not float(bounds[0]) <= number <= float(bounds[1]):
                raise ValueError(f"The correction must be within the user-stated range {bounds}.")
        if request.get("valid_levels") and value not in request["valid_levels"]:
            raise ValueError(f"The label must exactly match {request['valid_levels']}.")
        result["new_value"] = value
    return result


def validate_answers(requests, answers):
    """All-or-nothing validation; stop can be supplied as a single answer."""
    if not isinstance(answers, list):
        raise ValueError("Answers must be a list of objects keyed by request_id.")
    by_id = {r["request_id"]: r for r in requests}
    accepted, seen = [], set()
    for answer in answers:
        if not isinstance(answer, dict) or answer.get("request_id") not in by_id:
            raise ValueError("Every answer must name a current request_id.")
        rid = answer["request_id"]
        if rid in seen:
            raise ValueError(f"Duplicate answer: {rid}")
        seen.add(rid)
        accepted.append(validate_answer(by_id[rid], answer))
    if any(a["action"] == "stop" for a in accepted):
        return [next(a for a in accepted if a["action"] == "stop")]
    if seen != set(by_id):
        raise ValueError(f"Answers are missing for {sorted(set(by_id) - seen)}.")
    return accepted


class Nodes:
    def __init__(self, agent_a, agent_b, tool_runner):
        self.a, self.b, self.tool = agent_a, agent_b, tool_runner

    def guarded(self, name):
        function = getattr(self, name)

        def node(state: AnalysisState, config: RunnableConfig):
            started, calls = time.time(), []
            request_number = state["request_number"]

            def call(agent, method, *args, **kwargs):
                count = sum(c["request_number"] == request_number for c in state.get("model_calls", [])) + len(calls)
                if count >= state.get("max_model_calls", settings.MAX_MODEL_CALLS_PER_REQUEST):
                    raise RuntimeError("The model-call limit for the current request has been reached.")
                entry = {"request_number": request_number, "node": name, "method": method,
                         "model": agent.model_name, "mode": "MOCK" if agent.is_mock else "REAL", "status": "started"}
                calls.append(entry)
                try:
                    result = getattr(agent, method)(*args, **kwargs)
                except Exception:
                    entry["status"] = "failed"
                    raise
                entry["status"] = "completed"
                return result

            try:
                if current_errors(state) and name not in ("issue_notice", "save_session"):
                    update = {}
                    status = "skipped_after_error"
                else:
                    fault = state.get("test_fault") or {}
                    if fault.get("kind") == "model_failure" and fault.get("node") == name:
                        raise RuntimeError("TEST INPUT: simulated model failure.")
                    update = function(state, call)
                    status = "completed"
            except GraphBubbleUp:
                raise
            except Exception as exc:
                update = {"errors": [{"request_number": request_number, "node": name,
                                      "type": type(exc).__name__, "message": str(exc)}]}
                status = "error"
            update["model_calls"] = calls
            update["trace"] = [{"request_number": request_number, "node": name, "status": status,
                                "start": started, "end": time.time(), "thread": threading.current_thread().name,
                                "data_version": state.get("data_version"),
                                "step": config.get("metadata", {}).get("langgraph_step")}]
            return update
        node.__name__ = name
        return node

    def plan_analysis(self, s, call):
        design_problems = _design_problems(s["design_info"])
        if design_problems:
            return {"plan_route": "stop", "stop_reasons": design_problems}
        columns, _ = _read_csv(s["data_path"])
        plan = _schema(AnalysisPlan, call(self.a, "plan", s["research_question"], s["design_info"], columns,
                                        s.get("plan_feedback", [])))
        if plan["method"] == NO_METHOD:
            return {"analysis_plan": plan, "plan_route": "stop", "stop_reasons": [plan["method_rationale"]]}
        if s.get("plan_revision_count", 0) and plan["method"] != s["analysis_plan"]["method"]:
            return {"plan_route": "stop", "stop_reasons": ["A plan repair cannot silently change the statistical target or method."]}
        problems, variables = [], s["design_info"].get("variables", {})
        roles = METHODS[plan["method"]].roles
        for role, expected_type in roles.items():
            col = plan[role]
            if col not in columns:
                problems.append(f"Role {role} must name a CSV column, found {col!r}.")
            actual_type = variables.get(col, {}).get("type")
            if actual_type and actual_type != expected_type:
                problems.append(f"Role {role} must be {expected_type}; user metadata says {actual_type}.")
        if len({plan[r] for r in roles}) != len(roles):
            problems.append("The two variable roles must reference different columns.")
        if plan["method"] == "welch_t_test":
            labels = [plan["group_1_label"], plan["group_2_label"]]
            if not all(labels) or len(set(labels)) != 2:
                problems.append("Welch requires two different, explicitly ordered group labels.")
            levels = variables.get(plan["group"], {}).get("levels", [])
            if levels and (len(levels) != 2 or set(labels) != set(levels)):
                problems.append("Welch labels must match the two levels in the user metadata.")
        count = s.get("plan_revision_count", 0)
        if problems:
            again = count < settings.MAX_PLAN_REVISIONS
            return {"analysis_plan": plan, "plan_feedback": problems,
                    "plan_revision_count": count + int(again),
                    "plan_route": "revise_plan_once" if again else "stop", "stop_reasons": problems}
        return {"analysis_plan": plan, "plan_route": "ready", "stop_reasons": [], "plan_feedback": []}

    def prepare_data_summary(self, s, call):
        before = fingerprint(s["data_path"])
        result = self.tool("summary", tool_request(s), f"{s['run_id']}-summary-{s['request_number']}")
        if result["status"] != "ok":
            raise ValueError(f"The summary tool refused the request: {result}")
        if fingerprint(s["data_path"]) != before:
            raise ValueError("The data changed while its summary was being prepared; restart on a stable data version.")
        return {"data_summary": result, "data_fingerprint": before}

    def llm_diagnostics(self, s, call):
        return {"llm_diagnostics": _schema(LLMDiagnosticReport, call(
            self.a, "diagnose", s["analysis_plan"], s["design_info"], s["data_summary"]))}

    def stat_diagnostics(self, s, call):
        return {"stat_diagnostics": self.tool("diagnostics", tool_request(s), f"{s['run_id']}-diagnostics-{s['request_number']}")}

    def merge_diagnostics(self, s, call):
        d, request = s["stat_diagnostics"], tool_request(s)
        stop = [i["detail"] for i in d.get("method_findings", [])]
        stop += [i["issue"] for i in s["llm_diagnostics"]["issues"] if i["severity"] == "out_of_scope"]
        if d["status"] != "ok":
            stop.append(f"The diagnostic tool returned {d['status']}.")
        if fingerprint(s["data_path"]) != s["data_fingerprint"]:
            stop.append("The data changed during diagnostics; restart on the new data version.")
        open_items = []
        for i in d.get("findings", []):
            rid = f"{i['record_id']}:{i['field']}:{i['check']}:{i.get('row_number', '')}:{i['value_as_written']}"
            if rid in s.get("verified_ids", []) and i["severity"] == "verify":
                continue
            if i["check"] in ("missing_id", "duplicate_id"):
                stop.append("Correct missing or duplicate identifiers in a new source file before proceeding.")
                continue
            role = next((r for r, col in request["roles"].items() if col == i["field"]), None)
            options = ["correct", "exclude", "stop"]
            if i["severity"] == "verify":
                options.insert(0, "verify")
            item = {**i, "request_id": rid, "allowed_responses": options,
                    "field_type": METHODS[s["analysis_plan"]["method"]].roles.get(role),
                    "valid_range": request["valid_ranges"].get(i["field"]),
                    "valid_levels": request["valid_levels"].get(i["field"])}
            item["question"] = default_question(item)
            open_items.append(item)
        if open_items and s.get("clarification_rounds", 0) >= settings.MAX_CLARIFICATION_ROUNDS:
            stop.append("The bounded clarification rounds are exhausted; unresolved findings remain.")
        route = "stop" if stop else "needs_clarification" if open_items else "proceed"
        assessment = _schema(MergeAssessment, call(self.a, "merge", route=route, open_items=open_items,
            stop_reasons=stop, analysis_plan=s["analysis_plan"], design_info=s["design_info"],
            llm_diagnostics=s["llm_diagnostics"], stat_diagnostics=d))
        questions = {q["request_id"]: q["question"] for q in assessment["questions"]}
        for item in open_items:
            if questions.get(item["request_id"]):
                item["question"] = questions[item["request_id"]]
        return {"diagnostic_route": route, "diagnostic_assessment": assessment,
                "clarification_requests": open_items, "stop_reasons": stop}

    def request_clarification(self, s, call):
        rejections = []
        while True:
            answers = interrupt({"data_version": s["data_version"], "requests": s["clarification_requests"],
                                 "previous_rejections": rejections})
            try:
                accepted = validate_answers(s["clarification_requests"], answers)
            except ValueError as exc:
                rejections = [str(exc)]
                continue
            return {"clarification_answers": accepted, "clarification_rounds": s.get("clarification_rounds", 0) + 1,
                    "rejected_answers": rejections}

    def apply_corrections(self, s, call):
        answers = validate_answers(s["clarification_requests"], s["clarification_answers"])
        if any(a["action"] == "stop" for a in answers):
            return {"user_requested_stop": True, "stop_reasons": ["The user requested a stop; no corrections were applied."]}
        if fingerprint(s["data_path"]) != s["data_fingerprint"]:
            raise ValueError("The data changed after the clarification request; the answers cannot be applied safely.")
        columns, rows = _read_csv(s["data_path"])
        requests = {r["request_id"]: r for r in s["clarification_requests"]}
        excluded, verified = set(s.get("excluded_ids", [])), set(s.get("verified_ids", []))
        version = f"v{int(s['data_version'][1:]) + 1}"
        log = list(s.get("correction_log", []))
        changed_cells = {}
        for answer in answers:
            item = requests[answer["request_id"]]
            id_column = s["design_info"].get("id_column")
            indices = [i for i, row in enumerate(rows) if
                       (row[id_column] if id_column else f"row {i+1}") == item["record_id"]]
            if len(indices) != 1:
                raise ValueError("The clarification record must identify exactly one row.")
            index = indices[0]
            if rows[index][item["field"]] != item["value_as_written"]:
                raise ValueError("The observed value no longer matches the clarification request.")
            action, new_value = answer["action"], answer.get("new_value")
            cell = (index, item["field"])
            if action == "correct":
                if cell in changed_cells and changed_cells[cell] != new_value:
                    raise ValueError("Conflicting corrections were supplied for the same cell.")
                changed_cells[cell] = new_value
            elif action == "exclude":
                excluded.add(item["record_id"])
            elif action == "verify":
                verified.add(item["request_id"])
            log.append({**answer, "record_id": item["record_id"], "field": item["field"], "check": item["check"],
                        "old_value": item["value_as_written"], "new_value": new_value,
                        "from_version": s["data_version"], "to_version": version,
                        "request_number": s["request_number"], "source": "explicit user answer", "rows_affected": 1})
        for (index, field), value in changed_cells.items():
            rows[index][field] = value
        directory = settings.OUTPUT_DIR / "data_versions"
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"{uuid.uuid4().hex}_{version}.csv"
        with path.open("w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=columns)
            writer.writeheader()
            writer.writerows(rows)
        return {"data_path": str(path), "data_version": version, "excluded_ids": sorted(excluded),
                "verified_ids": sorted(verified), "correction_log": log, "user_requested_stop": False}

    def run_statistical_test(self, s, call):
        if fingerprint(s["data_path"]) != s["data_fingerprint"]:
            raise ValueError("The data changed after diagnostics; run fresh diagnostics before testing.")
        result = self.tool("run_test", tool_request(s), f"{s['run_id']}-test-{s['request_number']}")
        if fingerprint(s["data_path"]) != s["data_fingerprint"]:
            raise ValueError("The data changed while the statistical test was running; the result cannot be used for this data version.")
        if result["status"] != "ok":
            raise ValueError(f"The statistical tool refused the request: {result}")
        return {"stat_result": result}

    def build_stats_block(self, s, call):
        result, plan, request = s["stat_result"], s["analysis_plan"], tool_request(s)
        method = plan["method"]
        limitations = dict(METHODS[method].limitation)
        if s["design_info"].get("randomized") is not True:
            limitations["nonrandom_design"] = "Random allocation was not established. This analysis describes an association and does not establish causation."
        log = [r for r in s.get("correction_log", []) if r["record_id"] in s.get("excluded_ids", []) and r["action"] == "exclude"]
        if any(r["check"].startswith("missing") for r in log):
            limitations["missing_data"] = "User-confirmed exclusions include missing values. The missingness mechanism is unknown; complete-case analysis may be biased and generalizability is limited."
        if any(not r["check"].startswith("missing") for r in log):
            limitations["other_exclusions"] = "Other records were excluded with explicit user confirmation; exclusions may affect the estimate and generalizability."
        if method in ("pearson_correlation", "simple_linear_regression", "welch_t_test"):
            limitations["analysis_assumptions"] = "Inference is conditional on the stated independent observations and the method's distribution and model assumptions; descriptive checks do not prove these assumptions."
        if result.get("tool_warnings"):
            limitations["tool_warnings"] = "The statistical tool reported additional warnings, shown with the protected results; these warnings must be considered when interpreting the estimate."
        if method == "pearson_correlation" and result.get("t_statistic") is None:
            limitations["perfect_correlation"] = "The sample correlation lies at the boundary of its possible range. Its reported interval is degenerate; this does not establish a perfect relationship in the population."
        sb = {"method": method, "method_label": METHODS[method].label, "data_version": s["data_version"],
              "tool_call": result["tool_call"], "values": protected_values(method, result, s["conf_level"]),
              "hypotheses": hypotheses(method, request["roles"], request["group_labels"]),
              "required_placeholders": list(METHODS[method].required), "required_limitations": limitations,
              "direction": direction_of(method, result), "decision": "reject_H0" if result["p_value"] < settings.ALPHA else "do_not_reject_H0",
              "distribution_checks": s["stat_diagnostics"].get("distribution_checks", {}),
              "observed": result.get("observed"), "yates": result.get("yates_correction", False),
              "tool_warnings": result.get("tool_warnings", []), "t_statistic_note": result.get("t_statistic_note", "")}
        return {"stats_block": sb}

    def _context(self, s):
        return {**s["stats_block"], "placeholders": s["stats_block"]["values"],
                "analysis_plan": s["analysis_plan"], "design_info": s["design_info"],
                "sentence_plan": METHODS[s["analysis_plan"]["method"]].sentence_plan,
                "stat_result": s["stat_result"], "correction_log": s.get("correction_log", []),
                "followup_focus": s.get("followup_focus", "")}

    def draft_report(self, s, call):
        draft = _schema(ReportDraft, call(self.a, "draft", self._context(s)))
        draft["version"] = "draft1"
        fault = s.get("test_fault") or {}
        if fault.get("kind") == "causal_claim":
            draft["interpretation"] += " Tutoring caused an improvement in exam scores."
        elif fault.get("kind") == "wrong_number":
            draft["interpretation"] = draft["interpretation"].replace("{p_value}", "0.9999")
        return {"report_draft": draft}

    def check_report(self, s, call):
        draft = s["report_draft"]
        rendered = {**draft, "interpretation": render(draft["interpretation"], s["stats_block"]["values"]),
                    "limitations": [{**l, "text": render(l["text"], s["stats_block"]["values"])} for l in draft["limitations"]]}
        return {"program_check": check_draft(s["stats_block"], draft), "rendered_draft": rendered}

    def review_report(self, s, call):
        verdict = _schema(ReviewVerdict, call(self.b, "review", {"report_draft": s["rendered_draft"],
            "stat_result": s["stat_result"], "protected_statistics": s["stats_block"],
            "analysis_plan": s["analysis_plan"], "design_info": s["design_info"],
            "correction_log": s.get("correction_log", []), "required_limitations": s["stats_block"]["required_limitations"]}))
        if verdict["passed"] is False and not verdict["issues"]:
            raise ValueError("The reviewer returned an inconsistent verdict: passed=false with no review issues. The report cannot be treated as reviewed successfully.")
        # A critical issue determines failure. Optional wording comments cannot force a revision.
        verdict["passed"] = not any(i["severity"] == "critical" for i in verdict["issues"])
        return {"review_verdict": verdict}

    def revise_report(self, s, call):
        draft = _schema(ReportDraft, call(self.a, "revise", self._context(s), s["report_draft"],
            s["review_verdict"]["issues"], s["program_check"]["problems"]))
        draft["version"] = "draft2"
        return {"report_draft": draft, "revision_count": s.get("revision_count", 0) + 1}

    def deliver_report(self, s, call):
        draft = s["rendered_draft"]
        label = "MOCK: rule-based agent stand-ins; Python calculations are real." if self.a.is_mock else "REAL: two distinct models; statistics computed with Python."
        test = "\nTEST INPUT: " + str(s["test_fault"]) if s.get("test_fault") else ""
        text = label + test + "\n\n" + format_stats_block(s["stats_block"]) + "\n\n" + draft["interpretation"]
        text += "\n\nLimitations:\n" + "\n".join("- " + l["text"] for l in draft["limitations"])
        return {"final_status": "delivered", "final_report": text}

    def issue_notice(self, s, call):
        messages = list(s.get("stop_reasons", []))
        messages += [e["message"] for e in current_errors(s)]
        if not messages:
            messages = ["The report did not pass the program checks and review within the revision limit."]
        prefix = "TEST INPUT. " if s.get("test_fault") else ""
        return {"final_status": "stopped", "final_report": prefix + "No validated inferential report was delivered.\n" + "\n".join(messages)}

    def save_session(self, s, call):
        memory = copy.deepcopy(s.get("session_memory", {}))
        if s.get("final_status") == "delivered":
            keys = ("research_question", "design_info", "original_data_path", "data_path", "data_version", "data_fingerprint", "analysis_plan",
                    "excluded_ids", "verified_ids", "correction_log", "conf_level", "stat_result", "stats_block", "stat_diagnostics")
            memory["last_success"] = {k: copy.deepcopy(s[k]) for k in keys if k in s}
            memory["last_success"]["request_number"] = s["request_number"]
        memory["last_request_status"] = s["final_status"]
        return {"session_memory": memory}

    def handle_followup(self, s, call):
        previous = s.get("session_memory", {}).get("last_success")
        if not previous:
            return {"followup_route": "stop", "stop_reasons": ["A follow-up requires an earlier successful analysis on this thread."]}
        decision = _schema(FollowupDecision, call(self.a, "followup", s["followup_question"], previous))
        kind, updates = decision["kind"], {"followup_focus": decision["focus"]}
        bytes_changed = s.get("followup_data_changed", False) or fingerprint(s["data_path"]) != previous["data_fingerprint"]
        design_changed = s.get("followup_design_changed", False)
        changed = bytes_changed or design_changed
        if bytes_changed and not s.get("followup_dataset_replaced", False):
            return {"followup_route": "stop", "stop_reasons": ["The previously analysed file was edited externally. Supply the revised data as a new file so that the saved data version and correction history remain auditable."]}
        if kind == "unsupported":
            return {**updates, "followup_route": "stop", "stop_reasons": [decision["rationale"]]}
        if kind == "change_confidence_level":
            level = decision["confidence_level"]
            if not math.isfinite(level) or not 0 < level < 1:
                raise ValueError("The confidence level must be strictly between zero and one.")
            if previous["analysis_plan"]["method"] == "chi_square_independence":
                return {"followup_route": "stop", "stop_reasons": ["A confidence interval for Cramer's V is not implemented."]}
            updates["conf_level"] = level
        if kind == "new_question" or changed:
            updates.update(research_question=s["followup_question"] if kind == "new_question" else previous["research_question"],
                           followup_route="new_question", excluded_ids=[], verified_ids=[],
                           plan_feedback=[], plan_revision_count=0, clarification_rounds=0,
                           data_summary={}, llm_diagnostics={}, stat_diagnostics={}, stat_result={}, stats_block={})
            if changed:
                updates["data_version"] = f"v{int(s['data_version'][1:]) + 1}"
            if s.get("followup_dataset_replaced", False) and bytes_changed:
                updates["correction_log"] = []
                updates["original_data_path"] = s["data_path"]
            return updates
        updates["followup_route"] = "new_confidence_level" if kind == "change_confidence_level" else "re_explain"
        return updates
