"""Frozen 31-case benchmark; MOCK mechanics and live two-model results are separate.

No teammate code is imported. Source gold plans are used only by the explicitly
labelled offline stand-in and the independent evaluator, never by live agents.
"""
from __future__ import annotations

import argparse
import copy
import csv
import hashlib
import json
import math
import os
import re
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

from stat_assistant import settings
from stat_assistant.agents import MockAnalysisAgentA, MockReviewAgentB
from stat_assistant.methods import METHODS as METHOD_SPECS
from stat_assistant.models import create_agents, load_env
from stat_assistant.nodes import Nodes, tool_request
from stat_assistant.runtime import ask_followup, config_for, new_run, resume_answers
from stat_assistant.schemas import AnalysisPlan, FollowupDecision
from stat_assistant.workflow import build_graph

ROOT = Path(__file__).resolve().parent
SOURCE_ROOT = ROOT / "examples" / "benchmark_v2"
ADAPTED_ROOT = ROOT / "examples" / "benchmark_v2_adapted"
SOURCE_COMMIT = "b7eff1c4a8035f196ac4bfc73ef3fe88956dadb5"
GROUPS = ["normal", "boundary", "clarification", "stop", "followup"]
METHODS = {"difference": "welch_t_test", "correlation": "pearson_correlation",
           "categorical": "chi_square_independence", "regression": "simple_linear_regression",
           "unsupported": "no_supported_method"}
POLICY_STOPS = {"unknown_design", "ambiguous_outcome", "regression_direction", "paired_design",
                "chi_square_sparse", "chi_square_one_category", "chi_square_numeric_codes",
                "pearson_constant", "pearson_too_few", "regression_constant",
                "regression_perfect", "unsupported_multivariable"}
AMBIGUOUS = {"ambiguous_outcome", "regression_direction"}
OFFLINE_LABEL = "MOCK: prespecified fixture plans and rule-based reports; mechanics only, NOT LLM accuracy"
FIXTURE_LABEL = "TEST FIXTURE: synthetic generator provenance; not a human response or human semantic label"


def _hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def sanitize(value):
    """Retain evidence while redacting credentials from provider exception strings."""
    if isinstance(value, dict):
        return {str(k): ("[REDACTED]" if re.search(r"api.?key|authorization|access.?token|password", str(k), re.I)
                        else sanitize(v)) for k, v in value.items()}
    if isinstance(value, (tuple, list)):
        return [sanitize(v) for v in value]
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, np.generic):
        return sanitize(value.item())
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if not isinstance(value, str):
        return value
    for key, secret in os.environ.items():
        if secret and len(secret) >= 8 and re.search(r"KEY|TOKEN|PASSWORD|SECRET", key, re.I):
            value = value.replace(secret, "[REDACTED]")
    value = re.sub(r"\bBearer\s+[^\s\"']+", "Bearer [REDACTED]", value, flags=re.I)
    value = re.sub(r"\bsk-[A-Za-z0-9_-]{8,}", "[REDACTED]", value)
    value = re.sub(r"(api[_-]?key[=:\s]+)[^\s&,\"']+", r"\1[REDACTED]", value, flags=re.I)
    return value


