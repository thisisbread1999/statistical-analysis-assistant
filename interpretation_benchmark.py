"""Controlled interpretation challenges; fixture labels are not human accuracy ratings.

The challenge categories were adapted from teammate commit b7eff1c. Statistics,
drafts, program checks and reviewer verdicts are regenerated with this project.
No source implementation or source detector scores are imported.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import time
import uuid

from benchmark_suite import (adapted_plan, build_protected_context,
                             fixture_tool_request, load_cases)
from stat_assistant import models
from stat_assistant.agents import MockAnalysisAgentA, MockReviewAgentB
from stat_assistant.report import check_report, format_stats_block, render
from stat_assistant.schemas import ReportDraft, ReviewVerdict
from stat_assistant.tools import execute

ROOT = Path(__file__).resolve().parent
FIXTURE_DIR = ROOT / "examples" / "interpretation_checks"
OUTPUT_ROOT = ROOT / "artifacts" / "interpretation_checks"
PROVENANCE = {
    "source_commit": "b7eff1c",
    "source_file": "interpretation_benchmark.py",
    "adaptation": "Challenge categories and authored mutations adapted to this project's ReportDraft and Python tools.",
    "label_kind": "authored fixture expectation; not human review",
    "draft_origin": "MockAnalysisAgentA controlled template, with an optional authored mutation",
}


def _json_write(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")


def challenge_specs(selected: list[str] | None = None) -> list[dict]:
    """Load authored inputs only; no results from the teammate's runner are used."""
    paths = sorted(FIXTURE_DIR.glob("valid/*.json")) + sorted(FIXTURE_DIR.glob("planted_errors/*.json"))
    specs = [json.loads(path.read_text(encoding="utf-8")) for path in paths]
    ids = [spec["id"] for spec in specs]
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate interpretation challenge ids.")
    if selected:
        missing = set(selected) - set(ids)
        if missing:
            raise ValueError(f"Unknown interpretation challenge(s): {sorted(missing)}")
        specs = [spec for spec in specs if spec["id"] in set(selected)]
    if not specs:
        raise ValueError("No interpretation challenges found.")
    return specs


def _source_context(case: dict) -> dict:
    """Build evidence for a controlled template, without Model A or graph routing.

    The statistical tool still enforces its record and method requirements. Its
    non-blocking verification flags are retained as evidence; this controlled
    test does not pretend that a person reviewed or verified these records.
    """
    request = fixture_tool_request(case)
    diagnostics = execute("diagnostics", request)
    result = execute("run_test", request)
    if diagnostics.get("status") != "ok" or result.get("status") != "ok":
        raise ValueError(f"Controlled source fixture did not produce usable statistics: {result}")
    state = {
        "analysis_plan": adapted_plan(case), "stat_result": result,
        "stat_diagnostics": diagnostics, "conf_level": request["conf_level"],
        "excluded_ids": [], "correction_log": [],
    }
    context = build_protected_context(case, state=state, mode="offline")
    block = {key: deepcopy(context[key]) for key in (
        "method", "method_label", "data_version", "tool_call", "values", "hypotheses",
        "required_placeholders", "required_limitations", "direction", "decision",
        "distribution_checks", "observed", "yates", "tool_warnings", "t_statistic_note",
    ) if key in context}
    base = ReportDraft.model_validate(MockAnalysisAgentA().draft(context)).model_dump()
    base["version"] = "v1"
    return {
        "question": case["source"]["question"], "source_case": case["id"],
        "analysis_plan": deepcopy(context["analysis_plan"]),
        "design_info": deepcopy(context["design_info"]),
        "stat_result": deepcopy(result), "stat_diagnostics": deepcopy(diagnostics),
        "statistical_request": deepcopy(request), "stats_block": block,
        "correction_log": [], "original_draft": base,
        "controlled_execution": {
            "scope": "Interpretation template test; not an end-to-end run or clarification-policy test.",
            "record_verification": "No human record verification was performed or fabricated.",
            "verification_flags_retained": diagnostics.get("n_verify", 0),
        },
    }


