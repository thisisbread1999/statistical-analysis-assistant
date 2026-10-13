"""Meaningful adapter checks; MOCK mechanics are never live LLM accuracy."""
import csv
import json

import pytest

import benchmark_suite as bench
from stat_assistant.agents import MockAnalysisAgentA, MockReviewAgentB
from stat_assistant.tools import execute


def case(name):
    return bench.load_cases([name])[0]


def test_frozen_source_catalog_has_31_and_correct_commit():
    rows = bench.cases()
    assert len(rows) == 31
    assert {r["category"] for r in rows} == set(bench.GROUPS)
    assert all(r["adapter"]["source_commit"] == "b7eff1c4a8035f196ac4bfc73ef3fe88956dadb5" for r in rows)
    assert sum(r["source"]["expected_behavior"] == "result" for r in rows) == 17


def test_unknown_case_and_category_rejected():
    with pytest.raises(ValueError, match="Unknown cases"):
        bench.run(selected=["not_a_case"], export_only=True)
    with pytest.raises(ValueError, match="Unknown categories"):
        bench.load_cases(categories=["not_a_category"])


def test_planning_context_has_no_gold_or_invented_target():
    context = bench.build_protected_context(case("regression_clean"), mode="live")
    assert set(context) == {"question", "design_info", "data_path"}
    text = json.dumps(context)
    assert "numeric_reference" not in text and "expected_method" not in text and "typical_outcome" not in text
    ambiguous = bench.build_protected_context(case("regression_direction"), mode="live")
    assert "not chosen" in ambiguous["design_info"]["analysis_target"]
    codes = case("chi_square_numeric_codes")["design_info"]["variables"]
    assert all(value["type"] == "numeric" and "levels" not in value for value in codes.values())


def test_welch_contrast_matches_source_without_copying_reference():
    fixture = case("welch_clean")
    plan = bench.adapted_plan(fixture)
    assert (plan["group_1_label"], plan["group_2_label"]) == ("treatment", "control")
    oracle = bench.reference(fixture)
    assert oracle["mean_difference"] == pytest.approx(fixture["source"]["numeric_reference"]["effect"])
    fixture["source"]["numeric_reference"]["effect"] = -999
    assert bench.reference(fixture)["mean_difference"] == oracle["mean_difference"]


@pytest.mark.parametrize("name", ["welch_clean", "regression_missing"])
def test_primary_pause_retained_after_fixture_continuation(tmp_path, name):
    fixture = case(name)
    before = fixture["data_path"].read_bytes()
    paused = bench.evaluate(fixture, audit_dir=tmp_path / "primary")
    assert paused["primary_state"]["observed_status"] == "paused"
    assert paused["final_state"].get("stat_result", {}).get("status") != "ok"
    assert paused["mechanical_pass"] and not paused["interpretation_accepted"]
    continued = bench.evaluate(fixture, resume_fixtures=True, audit_dir=tmp_path / "continued")
    assert continued["primary_state"]["observed_status"] == "paused"
    assert continued["actual_status"] == "delivered"
    assert continued["numeric"]["passed"] and continued["interpretation_accepted"]
    assert all("TEST FIXTURE" in answer["reason"] for stage in continued["stages"] for answer in stage.get("answers", []))
    assert fixture["data_path"].read_bytes() == before
    if name == "regression_missing":
        assert continued["numeric"]["reference"]["n"] == 59
        assert continued["final_state"]["excluded_ids"] == ["row 1"]
        assert "missing_data" in continued["final_state"]["stats_block"]["required_limitations"]


@pytest.mark.parametrize("name", ["unknown_design", "ambiguous_outcome", "regression_direction", "chi_square_numeric_codes"])
def test_safe_stop_never_invents_answers_or_inference(tmp_path, name):
    row = bench.evaluate(case(name), resume_fixtures=True, audit_dir=tmp_path)
    assert row["actual_status"] == "stopped" and row["mechanical_pass"]
    assert row["final_state"].get("stat_result", {}).get("status") != "ok"
    assert not any(stage.get("answers") for stage in row["stages"])


def test_date_followup_stops_after_successful_warmup(tmp_path):
    row = bench.evaluate(case("correlation_2025"), audit_dir=tmp_path)
    assert row["warmup"]["observed_status"] == "delivered"
    assert row["actual_status"] == "stopped" and row["final_state"]["followup_route"] == "stop"
    assert "filter" in " ".join(row["final_state"]["stop_reasons"]).lower()
    assert row["numeric"]["reference"]["n"] == 20


def test_regression_threshold_is_preregistered(tmp_path):
    fixture = case("regression_too_few")
    assert fixture["source"]["expected_behavior"] == "stop" and fixture["expected_behavior"] == "result"
    row = bench.evaluate(fixture, audit_dir=tmp_path)
    assert row["mechanical_pass"] and row["numeric"]["reference"]["n"] == 4


def test_reference_uses_actual_version_exclusions_and_confidence(tmp_path):
    fixture = case("regression_clean")
    changed_path = tmp_path / "new_version.csv"
    fixture["data"].iloc[1:].to_csv(changed_path, index=False)
    state = {"analysis_plan": bench.adapted_plan(fixture), "data_path": str(changed_path), "excluded_ids": ["row 2"],
             "data_version": "v2", "conf_level": .99}
    oracle = bench.reference(fixture, state)
    computed = execute("run_test", bench.fixture_tool_request(fixture, state))
    assert oracle["n"] == 58 and computed["n"] == 58
    assert computed["slope"] == pytest.approx(oracle["slope"])
    assert computed["ci_lower"] == pytest.approx(oracle["ci_lower"])