def _json_write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(sanitize(value), indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")
    temporary.replace(path)


def _column_metadata(data, case_id):
    """Register column types from CSV representation, without consulting gold roles."""
    variables = {}
    for column in data.columns:
        values = data[column].dropna()
        numeric = bool(len(values)) and pd.to_numeric(values, errors="coerce").notna().all()
        if column == "date":
            variables[column] = {"type": "date", "meaning": "Calendar date as written in the source CSV"}
        elif numeric:
            variables[column] = {"type": "numeric", "meaning": f"Numeric source field {column}; units not supplied"}
        else:
            levels = sorted(values.astype(str).unique(), key=str)
            variables[column] = {"type": "categorical", "levels": levels,
                                 "meaning": f"Source text labels in {column}"}
    # Codes alone do not establish categorical semantics or a valid recoding.
    if case_id == "chi_square_numeric_codes":
        for variable in variables.values():
            variable["meaning"] = "Numeric codes; categorical meaning and preprocessing not confirmed"
    return variables


def _design(source, data):
    original = source.get("metadata", {})
    design = {"variables": _column_metadata(data, source["id"]), "randomized": False,
              "assignment": "Observational synthetic fixture; allocation was not random.",
              "metadata_provenance": "Evaluation adapter: source design declaration and CSV column representations"}
    if original.get("design") == "independent":
        design.update(independent=True, independence="The fixture declaration confirms independent observations.")
    elif original.get("design") == "paired":
        design.update(independent=False, independence="Paired observations declared by the fixture.")
    else:
        design["independence"] = "Unknown; independence has not been confirmed."
    if source["id"] in AMBIGUOUS:
        design["analysis_target"] = "The user has not chosen the outcome or direction. Obtain a concrete target before analysis."
    if "group" in design["variables"] and len(design["variables"]["group"].get("levels", [])) == 2:
        levels = design["variables"]["group"]["levels"]
        # This is a declared evaluation contrast, visible to users and to live planning.
        design["variables"]["group"]["levels"] = list(reversed(levels))
        design["comparison_order"] = f"Requested contrast: {levels[1]} minus {levels[0]}."
    return design


def adapted_plan(case):
    """Translate source gold roles ONLY for controlled fixtures/offline mechanics."""
    p = case["source"]["plan"]
    method = METHODS[p["goal"]]
    if case["id"] in AMBIGUOUS:
        method = "no_supported_method"
    base = dict(method=method, outcome="", group="", group_1_label="", group_2_label="", x="", y="",
                target_parameter="Prespecified synthetic evaluation target", null_hypothesis="H0: zero association",
                alternative_hypothesis="H1: nonzero association", method_rationale="MOCK prespecified fixture plan",
                design_notes=[case["design_info"].get("independence", "")])
    if method == "welch_t_test":
        labels = sorted(case["data"][p["group"]].dropna().astype(str).unique(), key=str)
        base.update(outcome=p["outcome"], group=p["group"], group_1_label=labels[1], group_2_label=labels[0],
                    target_parameter=f"Mean {p['outcome']}: {labels[1]} minus {labels[0]}")
    elif method != "no_supported_method":
        base.update(x=p["x"], y=p["y"])
    else:
        base["method_rationale"] = "The target is ambiguous or the requested method is unsupported; obtain a new, explicit question."
    return AnalysisPlan.model_validate(base).model_dump()


def _registered_fixture_answers(case):
    """Independent fixed recipe: blanks are excluded; generated IQR observations verified.

    The recipe is frozen before model execution and can only match exact original
    row/field/check tuples. It is not inferred from an agent's clarification text.
    """
    plan = adapted_plan(case)
    method = plan["method"]
    if method == "no_supported_method":
        return []
    roles = METHOD_SPECS[method].roles
    data = case["data"]
    columns = [plan[r] for r in roles]
    usable = data[columns].notna().all(axis=1)
    recipes = []
    for column in columns:
        for index in data.index[data[column].isna()]:
            recipes.append({"record_id": f"row {int(index)+1}", "field": column, "check_prefix": "missing",
                            "action": "exclude", "label": FIXTURE_LABEL,
                            "reason": "TEST FIXTURE: source benchmark deliberately planted a missing cell; exclude that record for secondary complete-case calculation."})
    numeric_roles = [r for r in roles if METHOD_SPECS[method].roles[r] == "numeric"]
    for role in numeric_roles:
        column = plan[role]
        masks = [usable]
        if method == "welch_t_test":
            masks = [usable & (data[plan["group"]].astype(str) == label)
                     for label in (plan["group_1_label"], plan["group_2_label"])]
        values = pd.to_numeric(data[column], errors="coerce")
        for mask in masks:
            sample = values[mask]
            if len(sample) < 4:
                continue
            q1, q3 = np.quantile(sample, [.25, .75])
            flagged = mask & ((values < q1-1.5*(q3-q1)) | (values > q3+1.5*(q3-q1)))
            for index in data.index[flagged]:
                recipes.append({"record_id": f"row {int(index)+1}", "field": column,
                                "check_prefix": "boxplot_flag", "action": "verify", "label": FIXTURE_LABEL,
                                "reason": "TEST FIXTURE: value is retained exactly as generated in the frozen synthetic CSV; this is not a real user verification."})
    return recipes


def _adapter(case):
    recipes = _registered_fixture_answers(case)
    followup = bool(case["source"].get("warmup"))
    behavior = "stop" if case["id"] in POLICY_STOPS else "pause" if recipes else "result"
    if followup:
        behavior = "warmup_pause_followup_unassessed" if recipes else "unsupported_followup_stop"
    return {"source_commit": SOURCE_COMMIT, "policy_version": "ours-v1",
            "source_expected_behavior": case["source"]["expected_behavior"],
            "expected_primary_behavior": behavior, "fixture_answers": recipes,
            "expected_method": case["expected_method"], "source_csv_sha256": _hash(case["data_path"]),
            "source_json_sha256": _hash(case["source_path"]),
            "adaptation_note": {
                "unknown_design": "Our design check stops immediately; source answer is never invented.",
                "ambiguous_outcome": "Safely stop with target unresolved; an arbitrary outcome is a failure.",
                "regression_direction": "Safely stop with direction unresolved; an arbitrary direction is a failure.",
                "chi_square_numeric_codes": "Codes are numeric without confirmed category semantics; require clarification/new metadata, never inject gold labels.",
                "regression_too_few": "Source has four rows; ours permits identifiable regression with at least three. Expected computation is adapted, not a disabled check.",
                "welch_extreme_small_group": "Source actually contains 25 rows per group; ours asks about the IQR flag instead of a different small-sample rule."
            }.get(case["id"], "Missing cells and IQR flags pause before computation. Date filtering is unsupported. Source declarations remain frozen.")}


def load_cases(selected=None, categories=None):
    checksums_path = ADAPTED_ROOT / "source_checksums.json"
    if checksums_path.exists():
        frozen = json.loads(checksums_path.read_text(encoding="utf-8-sig"))
        if frozen.get("source_commit") != SOURCE_COMMIT or len(frozen.get("files", {})) != 63:
            raise ValueError("Source checksum declaration must identify the frozen 63-file snapshot.")
        changed = [name for name, digest in frozen["files"].items() if _hash(SOURCE_ROOT / name) != digest]
        if changed:
            raise ValueError("Frozen source files changed: " + ", ".join(changed))
    manifest = json.loads((SOURCE_ROOT / "manifest.json").read_text(encoding="utf-8-sig"))
    if len(manifest) != 31 or len({r["id"] for r in manifest}) != 31:
        raise ValueError("Frozen source catalog must contain exactly 31 unique cases.")
    known = {r["id"] for r in manifest}
    if selected and set(selected)-known:
        raise ValueError("Unknown cases: " + ", ".join(sorted(set(selected)-known)))
    if categories and set(categories)-set(GROUPS):
        raise ValueError("Unknown categories: " + ", ".join(sorted(set(categories)-set(GROUPS))))
    rows = []
    for item in manifest:
        if (selected and item["id"] not in selected) or (categories and item["category"] not in categories):
            continue
        path = SOURCE_ROOT / item["category"] / (item["id"] + ".csv")
        source_path = path.with_suffix(".json")
        source = json.loads(source_path.read_text(encoding="utf-8-sig"))
        data = pd.read_csv(path, dtype=object)
        case = {"id": item["id"], "category": item["category"], "source": source, "data": data,
                "question": source["question"], "data_path": path, "source_path": source_path,
                "expected_method": METHODS[source["plan"]["goal"]], "design_info": _design(source, data)}
        case["adapter"] = _adapter(case)
        case["expected_behavior"] = case["adapter"]["expected_primary_behavior"]
        rows.append(case)
    if not rows:
        raise ValueError("No cases selected.")
    return rows


def cases():
    return load_cases()


def supplemental_cases():
    """Our additional requests are separate from the 31 unchanged source cases."""
    recipes = [
        ("ours_ci99", "pearson_clean", "Report a 99% confidence interval for this same analysis.", "change_confidence_level", False),
        ("ours_reexplain", "regression_clean", "Explain this result more simply. Can I say x caused y?", "re_explain", False),
        ("ours_missing_ci99", "regression_missing", "Report a 99% confidence interval for this same analysis.", "change_confidence_level", False),
        ("ours_missing_reexplain", "welch_missing", "Explain the existing result more simply and describe the missing-data limitation.", "re_explain", False),
        ("ours_replaced_data_ci99", "regression_clean", "Report a 99% confidence interval for this same analysis.", "change_confidence_level", True),
    ]
    result = []
    for name, source_id, question, kind, replacement in recipes:
        case = copy.deepcopy(load_cases([source_id])[0])
        case.update(id=name, category="supplemental", source_case_id=source_id)
        case["supplemental_followup"] = {"question": question, "kind": kind,
            "replacement_recipe": "New CSV omits exactly the first frozen source row; all retained values are unchanged." if replacement else None,
            "expected_conf_level": .99 if kind == "change_confidence_level" else .95,
            "expected_data_version": "v2" if replacement else None}
        case["adapter"] = {**case["adapter"], "suite": "ours_supplemental_v1", "source_case_id": source_id,
                           "supplemental_followup": case["supplemental_followup"]}
        result.append(case)
    return result


def export_catalog(rows=None):
    """Export adapter declarations only; never regenerate or modify source bytes."""
    rows = rows or load_cases()
    for case in rows:
        _json_write(ADAPTED_ROOT / case["category"] / (case["id"] + ".json"),
                    {"id": case["id"], "category": case["category"], "design_info": case["design_info"], **case["adapter"]})
    source_paths = [SOURCE_ROOT / "manifest.json"]
    source_paths += [case[key] for case in load_cases() for key in ("data_path", "source_path")]
    _json_write(ADAPTED_ROOT / "source_checksums.json", {"source_commit": SOURCE_COMMIT,
        "files": {str(path.relative_to(SOURCE_ROOT)).replace("\\", "/"): _hash(path) for path in source_paths}})


def fixture_tool_request(case, state=None):
    """Controlled synthetic request, not a live planning input."""
    base = {"analysis_plan": adapted_plan(case), "design_info": case["design_info"],
            "data_path": str(case["data_path"]), "data_version": "v1", "excluded_ids": [], "conf_level": .95}
    base.update(state or {})
    return tool_request(base)


def build_protected_context(case, state=None, mode="offline"):
    """Safe planning input without state; protected drafting input with computed evidence."""
    if state is None:
        return {"question": case["question"], "design_info": copy.deepcopy(case["design_info"]),
                "data_path": str(case.get("runtime_data_path", case["data_path"]))}
    s = {"design_info": copy.deepcopy(case["design_info"]), "data_path": str(case["data_path"]),
         "data_version": "v1", "conf_level": .95, "excluded_ids": [], "correction_log": [],
         "stat_diagnostics": {}, "followup_focus": "", **state}
    if not s.get("stat_result") or not s.get("analysis_plan"):
        raise ValueError("Protected drafting context requires computed stat_result and an actual analysis_plan.")
    s.update(Nodes(None, None, None).build_stats_block(s, None))
    return Nodes(None, None, None)._context(s)


class PrespecifiedAgents(MockAnalysisAgentA):
    """MOCK gold planning + rule-based templates; no language-model accuracy claim."""
    model_name = "MOCK Model A: prespecified gold plans + rule-based report stand-in"

    def __init__(self, case):
        self.case = case

    def plan(self, question, design_info, columns, plan_feedback):
        return AnalysisPlan.model_validate(adapted_plan(self.case))

    def followup(self, question, previous):
        if self.case["source"].get("warmup"):
            return FollowupDecision(kind="unsupported", confidence_level=0, focus=question,
                                    rationale="Date/subset filtering is unsupported; supply a new CSV with explicit rows.")
        return super().followup(question, previous)


def live_configuration(model_a=None, model_b=None):
    """Force actual real agents. Never use auto mode or a mock fallback."""
    load_env()
    from stat_assistant.models import DEFAULT_MODEL_A, DEFAULT_MODEL_B
    return {"mode": "real", "model_a": model_a or os.getenv("MODEL_A", DEFAULT_MODEL_A),
            "model_b": model_b or os.getenv("MODEL_B", DEFAULT_MODEL_B)}


def reference(case, state=None):
    """Independent SciPy/OLS oracle on the actual version and approved exclusions."""
    state = state or {}
    plan = state.get("analysis_plan") or adapted_plan(case)
    method = plan["method"]
    data = pd.read_csv(state.get("data_path", case["data_path"]), dtype=object)
    excluded = set(state.get("excluded_ids", []))
    id_column = state.get("design_info", case["design_info"]).get("id_column")
    ids = data[id_column].astype(str) if id_column else pd.Series([f"row {i+1}" for i in range(len(data))], index=data.index)
    data = data.loc[~ids.isin(excluded)]
    columns = [plan[r] for r in METHOD_SPECS[method].roles]
    data = data[columns].dropna()
    n, conf = len(data), state.get("conf_level", .95)
    result = {"n_included": n}
    if method == "welch_t_test":
        a, b = [pd.to_numeric(data.loc[data[plan["group"]].astype(str) == label, plan["outcome"]]).to_numpy()
                for label in (plan["group_1_label"], plan["group_2_label"])]
        test = stats.ttest_ind(a, b, equal_var=False)
        interval = test.confidence_interval(confidence_level=conf)
        result.update(mean_difference=float(a.mean()-b.mean()), t_statistic=float(test.statistic), p_value=float(test.pvalue),
                      df=float(test.df), ci_lower=float(interval.low), ci_upper=float(interval.high),
                      group_1_n=len(a), group_2_n=len(b))
    elif method == "chi_square_independence":
        counts = pd.crosstab(data[plan["x"]], data[plan["y"]]).to_numpy()
        expected = counts.sum(axis=1)[:, None]*counts.sum(axis=0)[None, :]/n
        statistic = float(np.sum((counts-expected)**2/expected))
        degrees = (counts.shape[0]-1)*(counts.shape[1]-1)
        result.update(n=n, chi_square=statistic, df=degrees, p_value=float(stats.chi2.sf(statistic, degrees)),
                      cramers_v=float(np.sqrt(statistic/(n*(min(counts.shape)-1)))))
    else:
        x, y = [pd.to_numeric(data[plan[r]]).to_numpy(dtype=float) for r in ("x", "y")]
        if method == "pearson_correlation":
            test = stats.pearsonr(x, y)
            interval = test.confidence_interval(confidence_level=conf)
            r = float(test.statistic)
            result.update(n=n, r=r, t_statistic=float(r*np.sqrt((n-2)/(1-r*r))) if abs(r) < 1 else None,
                          p_value=float(test.pvalue), df=n-2, ci_lower=float(interval.low), ci_upper=float(interval.high))
        else:
            design = np.column_stack([np.ones(n), x])
            beta = np.linalg.lstsq(design, y, rcond=None)[0]
            residual = y-design@beta
            sse, degrees = float(residual@residual), n-2
            se = float(np.sqrt((sse/degrees*np.linalg.inv(design.T@design))[1, 1]))
            statistic = float(beta[1]/se)
            critical = stats.t.ppf((1+conf)/2, degrees)
            result.update(n=n, slope=float(beta[1]), intercept=float(beta[0]), slope_se=se,
                          r_squared=float(1-sse/np.sum((y-y.mean())**2)), df=degrees,
                          t_statistic=statistic, p_value=float(2*stats.t.sf(abs(statistic), degrees)),
                          ci_lower=float(beta[1]-critical*se), ci_upper=float(beta[1]+critical*se))
    return result


def _status(graph, thread_id, state):
    return "paused" if graph.get_state(config_for(thread_id)).next else state.get("final_status", "unknown")


def _snapshot(state, status):
    return sanitize({k: v for k, v in state.items() if k != "__interrupt__"} | {"observed_status": status})


def _fixture_resume(graph, thread_id, case, state, stages):
    recipes = case["adapter"]["fixture_answers"]
    for round_number in range(settings.MAX_CLARIFICATION_ROUNDS):
        if _status(graph, thread_id, state) != "paused":
            break
        answers = []
        for request in state.get("clarification_requests", []):
            recipe = next((r for r in recipes if r["record_id"] == request["record_id"]
                           and r["field"] == request["field"] and request["check"].startswith(r["check_prefix"])), None)
            if recipe is None or recipe["action"] not in request["allowed_responses"]:
                stages.append({"stage": "fixture_continuation_unassessed", "reason": "Clarification not covered by preregistered TEST FIXTURE recipe.",
                               "request": sanitize(request)})
                return state
            answers.append({"request_id": request["request_id"], "action": recipe["action"], "reason": recipe["reason"]})
        if not answers:
            break
        state = resume_answers(graph, thread_id, answers)
        stages.append({"stage": f"TEST FIXTURE continuation {round_number+1}", "label": FIXTURE_LABEL,
                       "answers": answers, "state": _snapshot(state, _status(graph, thread_id, state))})
    return state


def _numeric_checks(case, state):
    result = state.get("stat_result", {})
    if result.get("status") != "ok":
        return {"assessed": False, "passed": None, "reference": None, "fields": {}}
    actual_plan = state["analysis_plan"]
    expected_plan = adapted_plan(case)
    if actual_plan["method"] != expected_plan["method"]:
        return {"assessed": False, "passed": False, "reason": "Actual method differs from prescribed target; no oracle for a guessed target."}
    roles = METHOD_SPECS[expected_plan["method"]].roles
    if any(actual_plan[r] != expected_plan[r] for r in roles):
        return {"assessed": False, "passed": False, "reason": "Actual roles differ from prescribed target; no oracle for a guessed target."}
    if actual_plan["method"] == "welch_t_test" and (actual_plan["group_1_label"], actual_plan["group_2_label"]) != (expected_plan["group_1_label"], expected_plan["group_2_label"]):
        return {"assessed": False, "passed": False, "reason": "Welch comparison order differs from declared source reference contrast."}
    oracle = reference(case, state)
    observed = {**result, "group_1_n": result.get("group_1", {}).get("n"), "group_2_n": result.get("group_2", {}).get("n")}
    fields = {key: observed.get(key) is None if value is None else observed.get(key) is not None and
              bool(np.isclose(observed[key], value, rtol=1e-8, atol=1e-10)) for key, value in oracle.items()}
    return {"assessed": True, "passed": all(fields.values()), "reference": oracle, "fields": fields,
            "actual_data_version": state.get("data_version"), "actual_data_path": state.get("data_path"),
            "approved_excluded_ids": state.get("excluded_ids", []), "original_n": len(case["data"])}


def evaluate(case, agents=None, mode="offline", resume_fixtures=False,
             max_model_calls=settings.MAX_MODEL_CALLS_PER_REQUEST, audit_dir=None):
    """Retain first-pause evidence and optional bounded labelled fixture continuation."""
    mode = {"mock": "offline", "real": "live"}.get(mode, mode)
    if mode not in {"offline", "live"}:
        raise ValueError("mode must be offline or live")
    if mode == "offline":
        pair = agents if isinstance(agents, tuple) else (agents or PrespecifiedAgents(case), MockReviewAgentB())
    else:
        pair = agents or create_agents(live_configuration())[:2]
        if any(agent.is_mock for agent in pair):
            raise ValueError("A live benchmark cannot contain mock agents.")
    graph = build_graph(*pair)
    # Tool audit filenames contain the thread id; keep them below Windows MAX_PATH.
    thread_id = f"bench-{uuid.uuid4().hex[:16]}"
    stages, warmup = [], None
    previous_output_dir = settings.OUTPUT_DIR
    audit_dir = Path(audit_dir) if audit_dir is not None else ROOT / "artifacts" / "runtime" / "bench" / uuid.uuid4().hex[:8]
    settings.OUTPUT_DIR = audit_dir
    started = time.monotonic()
    state, primary, error = {}, {}, None
    try:
        # The source category and filename encode evaluation labels. Copy exact
        # bytes to a neutral path before any production tool/model sees the CSV.
        audit_dir.mkdir(parents=True, exist_ok=True)
        runtime_path = audit_dir / "input.csv"
        runtime_path.write_bytes(case["data_path"].read_bytes())
        if _hash(runtime_path) != case["adapter"]["source_csv_sha256"]:
            raise ValueError("The source CSV changed after preregistration.")
        runtime_case = {**case, "runtime_data_path": runtime_path}
        if case["source"].get("warmup"):
            goal = case["source"]["plan"]["goal"]
            question = "Fit simple linear regression with x as predictor and y as outcome." if goal == "regression" else "Compute Pearson correlation between x and y."
        else:
            question = case["question"]
        context = build_protected_context(runtime_case, mode=mode)
        state = new_run(graph, context["data_path"], question, context["design_info"], thread_id=thread_id,
                        max_model_calls=max_model_calls)
        primary = _snapshot(state, _status(graph, thread_id, state))
        stages.append({"stage": "warmup_primary" if case["source"].get("warmup") else "primary", "state": primary})
        if resume_fixtures:
            state = _fixture_resume(graph, thread_id, case, state, stages)
        if case["source"].get("warmup"):
            warmup = _snapshot(state, _status(graph, thread_id, state))
            if warmup["observed_status"] == "delivered":
                state = ask_followup(graph, thread_id, case["question"], max_model_calls=max_model_calls)
                stages.append({"stage": "unsupported_date_followup", "state": _snapshot(state, _status(graph, thread_id, state))})
            else:
                stages.append({"stage": "followup_unassessed", "reason": "Warmup paused or failed; no user answers were invented."})
        if case.get("supplemental_followup"):
            warmup = _snapshot(state, _status(graph, thread_id, state))
            recipe = case["supplemental_followup"]
            if warmup["observed_status"] == "delivered":
                replacement = None
                if recipe["replacement_recipe"]:
                    replacement = Path(settings.OUTPUT_DIR) / "replacement.csv"
                    replacement.parent.mkdir(parents=True, exist_ok=True)
                    case["data"].iloc[1:].to_csv(replacement, index=False)
                    stages.append({"stage": "TEST FIXTURE replacement dataset", "label": FIXTURE_LABEL,
                                   "recipe": recipe["replacement_recipe"], "path": str(replacement), "sha256": _hash(replacement)})
                state = ask_followup(graph, thread_id, recipe["question"], data_path=replacement,
                                     max_model_calls=max_model_calls)
                stages.append({"stage": "supplemental_followup_primary", "state": _snapshot(state, _status(graph, thread_id, state))})
                if resume_fixtures:
                    state = _fixture_resume(graph, thread_id, case, state, stages)
            else:
                stages.append({"stage": "supplemental_followup_unassessed", "reason": "Warmup paused or failed; required responses were not invented."})
    except Exception as exc:
        error = {"type": type(exc).__name__, "message": sanitize(str(exc))}
        state = graph.get_state(config_for(thread_id)).values or state
        if not primary:
            primary = _snapshot(state, _status(graph, thread_id, state))
    finally:
        settings.OUTPUT_DIR = previous_output_dir
    final = _snapshot(state, _status(graph, thread_id, state))
    analysis_nodes = {"plan_analysis", "prepare_data_summary", "llm_diagnostics", "stat_diagnostics", "merge_diagnostics",
                      "request_clarification", "apply_corrections", "run_statistical_test", "build_stats_block", "handle_followup"}
    analysis_errors = [e for e in final.get("errors", []) if e.get("node") in analysis_nodes]
    expected = case["expected_behavior"]
    computed_primary = primary.get("stat_result", {}).get("status") == "ok"
    safe_no_result = not computed_primary
    if expected in {"pause", "warmup_pause_followup_unassessed"}:
        safety = primary["observed_status"] == "paused" and safe_no_result and bool(primary.get("clarification_requests"))
    elif expected == "stop":
        safety = primary["observed_status"] == "stopped" and safe_no_result
    elif expected == "unsupported_followup_stop":
        safety = bool(warmup and warmup["observed_status"] == "delivered" and final["observed_status"] == "stopped")
    else:
        # A failed report review can withhold text despite correct method/math.
        safety = computed_primary
    numerical_state = warmup if case["source"].get("warmup") and warmup and warmup.get("stat_result", {}).get("status") == "ok" else final
    numeric = _numeric_checks(case, numerical_state)
    expected_plan = adapted_plan(case)
    plan = (primary.get("analysis_plan") or final.get("analysis_plan") or {})
    method_assessed = bool(plan)
    method_ok = plan.get("method") == expected_plan["method"] if method_assessed else None
    roles_ok = None
    if method_assessed and expected_plan["method"] != "no_supported_method":
        roles_ok = all(plan.get(r) == expected_plan[r] for r in METHOD_SPECS[expected_plan["method"]].roles)
        if expected_plan["method"] == "welch_t_test":
            roles_ok = roles_ok and all(plan.get(r) == expected_plan[r] for r in ("group_1_label", "group_2_label"))
    # A provider/tool crash is not evidence that a safety requirement was checked.
    if analysis_errors or error:
        safety = None
    checks = {"primary_safety_behavior": safety is True, "no_runner_exception": error is None,
              "no_core_errors": not final.get("errors", []), "analysis_execution_valid": not analysis_errors}
    if method_assessed:
        checks["method"] = bool(method_ok)
    if roles_ok is not None:
        checks["roles_and_contrast"] = bool(roles_ok)
    if numeric["passed"] is not None:
        checks["independent_numbers"] = bool(numeric["passed"])
    if case.get("supplemental_followup") and warmup and warmup["observed_status"] == "delivered":
        recipe = case["supplemental_followup"]
        checks["followup_reached_inference"] = final.get("request_number", 0) == 2 and final.get("stat_result", {}).get("status") == "ok"
        checks["followup_confidence"] = final.get("conf_level") == recipe["expected_conf_level"]
        if recipe["expected_data_version"]:
            checks["new_data_version"] = final.get("data_version") == recipe["expected_data_version"]
            checks["fresh_new_dataset_count"] = final.get("stat_result", {}).get("n") == len(case["data"])-1
        else:
            checks["same_data_version"] = final.get("data_version") == warmup.get("data_version")
            checks["same_approved_exclusions"] = final.get("excluded_ids") == warmup.get("excluded_ids")
            if recipe["kind"] == "re_explain":
                checks["unchanged_statistics"] = final.get("stat_result") == warmup.get("stat_result")
    warnings = numerical_state.get("stat_result", {}).get("regression_diagnostics", {}).get("warnings", [])
    warning_codes = [w.get("code") if isinstance(w, dict) else str(w) for w in warnings]
    warning_expected = {"regression_influential": "influential_observations", "regression_heteroscedastic": "heteroscedasticity"}.get(case["id"])
    if warning_expected and numeric["assessed"]:
        # Some tool versions expose warning strings in tool_warnings; record both.
        combined = json.dumps(numerical_state.get("stat_result", {}), default=str)
        checks["regression_warning"] = warning_expected in combined
    report_state = warmup if case["source"].get("warmup") else final
    accepted = bool(report_state and report_state.get("observed_status") == "delivered"
                    and report_state.get("program_check", {}).get("passed")
                    and report_state.get("review_verdict", {}).get("passed"))
    core_errors = final.get("errors", [])
    infrastructure = any(re.search(r"cannot record|no such file|filename.*too long|path.*too long|cannot read csv", e.get("message", ""), re.I)
                         for e in core_errors)
    failure_class = "infrastructure" if infrastructure else "runner_exception" if error else "model_or_tool_error" if core_errors else "report_gate" if numeric["assessed"] and not accepted else None
    return sanitize({"id": case["id"], "category": case["category"], "mode": mode,
        "mode_label": OFFLINE_LABEL if mode == "offline" else "REAL: actual two-model agents; one attempt with bounded internal revisions",
        "source_commit": SOURCE_COMMIT, "source_question": case["question"], "source_expected_behavior": case["source"]["expected_behavior"],
        "source_data_path": str(case["data_path"]), "source_csv_sha256": case["adapter"]["source_csv_sha256"],
        "blinding": "Exact source bytes copied to neutral hashed runtime path before any agent/tool input; source labels retained only in evaluator evidence.",
        "adapted_expectation": case["adapter"], "checks": checks, "mechanical_pass": all(checks.values()),
        "method_assessed": method_assessed, "method_pass": method_ok, "safety_assessed": safety is not None,
        "safety_pass": safety, "numeric": numeric,
        "interpretation_accepted": accepted, "semantic_review": "unlabelled: no independent human review",
        "numeric_stage": "warmup" if case["source"].get("warmup") and warmup else "final",
        "report_delivery_stage": "warmup" if case["source"].get("warmup") else "final",
        "report_delivery_status": report_state.get("observed_status") if report_state else "unassessed",
        "actual_status": final["observed_status"], "primary_state": primary, "final_state": final, "warmup": warmup,
        "stages": stages, "clarification_requested": bool(primary.get("clarification_requests")),
        "model_calls": final.get("model_calls", []), "original_diagnostics": primary.get("stat_diagnostics", {}),
        "report_revisions": report_state.get("revision_count", 0) if report_state else 0,
        "regression_warning_codes": warning_codes, "error": error, "failure_class": failure_class,
        "suite": "ours_supplemental_v1" if case.get("supplemental_followup") else "frozen_source_31",
        "runtime_audit_dir": str(audit_dir) if audit_dir else str(previous_output_dir), "duration_seconds": time.monotonic()-started})


def _failure(case, mode, error):
    return {"id": case["id"], "category": case["category"], "mode": mode, "source_commit": SOURCE_COMMIT,
            "adapted_expectation": case["adapter"], "actual_status": "runner_error", "checks": {"no_runner_exception": False},
            "mechanical_pass": False, "safety_assessed": False, "safety_pass": None,
            "numeric": {"assessed": False, "passed": None}, "interpretation_accepted": False,
            "semantic_review": "unlabelled: no independent human review", "model_calls": [],
            "error": {"type": type(error).__name__, "message": sanitize(str(error))}, "failure_class": "runner_exception",
            "primary_state": {}, "final_state": {}, "stages": []}


def runtime_audit_dir(out, case_id):
    """Short paths retain unique per-run/per-case audit files on Windows."""
    run_hash = hashlib.sha256(str(Path(out).resolve()).encode()).hexdigest()[:8]
    case_hash = hashlib.sha256(case_id.encode()).hexdigest()[:8]
    return ROOT / "artifacts" / "runtime" / "bench" / run_hash / case_hash


def _report(out, mode, rows, requested_count, resume_fixtures, configuration):
    numeric = [r for r in rows if r["numeric"]["assessed"]]
    computed = [r for r in rows if r.get("final_state", {}).get("stat_result", {}).get("status") == "ok" or
                (r.get("warmup") or {}).get("stat_result", {}).get("status") == "ok"]
    summary = {"mode": mode, "mode_label": OFFLINE_LABEL if mode == "offline" else "REAL actual agents",
               "source_commit": SOURCE_COMMIT, "configuration": configuration, "resume_fixtures": resume_fixtures,
               "selected_case_count": requested_count, "completed_case_count": len(rows), "cases": rows,
               "counts": {"mechanical_pass": sum(r["mechanical_pass"] for r in rows), "numeric_assessed": len(numeric),
                          "safety_assessed": sum(r.get("safety_assessed", False) for r in rows),
                          "safety_unassessed": sum(not r.get("safety_assessed", False) for r in rows),
                          "infrastructure_failures": sum(r.get("failure_class") == "infrastructure" for r in rows),
                          "numeric_pass": sum(r["numeric"]["passed"] for r in numeric), "computed_results": len(computed),
                          "reports_accepted_by_code_and_model_b": sum(r["interpretation_accepted"] for r in rows)}}
    _json_write(out / "results.json", summary)
    lines = ["# Adapted frozen four-method benchmark", "", summary["mode_label"], "",
             f"Source snapshot: `{SOURCE_COMMIT}`. Completed {len(rows)}/{requested_count} selected cases.",
             f"Mechanical method/safety/numeric checks: {summary['counts']['mechanical_pass']}/{len(rows)}.",
             f"Independent numerical checks: {summary['counts']['numeric_pass']}/{len(numeric)} assessed computed cases.",
             f"Reports delivered after program checks and Model B: {summary['counts']['reports_accepted_by_code_and_model_b']}/{len(computed)} computed cases.", "",
             "Code acceptance and Model B review are not independent human semantic accuracy. Human labels remain blank.",
             "Primary pauses are retained. Optional secondary answers are explicitly TEST FIXTURE synthetic recipes, not user decisions.",
             "No training, mock fallback, cherry picking, or copying of teammate scores is performed.", "",
             "| Category | Case | Primary status | Final status | Failed mechanical checks | Report accepted (stage) |",
             "|---|---|---|---|---|---|"]
    lines += [f"| {r['category']} | {r['id']} | {r.get('primary_state',{}).get('observed_status','runner_error')} | {r['actual_status']} | {', '.join(k for k,v in r['checks'].items() if not v) or 'none'} | {r['interpretation_accepted']} ({r.get('report_delivery_stage','unassessed')}) |" for r in rows]
    (out / "REPORT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    with (out / "human_review.csv").open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=["case_id", "category", "mode", "report_stage", "report_sha256", "frozen_report_file",
                                                  "human_method_label", "human_numeric_label", "human_semantic_label", "human_notes", "reviewer", "review_date"])
        writer.writeheader()
        for row in rows:
            use_warmup = bool(row.get("warmup")) and row.get("suite") != "ours_supplemental_v1"
            state = row.get("warmup") if use_warmup else row.get("final_state", {})
            text = (state or {}).get("final_report", "")
            report_stage = "warmup" if use_warmup else "final"
            if not row["interpretation_accepted"]:
                rendered = (state or {}).get("rendered_draft", {})
                text = rendered.get("interpretation", "")
                if text:
                    text += "\n\nLimitations:\n" + "\n".join(l["text"] for l in rendered.get("limitations", []))
                    report_stage += "_withheld_draft"
            if not text:
                continue
            relative = Path(row["category"]) / (row["id"] + ".report.txt")
            report_file = out / relative
            report_file.write_text(text, encoding="utf-8")
            writer.writerow({"case_id": row["id"], "category": row["category"], "mode": mode,
                             "report_stage": report_stage, "report_sha256": _hash(report_file),
                             "frozen_report_file": str(relative).replace("\\", "/")})
    return summary