def prepare_challenge(spec: dict, sources: dict[str, dict], cache: dict | None = None) -> dict:
    """Apply exactly the declared authored mutation to an original draft."""
    cache = cache if cache is not None else {}
    source_id = spec["source_case"]
    if source_id not in cache:
        cache[source_id] = _source_context(sources[source_id])
    evidence = deepcopy(cache[source_id])
    draft = deepcopy(evidence["original_draft"])
    mutation = spec["mutation"]
    append_text = {
        "causal": " This analysis causes improvement.",
        "wrong_method": " This is Pearson correlation.",
        "percent_misinterpretation": " This means the outcome increases by eighty percent.",
        "interval_probability": " The fixed true slope has a ninety-five percent probability of lying inside this observed interval.",
        "nonlinear_no_relationship": " There is no relationship between these variables.",
    }
    if mutation == "wrong_number":
        if "{p_value}" not in draft["interpretation"]:
            raise ValueError("Original template does not contain the p_value placeholder.")
        draft["interpretation"] = draft["interpretation"].replace("{p_value}", "0.123", 1)
    elif mutation in append_text:
        draft["interpretation"] += append_text[mutation]
    elif mutation != "none":
        raise ValueError(f"Unknown authored mutation: {mutation}")
    # Report metadata must not reveal the authored validity/mutation label to B.
    # Challenge identity belongs only to the evaluator's enclosing case record.
    draft["version"] = "v1"
    # Validation is about this project's exchange schema, not the expectation label.
    ReportDraft.model_validate(draft)
    return {**deepcopy(spec), **evidence, "provenance": deepcopy(PROVENANCE), "draft": draft}


def challenges(selected: list[str] | None = None) -> list[dict]:
    specs = challenge_specs(selected)
    sources = {case["id"]: case for case in load_cases(selected=sorted({s["source_case"] for s in specs}))}
    cache: dict = {}
    return [prepare_challenge(spec, sources, cache) for spec in specs]


def review_payload(row: dict) -> dict:
    """Project original evidence without fixture identity, labels or checker results."""
    values = row["stats_block"]["values"]
    rendered = {**deepcopy(row["draft"]), "interpretation": render(row["draft"]["interpretation"], values),
                "limitations": [{**limitation, "text": render(limitation["text"], values)}
                                for limitation in row["draft"]["limitations"]]}
    # The source filename includes fixture names such as pearson_nonlinear.
    # Its filesystem provenance remains in the evaluator's original stat_result;
    # omit this metadata from B's projection without changing any statistics.
    original_statistics = deepcopy(row["stat_result"])
    original_statistics.pop("data_path", None)
    return {
        "report_draft": rendered, "stat_result": original_statistics,
        "protected_statistics": deepcopy(row["stats_block"]),
        "analysis_plan": deepcopy(row["analysis_plan"]), "design_info": deepcopy(row["design_info"]),
        "correction_log": deepcopy(row["correction_log"]),
        "required_limitations": deepcopy(row["stats_block"]["required_limitations"]),
    }


def _unassessed(error: Exception | str) -> dict:
    return {"status": "unassessed", "accepted": None, "error": str(error)}


