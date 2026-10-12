"""
Automated checks of the LangGraph workflow's control flow.

Run from the project folder:   python tests/run_checks.py

How it works: the script loads the code cells tagged "graph-definition" and "run-helpers"
directly from stats_assistant_graph.ipynb, so it tests exactly the graph defined in the
notebook (not a copy). Diagram and example cells are not executed.

Every scripted user answer and every injected report error below is a TEST INPUT. Scripted
answers stand in for a person typing in the notebook; they test the routing only. In mock mode
both agents are rule-based stand-ins, so passing these checks says nothing about how real
models behave.
"""
import hashlib
import json
import os
import sys
import traceback
from pathlib import Path

import nbformat

PROJECT_DIR = Path(__file__).resolve().parents[1]
os.chdir(PROJECT_DIR)
os.environ["LLM_MODE"] = "mock"          # these checks always use the rule-based stand-ins

nb = nbformat.read(PROJECT_DIR / "stats_assistant_graph.ipynb", as_version=4)
ns: dict = {}
for cell in nb.cells:
    tags = cell.metadata.get("tags", [])
    if cell.cell_type == "code" and ("graph-definition" in tags or "run-helpers" in tags):
        exec(compile(cell.source, f"<notebook cell {cell.get('id', '?')}>", "exec"), ns)

graph, Command, new_run = ns["graph"], ns["Command"], ns["new_run"]
DATA_DIR, OUTPUT_DIR = ns["DATA_DIR"], ns["OUTPUT_DIR"]
CLEAN = DATA_DIR / "tutoring_scores_clean_synthetic.csv"
MESSY = DATA_DIR / "tutoring_scores_messy_synthetic.csv"
print(f"LLM_MODE = {ns['LLM_MODE']}; Model A = {ns['AGENT_A'].model_name}; Model B = {ns['AGENT_B'].model_name}\n")

RESULTS = []


def check(name):
    def wrap(fn):
        try:
            fn()
            RESULTS.append((name, "PASS", ""))
        except Exception as err:          # report every failure, keep going
            RESULTS.append((name, "FAIL", f"{type(err).__name__}: {err}"))
            traceback.print_exc()
        return fn
    return wrap


def nodes_run(result):
    return [t["node"] for t in result["trace"]]


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def answers_for(requests, rules):
    """TEST INPUT: build scripted answers {request_id: {response, reason}} from simple rules."""
    out = {}
    for r in requests:
        response, reason = rules(r)
        out[r["request_id"]] = {"response": response, "reason": reason}
    return out


def case_study_answers(r):
    """TEST INPUT transcribed from the case-study scenario (Step 3); extra boxplot flags kept as genuine."""
    if r["check"] == "missing_score":
        return "exclude", "TEST INPUT: score cannot be recovered; user agrees to complete-case analysis"
    if r["check"] == "out_of_range":
        return "85", "TEST INPUT: entry error, 850 should be 85"
    if r["check"] == "invalid_label":
        return "yes", "TEST INPUT: trailing space; label means yes"
    if r["check"] == "boxplot_flag":
        return "keep", "TEST INPUT: score verified as genuine"
    return "stop", ""


# ---------------------------------------------------------------------------
@check("graph structure: 16 real nodes, join edge, both conditional routers and their labels")
def _():
    g = graph.get_graph()
    nodes = {n for n in g.nodes if not n.startswith("__")}
    assert nodes == set(ns["NODE_ROLES"]) and len(nodes) == 16, nodes
    mermaid = g.draw_mermaid()
    for label in ["needs_clarification", "proceed", "stop", "review_passed", "revise_once", "fail_after_revision"]:
        assert f"&nbsp;{label}&nbsp;" in mermaid, label
    # The join is a single waiting edge with both sources (stored by StateGraph as waiting_edges).
    assert (("llm_diagnostics", "r_diagnostics"), "merge_diagnostics") in ns["builder"].waiting_edges