def test_numeric_check_rejects_guessed_target():
    fixture = case("regression_clean")
    plan = bench.adapted_plan(fixture)
    plan.update(x="y", y="x")
    result = execute("run_test", bench.fixture_tool_request(fixture, {"analysis_plan": plan}))
    check = bench._numeric_checks(fixture, {"analysis_plan": plan, "stat_result": result})
    assert check["passed"] is False and not check["assessed"]


def test_live_rejects_mock_agents(tmp_path):
    with pytest.raises(ValueError, match="cannot contain mock"):
        bench.evaluate(case("regression_clean"), (MockAnalysisAgentA(), MockReviewAgentB()), mode="live", audit_dir=tmp_path)


def test_expected_stop_cannot_pass_when_planner_crashes(tmp_path):
    class FailedPlanner(MockAnalysisAgentA):
        def plan(self, *args, **kwargs):
            raise RuntimeError("provider unavailable")

    row = bench.evaluate(case("chi_square_sparse"), FailedPlanner(), audit_dir=tmp_path)
    assert row["actual_status"] == "stopped"
    assert not row["mechanical_pass"] and not row["checks"]["no_core_errors"]
    assert not row["safety_assessed"] and row["safety_pass"] is None
    assert row["failure_class"] == "model_or_tool_error"
    assert not row["numeric"]["assessed"]


def test_live_runtime_boundary_blinds_source_labels_and_preserves_bytes(tmp_path, monkeypatch):
    fixture = case("welch_clean")
    original = fixture["data_path"].read_bytes()
    captured = {}

    class AgentIdentity:
        is_mock = False

        def __init__(self, model_name):
            self.model_name = model_name

    def boundary(graph, data_path, question, design_info, **kwargs):
        captured.update(path=str(data_path), question=question, design_info=design_info)
        assert __import__("pathlib").Path(data_path).read_bytes() == original
        # This test spies the live entry boundary; it makes no actual model calls.
        raise RuntimeError("TEST SPY: stop before model invocation")

    monkeypatch.setattr(bench, "new_run", boundary)
    pair = (AgentIdentity("openai:boundary-a"), AgentIdentity("openai:boundary-b"))
    bench.evaluate(fixture, agents=pair, mode="live", audit_dir=tmp_path / "a1b2c3d4" / "e5f6a7b8")
    serialized = json.dumps(captured)
    assert fixture["id"] not in serialized and "/normal/" not in serialized.replace("\\", "/")
    assert "benchmark_v2" not in serialized and "numeric_reference" not in serialized
    assert captured["path"].endswith("input.csv") and fixture["data_path"].read_bytes() == original


def test_existing_evidence_rejected_and_failure_rows_retained(tmp_path, monkeypatch):
    (tmp_path / "occupied").mkdir()
    with pytest.raises(ValueError, match="exists"):
        bench.run(selected=["regression_clean"], prefix="occupied", output_root=tmp_path)

    def fail(*args, **kwargs):
        raise RuntimeError("provider failure; api_key=do_not_record_this")

    monkeypatch.setattr(bench, "evaluate", fail)
    summary = bench.run(selected=["regression_clean", "pearson_clean"], prefix="failures", output_root=tmp_path)
    assert summary["completed_case_count"] == 2
    assert all(row["actual_status"] == "runner_error" for row in summary["cases"])
    evidence = (tmp_path / "failures" / "results.json").read_text(encoding="utf-8")
    assert "do_not_record_this" not in evidence and "REDACTED" in evidence


def test_export_only_never_creates_agents(tmp_path, monkeypatch):
    monkeypatch.setattr(bench, "ADAPTED_ROOT", tmp_path)
    monkeypatch.setattr(bench, "create_agents", lambda *args, **kwargs: pytest.fail("export-only created agents"))
    result = bench.run(mode="live", export_only=True)
    assert result["exported_case_count"] == 31 and result["llm_calls"] == 0
    assert len(json.loads((tmp_path / "source_checksums.json").read_text())["files"]) == 63


def test_blank_human_labels_and_actual_report_hash(tmp_path, monkeypatch):
    monkeypatch.setattr(bench, "runtime_audit_dir", lambda out, case_id: tmp_path / "audit")
    summary = bench.run(selected=["regression_clean"], prefix="review_sheet", output_root=tmp_path)
    assert summary["cases"][0]["interpretation_accepted"]
    with (tmp_path / "review_sheet" / "human_review.csv").open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 1 and rows[0]["human_semantic_label"] == rows[0]["reviewer"] == ""
    assert rows[0]["report_sha256"] == bench._hash(tmp_path / "review_sheet" / rows[0]["frozen_report_file"])


def test_runtime_audit_paths_and_thread_tags_are_short_for_windows(tmp_path):
    path = bench.runtime_audit_dir(tmp_path / ("very_long_output_name" * 4), "welch_extreme_small_group")
    assert len(path.name) == len(path.parent.name) == 8
    filename = "bench-" + "a"*16 + "-diagnostics-1_diagnostics_" + "b"*12 + "_request.json"
    assert len(str(path / "stat_io" / filename)) < 260


@pytest.mark.parametrize("fixture", bench.supplemental_cases(), ids=lambda c: c["id"])
def test_supplemental_followup_numbers_and_versions(tmp_path, fixture):
    row = bench.evaluate(fixture, resume_fixtures=True, audit_dir=tmp_path)
    assert row["mechanical_pass"], row["checks"]
    assert row["suite"] == "ours_supplemental_v1" and row["interpretation_accepted"]
    assert row["numeric"]["passed"] and row["final_state"]["request_number"] == 2
    if fixture["source_case_id"] == "regression_missing":
        assert row["primary_state"]["observed_status"] == "paused"
        assert row["numeric"]["reference"]["n"] == 59
        assert row["final_state"]["conf_level"] == .99
    assert len(bench.cases()) == 31