def evaluate_challenge(row: dict, reviewer=None, reviewer_error: str | None = None) -> dict:
    """Check both detectors independently, even when the program rejects a draft."""
    evaluated = deepcopy(row)
    payload = review_payload(row)
    evaluated["review_evidence"] = deepcopy(payload)
    evaluated["rendered_draft"] = deepcopy(payload["report_draft"])
    try:
        check = check_report(deepcopy(row["stats_block"]), deepcopy(row["draft"]))
        code = {"status": "assessed", "accepted": check["passed"], "check": check}
    except Exception as error:
        code = _unassessed(error)
    # Reviewer sees only original statistical evidence and rendered draft, with
    # neither expectation labels nor code feedback to steer its verdict.
    if reviewer is None:
        review = _unassessed(reviewer_error or "Reviewer was not initialized.")
    else:
        started = time.monotonic()
        try:
            raw = ReviewVerdict.model_validate(reviewer.review(deepcopy(payload))).model_dump()
            if raw["passed"] is False and not raw["issues"]:
                raise ValueError("Reviewer returned passed=false without issues; verdict is unassessed.")
            verdict = deepcopy(raw)
            # Production defines critical issues as failure; minor suggestions
            # cannot change acceptance.
            verdict["passed"] = not any(i["severity"] == "critical" for i in verdict["issues"])
            review = {"status": "assessed", "accepted": verdict["passed"],
                      "raw_verdict": raw, "verdict": verdict}
        except Exception as error:
            review = _unassessed(error)
        review["elapsed_seconds"] = round(time.monotonic() - started, 3)
    combined = ({"status": "assessed", "accepted": code["accepted"] and review["accepted"]}
                if code["status"] == review["status"] == "assessed"
                else _unassessed("Both detectors must complete before combined acceptance is scored."))
    evaluated["detectors"] = {"program": code, "reviewer_b": review, "combined": combined}
    return evaluated


def score(records: list[dict]) -> dict:
    """Count fixture coverage, keeping unassessed results out of caught/missed."""
    totals = {}
    for detector in ("program", "reviewer_b", "combined"):
        counts = {"valid_total": 0, "valid_accepted": 0, "valid_false_alarms": 0, "valid_unassessed": 0,
                  "planted_total": 0, "planted_caught": 0, "planted_missed": 0, "planted_unassessed": 0}
        for row in records:
            valid = row["expected_valid"]
            prefix = "valid" if valid else "planted"
            counts[prefix + "_total"] += 1
            result = row["detectors"][detector]
            if result["status"] != "assessed" or result["accepted"] is None:
                counts[prefix + "_unassessed"] += 1
            elif valid:
                counts["valid_accepted" if result["accepted"] else "valid_false_alarms"] += 1
            else:
                counts["planted_missed" if result["accepted"] else "planted_caught"] += 1
        totals[detector] = counts
    return totals


def _report(records: list[dict], metadata: dict) -> str:
    counts = score(records)
    lines = ["# Interpretation challenge evaluation", "", metadata["evaluation_scope"], "",
             f"Mode: {metadata['mode']}. Reviewer: {metadata['reviewer_model']}.", "",
             "All labels are authored test expectations. These counts are detector coverage on controlled drafts, not human semantic ratings or an error rate for real Model A outputs.", "",
             "| Detector | Valid accepted | Valid false alarms | Valid unassessed | Planted caught | Planted missed | Planted unassessed |",
             "|---|---:|---:|---:|---:|---:|---:|"]
    for name, c in counts.items():
        lines.append(f"| {name} | {c['valid_accepted']}/{c['valid_total']} | {c['valid_false_alarms']} | {c['valid_unassessed']} | {c['planted_caught']}/{c['planted_total']} | {c['planted_missed']} | {c['planted_unassessed']} |")
    lines += ["", "Combined acceptance requires both detectors to accept. A detector error produces an unassessed result and receives no detection credit.", "",
              "| Challenge | Expected valid | Program accepts | Reviewer B accepts | Combined accepts | Note |",
              "|---|---|---|---|---|---|"]
    for row in records:
        cells = [str(row["detectors"][name]["accepted"]) if row["detectors"][name]["status"] == "assessed" else "unassessed"
                 for name in ("program", "reviewer_b", "combined")]
        lines.append(f"| {row['id']} | {row['expected_valid']} | {' | '.join(cells)} | {row['note'].replace('|', '/')} |")
    lines += ["", "Per-case JSON retains the original Python results, protected statistics, original template, mutation, rendered reviewer evidence, checks and verdicts. Non-blocking verification flags are retained; no human verification is claimed.",
              "", "Challenge categories were adapted from teammate commit b7eff1c. This project recomputed all results; source scores were not imported."]
    return "\n".join(lines) + "\n"