@check("normal path (clean data): parallel diagnostics -> proceed -> R test -> review passes -> delivered")
def _():
    state, config = new_run("check-clean", CLEAN)
    result = graph.invoke(state, config)
    path = nodes_run(result)
    assert result["final_status"] == "delivered", result["final_status"]
    assert "request_clarification" not in path and "revise_report" not in path
    assert path[-1] == "save_session" and Path(result["session_record_path"]).exists()
    # Parallel: both branches in the same superstep, same data version
    diag = [t for t in result["trace"] if t["node"] in ("llm_diagnostics", "r_diagnostics")]
    assert len(diag) == 2 and diag[0]["step"] == diag[1]["step"], diag
    assert {t["data_version"] for t in diag} == {"v1"}
    # Statistics come from R and are only formatted by the program
    r, sb = result["r_results"], result["stats_block"]
    assert sb["t_statistic"] == f"{r['t_statistic']:.3f}" and sb["df"] == f"{r['df']:.2f}"
    assert result["numeric_check"]["passed"] and result["review"]["passed"]
    assert "R version" in r["r_version"]


@check("normal path, no significant difference: delivered with 'do not reject H0' and the correct direction")
def _():
    state, config = new_run("check-no-difference", DATA_DIR / "tutoring_scores_no_difference_synthetic.csv")
    result = graph.invoke(state, config)
    sb, r = result["stats_block"], result["r_results"]
    assert result["final_status"] == "delivered"
    assert r["p_value"] >= ns["ALPHA"] and sb["decision"] == "do_not_reject_H0"
    expected = "tutoring_group_lower" if r["mean_difference"] < 0 else "tutoring_group_higher"
    assert result["report_draft"]["direction_claim"] == expected


@check("normal path, unequal group sizes and variances: delivered; Welch df is not the pooled n1+n2-2")
def _():
    state, config = new_run("check-unequal", DATA_DIR / "tutoring_scores_unequal_variance_synthetic.csv")
    result = graph.invoke(state, config)
    r = result["r_results"]
    assert result["final_status"] == "delivered"
    assert (r["group_1"]["n"], r["group_2"]["n"]) == (30, 50)
    assert r["var_equal"] is False and abs(r["df"] - 78) > 1, r["df"]


@check("checkpoint history shows both diagnostic branches scheduled in ONE superstep")
def _():
    state, config = new_run("check-superstep", CLEAN)
    graph.invoke(state, config)
    nexts = [tuple(s.next) for s in graph.get_state_history(config)]
    assert ("llm_diagnostics", "r_diagnostics") in nexts, nexts