def run(mode="offline", selected=None, categories=None, prefix=None, export_only=False,
        resume_fixtures=False, max_model_calls=settings.MAX_MODEL_CALLS_PER_REQUEST, stop_after=None,
        model_a=None, model_b=None, output_root=None, supplemental=False):
    mode = {"mock": "offline", "real": "live"}.get(mode, mode)
    if mode not in {"offline", "live"}:
        raise ValueError("mode must be offline or live")
    if isinstance(max_model_calls, bool) or not isinstance(max_model_calls, int) or max_model_calls < 1:
        raise ValueError("max_model_calls must be a positive integer")
    if stop_after is not None and (isinstance(stop_after, bool) or stop_after < 1):
        raise ValueError("stop_after must be positive")
    chosen = supplemental_cases() if supplemental else load_cases(selected, categories)
    if supplemental and (selected or categories):
        raise ValueError("Supplemental suite runs separately from source --case/--category selection.")
    if export_only:
        export_catalog(load_cases())
        return {"exported_case_count": 31, "source_commit": SOURCE_COMMIT, "llm_calls": 0}
    prefix = prefix or f"{mode}_{'supplemental' if supplemental else 'v2'}_{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}_{uuid.uuid4().hex[:6]}"
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,100}", prefix):
        raise ValueError("Output name must be a simple alphanumeric filename")
    out = Path(output_root or ROOT / "artifacts" / "benchmark_v2") / prefix
    if out.exists():
        raise ValueError("Output directory exists; choose a new --output to preserve evidence.")
    out.mkdir(parents=True)
    configuration = live_configuration(model_a, model_b) if mode == "live" else {"mode": "mock", "label": OFFLINE_LABEL}
    _json_write(out / "preregistered_cases.json", {"source_commit": SOURCE_COMMIT, "cases": [{"id": c["id"], "category": c["category"],
                "design_info": c["design_info"], "adapter": c["adapter"]} for c in chosen], "configuration": configuration})
    pair, initialization_error = None, None
    if mode == "live":
        try:
            pair = create_agents(configuration)[:2]
        except Exception as exc:
            initialization_error = exc
    rows = []
    _report(out, mode, rows, len(chosen), resume_fixtures, configuration)
    for case in chosen[:stop_after]:
        try:
            if initialization_error is not None:
                raise initialization_error
            row = evaluate(case, agents=pair, mode=mode, resume_fixtures=resume_fixtures,
                           max_model_calls=max_model_calls, audit_dir=runtime_audit_dir(out, case["id"]))
        except Exception as exc:
            row = _failure(case, mode, exc)
        rows.append(row)
        _json_write(out / case["category"] / (case["id"] + ".json"), row)
        summary = _report(out, mode, rows, len(chosen), resume_fixtures, configuration)
        print(case["id"], row["actual_status"], "PASS" if row["mechanical_pass"] else "FAIL", flush=True)
    print(f"Evidence: {out}", flush=True)
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=["offline", "live", "mock", "real"], default="offline")
    parser.add_argument("--case", action="append")
    parser.add_argument("--category", choices=GROUPS, action="append")
    parser.add_argument("--output", help="New evidence directory name; existing directories are rejected")
    parser.add_argument("--export-only", action="store_true", help="Freeze adapter declarations; no LLM creation/calls")
    parser.add_argument("--list", action="store_true")
    parser.add_argument("--resume-fixtures", action="store_true", help="Bounded labelled synthetic secondary continuation; primary pause remains recorded")
    parser.add_argument("--max-model-calls", type=int, default=settings.MAX_MODEL_CALLS_PER_REQUEST)
    parser.add_argument("--stop-after", type=int)
    parser.add_argument("--supplemental", action="store_true", help="Run our five extra followup cases separately; source suite stays 31")
    parser.add_argument("--model-a")
    parser.add_argument("--model-b")
    args = parser.parse_args()
    if args.list:
        for case in supplemental_cases() if args.supplemental else load_cases(args.case, args.category):
            print(case["category"], case["id"], case["expected_behavior"])
        return
    run(args.mode, args.case, args.category, args.output, args.export_only, args.resume_fixtures,
        args.max_model_calls, args.stop_after, args.model_a, args.model_b, supplemental=args.supplemental)


if __name__ == "__main__":
    main()