def make_reviewer(mode: str):
    if mode == "offline":
        return MockReviewAgentB(), {"mode": "offline", "model_b": MockReviewAgentB.model_name}
    if mode != "live":
        raise ValueError("mode must be offline or live")
    models.load_env()
    configuration = {"mode": "real", "model_a": os.getenv("MODEL_A", models.DEFAULT_MODEL_A),
                     "model_b": os.getenv("MODEL_B", models.DEFAULT_MODEL_B)}
    # Use production model configuration and distinct-model checks. The returned
    # real Model A is never invoked; only Model B reviews controlled drafts.
    _, reviewer, configuration = models.create_agents(configuration)
    return reviewer, configuration


def run(mode: str = "offline", selected: list[str] | None = None, name: str | None = None,
        output_root: Path | None = None, reviewer=None) -> Path:
    specs = challenge_specs(selected)
    if name is None:
        name = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "_" + mode + "_" + uuid.uuid4().hex[:8]
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", name) or name in {".", ".."}:
        raise ValueError("Run name must be a single directory name using letters, digits, dots, hyphens or underscores.")
    directory = Path(output_root or OUTPUT_ROOT) / name
    directory.mkdir(parents=True, exist_ok=False)
    metadata = {"run_name": name, "mode": mode, "started_utc": datetime.now(timezone.utc).isoformat(),
                "reviewer_model": getattr(reviewer, "model_name", "not initialized"),
                "evaluation_scope": "Four valid controlled templates and twelve authored mutations; Python statistics are real. Model A is not called.",
                "provenance": PROVENANCE, "requested_cases": [spec["id"] for spec in specs],
                "review_evidence_blinded": True,
                "blinding": "Neutral report version; fixture id, labels and source filename are kept only in evaluator artifacts."}
    initialization_error = None
    if reviewer is None:
        try:
            reviewer, configuration = make_reviewer(mode)
            metadata["configuration"] = configuration
            metadata["reviewer_model"] = reviewer.model_name
        except Exception as error:
            initialization_error = str(error)
            metadata["reviewer_initialization_error"] = initialization_error
    records = []
    source_error = None
    try:
        sources = {case["id"]: case for case in load_cases(selected=sorted({s["source_case"] for s in specs}))}
    except Exception as error:
        sources, source_error = {}, error
    cache: dict = {}
    for spec in specs:
        try:
            if source_error is not None:
                raise source_error
            row = prepare_challenge(spec, sources, cache)
            row = evaluate_challenge(row, reviewer, initialization_error)
        except Exception as error:
            row = {**deepcopy(spec), "provenance": deepcopy(PROVENANCE), "preparation_error": str(error),
                   "detectors": {key: _unassessed(error) for key in ("program", "reviewer_b", "combined")}}
        records.append(row)
        _json_write(directory / (spec["id"] + ".json"), row)
        # Persist after every case so a later model/tool failure cannot erase
        # completed evidence or leave only an aggregate success claim.
        _json_write(directory / "results.json", {"metadata": metadata, "completed_cases": len(records),
                    "summary": score(records), "cases": [{"id": r["id"], "expected_valid": r["expected_valid"],
                    "detectors": r["detectors"]} for r in records]})
        (directory / "REPORT.md").write_text(_report(records, metadata), encoding="utf-8")
        print(f"{spec['id']}: " + ", ".join(f"{key}={value['accepted'] if value['status'] == 'assessed' else 'unassessed'}"
                                          for key, value in row["detectors"].items()), flush=True)
    return directory


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("offline", "live"), default="offline")
    parser.add_argument("--case", action="append", dest="selected", help="Challenge id; repeat to select several.")
    parser.add_argument("--name", help="Unique run directory name; existing directories are never overwritten.")
    args = parser.parse_args()
    directory = run(args.mode, args.selected, args.name)
    print(f"Saved interpretation evidence: {directory}")


if __name__ == "__main__":
    main()