@check("data problems -> pause BEFORE any test; resume with TEST INPUT answers -> new version -> recheck -> delivered")
def _():
    before = sha256(MESSY)
    state, config = new_run("check-messy", MESSY)
    result = graph.invoke(state, config)
    assert "__interrupt__" in result, "graph did not pause"
    assert "r_results" not in result, "a test was run before clarification"
    assert graph.get_state(config).next == ("request_clarification",)
    requests = result["__interrupt__"][0].value["requests"]
    flagged = {(r["record_id"], r["check"]) for r in requests}
    for expected in [("S001", "missing_score"), ("S041", "missing_score"), ("S006", "out_of_range"),
                     ("S015", "invalid_label"), ("S065", "boxplot_flag")]:
        assert expected in flagged, (expected, flagged)
    rounds = 0
    while "__interrupt__" in result:
        rounds += 1
        reqs = result["__interrupt__"][0].value["requests"]
        result = graph.invoke(Command(resume=answers_for(reqs, case_study_answers)), config)
    assert result["final_status"] == "delivered", result.get("final_report")
    assert sha256(MESSY) == before, "original file was modified"
    assert result["excluded_ids"] == ["S001", "S041"]
    assert "S065" in result["verified_ids"]
    log = {(e["record_id"], e["action"]) for e in result["correction_log"]}
    assert {("S006", "set_score"), ("S015", "set_label"), ("S001", "exclude"), ("S041", "exclude"),
            ("S065", "keep")} <= log
    assert all(e["reason"] and e["source"] == "user confirmation" for e in result["correction_log"])
    import pandas as pd
    v = pd.read_csv(result["data_path"], dtype=str, keep_default_na=False).set_index("student_id")
    assert v.loc["S006", "score"] == "85" and v.loc["S015", "tutoring"] == "yes"
    assert v.loc["S001", "score"] == "", "missing score was imputed"
    g1, g2 = result["r_results"]["group_1"], result["r_results"]["group_2"]
    assert (g1["n"], g2["n"]) == (39, 39), (g1["n"], g2["n"])
    # Diagnostics were re-run on the new data version (two rounds of both branches)
    versions = [t["data_version"] for t in result["trace"] if t["node"] == "r_diagnostics"]
    assert versions[0] == "v1" and versions[-1] == result["data_version"] != "v1", versions
    lims = result["stats_block"]["required_limitations"]
    assert "excluded_missing_scores" in lims and "excluded_flagged_records" not in lims, lims
    assert "complete-case" in result["report_draft"]["interpretation"]
    print("    path:", " -> ".join(nodes_run(result)))
    print(f"    clarification rounds used: {rounds}; final data version {result['data_version']}; "
          f"n = {g1['n']}/{g2['n']}; t = {result['stats_block']['t_statistic']}, p = {result['stats_block']['p_value']}")


@check("user answers 'stop' (TEST INPUT) -> stop at diagnostics, no test run")
def _():
    state, config = new_run("check-user-stop", MESSY)
    result = graph.invoke(state, config)
    reqs = result["__interrupt__"][0].value["requests"]
    result = graph.invoke(Command(resume=answers_for(reqs, lambda r: ("stop", ""))), config)
    assert result["final_status"] == "stopped_at_diagnostics"
    assert "r_results" not in result
    assert any("stop" in s for s in result["diagnostic_decision"]["stop_reasons"])


@check("invalid answers (TEST INPUT) are rejected, re-asked, then stop after the clarification round limit")
def _():
    state, config = new_run("check-invalid-answers", MESSY)
    result = graph.invoke(state, config)
    pauses = 0
    while "__interrupt__" in result:
        pauses += 1
        reqs = result["__interrupt__"][0].value["requests"]
        result = graph.invoke(Command(resume=answers_for(reqs, lambda r: ("850", ""))), config)  # no reason, bad value
        assert pauses <= ns["MAX_CLARIFICATION_ROUNDS"]
    assert pauses == ns["MAX_CLARIFICATION_ROUNDS"], pauses
    assert result["final_status"] == "stopped_at_diagnostics"
    assert all(len(c["accepted"]) == 0 for c in result["user_confirmations"])
    assert "r_results" not in result


@check("missing required column (TEST INPUT file) -> stop at diagnostics without pausing")
def _():
    import pandas as pd
    f = OUTPUT_DIR / "check_input_no_tutoring_column_synthetic.csv"
    pd.read_csv(CLEAN, dtype=str).drop(columns="tutoring").to_csv(f, index=False)
    state, config = new_run("check-missing-column", f)
    result = graph.invoke(state, config)
    assert "__interrupt__" not in result
    assert result["final_status"] == "stopped_at_diagnostics"
    assert "tutoring" in " ".join(result["diagnostic_decision"]["stop_reasons"])


@check("review fails once (TEST INPUT causal sentence) -> one revision -> passes -> delivered")
def _():
    state, config = new_run("check-causal", CLEAN, test_fault={"type": "causal_claim", "apply_to": "first_draft"})
    result = graph.invoke(state, config)
    path = nodes_run(result)
    assert result["final_status"] == "delivered"
    assert result["revision_count"] == 1 and path.count("review_report") == 2 and path.count("revise_report") == 1
    first, second = result["review_history"]
    assert not first["passed"] and any(i["category"] == "causal_claim" for i in first["issues"])
    assert second["passed"]


