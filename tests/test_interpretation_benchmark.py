"""Authored challenge coverage, evidence isolation and honest failure accounting."""
from copy import deepcopy
import json

import pytest

import interpretation_benchmark as benchmark
from stat_assistant.agents import MockReviewAgentB


@pytest.fixture(scope="module")
def challenge_rows():
    return benchmark.challenges()


def test_sixteen_authored_categories_and_labels(challenge_rows):
    assert len(challenge_rows) == 16
    assert len({row["id"] for row in challenge_rows}) == 16
    assert sum(row["expected_valid"] for row in challenge_rows) == 4
    counts = {}
    for row in challenge_rows:
        counts[row["mutation"]] = counts.get(row["mutation"], 0) + 1
        assert row["provenance"]["source_commit"] == "b7eff1c"
        assert "not human" in row["provenance"]["label_kind"]
        assert row["correction_log"] == []
    assert counts == {"none": 4, "wrong_number": 4, "causal": 4, "wrong_method": 1,
                      "percent_misinterpretation": 1, "interval_probability": 1,
                      "nonlinear_no_relationship": 1}


def test_mutations_preserve_original_statistics_and_structured_claims(challenge_rows):
    for row in challenge_rows:
        original = row["original_draft"]
        draft = row["draft"]
        assert draft["limitations"] == original["limitations"]
        assert draft["decision_claim"] == original["decision_claim"] == row["stats_block"]["decision"]
        assert draft["direction_claim"] == original["direction_claim"] == row["stats_block"]["direction"]
        assert benchmark.check_report(row["stats_block"], original)["passed"]
        assert row["stat_result"]["status"] == "ok"
        assert "{p_value}" in original["interpretation"]
        if row["mutation"] == "wrong_number":
            assert "0.123" in draft["interpretation"]
            assert "{p_value}" not in draft["interpretation"]
            assert row["stats_block"]["values"]["p_value"] != "0.123"
        elif row["mutation"] == "none":
            assert draft["interpretation"] == original["interpretation"]
        else:
            assert draft["interpretation"].startswith(original["interpretation"])


class RecordingReviewer:
    model_name = "test recorder"

    def __init__(self):
        self.evidence = []

    def review(self, evidence):
        self.evidence.append(deepcopy(evidence))
        return {"passed": True, "issues": [], "summary": "Recorded evidence."}


def test_b_receives_original_evidence_even_after_program_rejection(challenge_rows):
    row = next(r for r in challenge_rows if r["id"] == "welch_clean_wrong_number")
    reviewer = RecordingReviewer()
    evaluated = benchmark.evaluate_challenge(row, reviewer)
    assert evaluated["detectors"]["program"]["accepted"] is False
    assert len(reviewer.evidence) == 1
    payload = reviewer.evidence[0]
    assert set(payload) == {"report_draft", "stat_result", "protected_statistics", "analysis_plan",
                            "design_info", "correction_log", "required_limitations"}
    assert "0.123" in payload["report_draft"]["interpretation"]
    assert "{p_value}" not in payload["report_draft"]["interpretation"]
    original_statistics = {key: value for key, value in row["stat_result"].items() if key != "data_path"}
    assert payload["stat_result"] == original_statistics
    assert payload["protected_statistics"] == row["stats_block"]
    assert payload["protected_statistics"]["values"]["p_value"] != "0.123"
    assert payload["analysis_plan"] == row["analysis_plan"]
    assert payload["required_limitations"] == row["stats_block"]["required_limitations"]
    assert "expected_valid" not in payload and "program_check" not in payload


def test_b_receives_no_challenge_identity_or_authored_type_labels(challenge_rows):
    planted_markers = ("wrong_number", "wrong_method", "percent_misinterpretation",
                       "interval_probability", "nonlinear_no_relationship", "_causal", "_valid")
    for row in challenge_rows:
        payload = benchmark.review_payload(row)
        text = json.dumps(payload, sort_keys=True)
        assert row["id"] not in text
        assert row["source_case"] not in text
        assert "expected_valid" not in text and '"mutation"' not in text
        assert all(marker not in text for marker in planted_markers)
        assert payload["report_draft"]["version"] == "v1"
        assert "data_path" not in payload["stat_result"]
        assert row["id"] and row["mutation"] and row["source_case"]
        assert "data_path" in row["stat_result"]
        assert row["original_draft"]["version"] == "v1"


def test_reviewer_cannot_mutate_saved_original_evidence(challenge_rows):
    class MutatingReviewer(RecordingReviewer):
        def review(self, evidence):
            evidence["protected_statistics"]["values"]["p_value"] = "invented"
            evidence["stat_result"]["p_value"] = 99
            return {"passed": True, "issues": [], "summary": "Done."}

    original = deepcopy(challenge_rows[0])
    evaluated = benchmark.evaluate_challenge(challenge_rows[0], MutatingReviewer())
    assert challenge_rows[0] == original
    assert evaluated["review_evidence"]["protected_statistics"] == original["stats_block"]
    assert evaluated["review_evidence"]["stat_result"] == {
        key: value for key, value in original["stat_result"].items() if key != "data_path"}