@check("review fails again after the one revision (TEST INPUT wrong number) -> stop, at most one revision")
def _():
    state, config = new_run("check-persistent", CLEAN, test_fault={"type": "wrong_number", "apply_to": "all_drafts"})
    result = graph.invoke(state, config)
    path = nodes_run(result)
    assert result["final_status"] == "stopped_after_review"
    assert result["revision_count"] == 1 and path.count("revise_report") == 1 and path.count("review_report") == 2
    assert all(not rv["numeric_check_passed"] for rv in result["review_history"])
    assert "withheld" in result["final_report"] and "p =" not in result["final_report"]


@check("numeric check catches rounding, sign, field, invented-number, direction and decision errors")
def _():
    state, config = new_run("check-numeric", CLEAN)
    result = graph.invoke(state, config)
    sb, good = result["stats_block"], result["report_draft"]
    check_fn = ns["check_report_numbers"]
    assert check_fn({"stats_block": sb, "report_draft": good})["numeric_check"]["passed"]
    cases = {
        "rounding": {"interpretation": f"The difference was {float(sb['mean_difference']):.1f} points."},
        "sign": {"interpretation": f"The difference was -{sb['mean_difference']} points."},
        "unverified_number": {"interpretation": "The mean difference was 2 points."},
        "field_mismatch": {"reported_statistics": {**good["reported_statistics"], "p_value": "0.05"}},
        "direction": {"direction_claim": "tutoring_group_lower"},
        "decision": {"decision_claim": "do_not_reject_H0" if sb["decision"] == "reject_H0" else "reject_H0"},
        "missing_content": {"interpretation": "Students who attended tutoring scored higher; we reject H0."},
        "decision_wording": {"interpretation": good["interpretation"].replace("we reject H0", "we do not reject H0")},
        "required_sections": {"limitations": good["limitations"] + [{"limitation_id": "normality",
                              "text": "A non-parametric test may be more appropriate."}]},
    }
    numbered = {**good, "interpretation": "1. " + good["interpretation"].replace(". For H0", ". 2. For H0")}
    assert check_fn({"stats_block": sb, "report_draft": numbered})["numeric_check"]["passed"], "list numbers flagged"
    for expected, change in cases.items():
        out = check_fn({"stats_block": sb, "report_draft": {**good, **change}})["numeric_check"]
        found = {p["check"] for p in out["problems"]}
        assert expected in found, (expected, out["problems"])


@check("labels written 'Yes'/'No' for a whole group -> the user is ASKED (not stopped)")
def _():
    import pandas as pd
    f = OUTPUT_DIR / "check_input_capitalised_labels_synthetic.csv"
    df = pd.read_csv(CLEAN, dtype=str)
    df["tutoring"] = df["tutoring"].str.capitalize()
    df.to_csv(f, index=False)
    state, config = new_run("check-capitalised", f)
    result = graph.invoke(state, config)
    assert "__interrupt__" in result, result.get("diagnostic_decision")
    reqs = result["__interrupt__"][0].value["requests"]
    assert len(reqs) == 80 and all(r["check"] == "invalid_label" for r in reqs)


@check("rejected answers are shown in the next pause; strict number parsing; out-of-range message")
def _():
    state, config = new_run("check-rejections", MESSY)
    result = graph.invoke(state, config)
    reqs = result["__interrupt__"][0].value["requests"]
    s006 = next(r for r in reqs if r["request_id"] == "S006:out_of_range")
    parse = ns["parse_user_answer"]
    for bad in ["8_5", "٨٥", "1e1"]:
        try:
            parse(s006, {"response": bad, "reason": "TEST INPUT"}); raise AssertionError(bad)
        except ValueError:
            pass
    try:
        parse(s006, {"response": "805", "reason": "TEST INPUT"}); raise AssertionError("805 accepted")
    except ValueError as err:
        assert "between 0 and 100" in str(err)
    assert parse(s006, {"response": "85.0", "reason": "TEST INPUT"})["value"] == "85"
    answers = answers_for(reqs, case_study_answers)
    answers["S006:out_of_range"] = {"response": "805", "reason": "TEST INPUT: typo"}
    result = graph.invoke(Command(resume=answers), config)
    payload = result["__interrupt__"][0].value
    assert any(r["request_id"] == "S006:out_of_range" for r in payload["previous_rejections"])
    assert [r["request_id"] for r in payload["requests"]] == ["S006:out_of_range"]


@check("duplicate ID: question states the row count; only exclude/stop offered for every finding on that ID")
def _():
    import pandas as pd
    f = OUTPUT_DIR / "check_input_duplicate_id_synthetic.csv"
    df = pd.read_csv(CLEAN, dtype=str)
    extra = df[df["student_id"] == "S010"].assign(score="850")
    pd.concat([df, extra]).to_csv(f, index=False)
    state, config = new_run("check-duplicate", f)
    result = graph.invoke(state, config)
    reqs = [r for r in result["__interrupt__"][0].value["requests"] if r["record_id"] == "S010"]
    assert {r["check"] for r in reqs} == {"duplicate_id", "out_of_range"}, reqs
    assert all(r["allowed_responses"] == ["exclude", "stop"] for r in reqs)
    assert "2 rows" in next(r for r in reqs if r["check"] == "duplicate_id")["detail"]


@check("excluding an out-of-range record is reported as a non-missing exclusion, not 'complete-case'")
def _():
    state, config = new_run("check-exclusion-reason", MESSY)
    result = graph.invoke(state, config)
    def rules(r):
        if r["check"] == "out_of_range":
            return "exclude", "TEST INPUT: source record lost"
        return case_study_answers(r)
    while "__interrupt__" in result:
        result = graph.invoke(Command(resume=answers_for(result["__interrupt__"][0].value["requests"], rules)), config)
    lims = result["stats_block"]["required_limitations"]
    assert "excluded_flagged_records" in lims and "S006 (out of range)" in lims["excluded_flagged_records"], lims
    assert "complete-case" not in result["report_draft"]["interpretation"]
    assert result["final_status"] == "delivered"


@check("mock reviewer flags a causal sentence that merely mentions 'no tutoring'")
def _():
    state, config = new_run("check-mock-negation", CLEAN)
    result = graph.invoke(state, config)
    draft = dict(result["report_draft"])
    draft["interpretation"] += " Compared with students who had no tutoring, tutoring improved scores."
    verdict = ns["AGENT_B"].review({"report_draft": draft, "stats_block": result["stats_block"]})
    assert not verdict.passed and verdict.issues[0].category == "causal_claim"


@check("helpers: model-identity guard normalises names; p-value never prints as alpha")
def _():
    rm = ns["resolved_model"]
    assert rm("openai:gpt-4.1-mini") == rm("gpt-4.1-mini") == rm(" OpenAI:GPT-4.1-mini ")
    assert rm("openai:gpt-4.1-mini") != rm("anthropic:claude-sonnet-5-5")
    fp = ns["format_p"]
    assert fp(0.04996) != "0.0500" and float(fp(0.04996)) < 0.05
    assert fp(0.0140) == "0.0140" and fp(0.00001) == "< 0.0001"


# ---------------------------------------------------------------------------
print()
for name, status, detail in RESULTS:
    print(f"[{status}] {name}" + (f"\n        {detail}" if detail else ""))
n_fail = sum(s == "FAIL" for _, s, _ in RESULTS)
print(f"\n{len(RESULTS) - n_fail}/{len(RESULTS)} checks passed")
sys.exit(1 if n_fail else 0)