def test_offline_reports_existing_detector_blind_spots(challenge_rows):
    evaluated = [benchmark.evaluate_challenge(row, MockReviewAgentB()) for row in challenge_rows]
    summary = benchmark.score(evaluated)
    assert summary["program"]["valid_accepted"] == 4
    assert summary["reviewer_b"]["valid_accepted"] == 4
    assert summary["combined"]["valid_false_alarms"] == 0
    assert summary["program"]["planted_caught"] == 4
    assert summary["reviewer_b"]["planted_caught"] == 4
    assert summary["combined"]["planted_caught"] == 8
    assert summary["combined"]["planted_missed"] == 4
    assert summary["combined"]["planted_unassessed"] == 0


@pytest.mark.parametrize("kind", ["exception", "malformed", "empty_failed_verdict"])
def test_reviewer_failure_is_unassessed_without_detection_credit(challenge_rows, kind):
    class FailingReviewer:
        def review(self, evidence):
            if kind == "exception":
                raise RuntimeError("Model connection failed.")
            if kind == "malformed":
                return {"unexpected": "shape"}
            return {"passed": False, "issues": [], "summary": "Failed without evidence."}

    row = next(r for r in challenge_rows if r["id"] == "welch_clean_wrong_number")
    evaluated = benchmark.evaluate_challenge(row, FailingReviewer())
    summary = benchmark.score([evaluated])
    assert summary["program"]["planted_caught"] == 1
    for detector in ("reviewer_b", "combined"):
        assert evaluated["detectors"][detector]["accepted"] is None
        assert summary[detector]["planted_caught"] == 0
        assert summary[detector]["planted_missed"] == 0
        assert summary[detector]["planted_unassessed"] == 1


def test_only_critical_issues_reject_draft(challenge_rows):
    class MinorReviewer:
        def review(self, evidence):
            return {"passed": False, "issues": [{"severity": "minor", "category": "other",
                    "offending_sentence": "Optional phrasing.", "evidence": "Style only.",
                    "suggested_correction": "Optional wording."}], "summary": "Minor suggestion."}

    result = benchmark.evaluate_challenge(challenge_rows[0], MinorReviewer())
    assert result["detectors"]["reviewer_b"]["accepted"] is True
    assert result["detectors"]["reviewer_b"]["raw_verdict"]["passed"] is False


def test_offline_reviewer_does_not_initialize_real_models(monkeypatch):
    def no_live(*args, **kwargs):
        pytest.fail("Offline evaluation cannot initialize live models.")

    monkeypatch.setattr(benchmark.models, "create_agents", no_live)
    reviewer, config = benchmark.make_reviewer("offline")
    assert isinstance(reviewer, MockReviewAgentB)
    assert config["mode"] == "offline"


def test_live_uses_existing_config_and_never_calls_real_a(monkeypatch):
    calls = []

    class ForbiddenA:
        def draft(self, *args, **kwargs):
            pytest.fail("Interpretation challenge runner cannot call real Model A.")

    reviewer = RecordingReviewer()

    def create(config):
        calls.append(config)
        return ForbiddenA(), reviewer, config

    monkeypatch.setattr(benchmark.models, "load_env", lambda: None)
    monkeypatch.setattr(benchmark.models, "create_agents", create)
    monkeypatch.setenv("MODEL_A", "ollama:fixture-a")
    monkeypatch.setenv("MODEL_B", "ollama:fixture-b")
    actual, config = benchmark.make_reviewer("live")
    assert actual is reviewer
    assert calls == [{"mode": "real", "model_a": "ollama:fixture-a", "model_b": "ollama:fixture-b"}]


def test_unique_runs_save_per_case_and_errors_incrementally(tmp_path):
    class FailingReviewer:
        model_name = "failure test double"

        def review(self, evidence):
            raise RuntimeError("Reviewer unavailable.")

    selected = ["welch_clean_valid", "welch_clean_wrong_number"]
    directory = benchmark.run(selected=selected, name="retained", output_root=tmp_path, reviewer=FailingReviewer())
    assert (directory / "welch_clean_valid.json").exists()
    failed = json.loads((directory / "welch_clean_wrong_number.json").read_text(encoding="utf-8"))
    assert failed["detectors"]["reviewer_b"]["status"] == "unassessed"
    assert "Reviewer unavailable" in failed["detectors"]["reviewer_b"]["error"]
    results = json.loads((directory / "results.json").read_text(encoding="utf-8"))
    assert results["completed_cases"] == 2
    assert results["summary"]["reviewer_b"]["planted_unassessed"] == 1
    assert results["summary"]["reviewer_b"]["valid_unassessed"] == 1
    assert "not human semantic ratings" in (directory / "REPORT.md").read_text(encoding="utf-8")
    with pytest.raises(FileExistsError):
        benchmark.run(selected=selected, name="retained", output_root=tmp_path, reviewer=RecordingReviewer())


def test_selected_challenges_are_explicit_and_unknown_id_rejected():
    specs = benchmark.challenge_specs(["welch_clean_valid", "welch_wrong_method"])
    assert {spec["id"] for spec in specs} == {"welch_clean_valid", "welch_wrong_method"}
    with pytest.raises(ValueError, match="Unknown interpretation"):
        benchmark.challenge_specs(["missing-case"])
