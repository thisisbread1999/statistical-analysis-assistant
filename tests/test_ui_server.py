"""Browser adapter checks using the real graph and explicit mock agents.

These exercise the UI boundary, its asynchronous jobs and human decisions. They
do not measure either language model's accuracy or reproduce the statistical
tool's implementation.
"""
from __future__ import annotations

import copy
import json
import threading
import time
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from stat_assistant import settings
from ui_server import Workspace, create_server


CONFIGURATION = {
    "mode": "mock", "model_a": "ollama:qwen3:8b", "model_b": "ollama:gemma3:12b"
}
QUESTION = "Is the mean score different between tutoring groups?"
PROJECT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("example_id,warning", [
    ("regression_influential", "influential_observations"),
    ("regression_heteroscedastic", "heteroscedasticity"),
])
def test_regression_examples_keep_target_and_expose_diagnostics(workspace, example_id, warning):
    result = finish(workspace, {"action": "analyze", "mode": "mock", "example": example_id,
                              "question": workspace.example(example_id)["question"]})
    assert result["plan"]["x"] == "x" and result["plan"]["y"] == "y"
    if result["status"] == "needs_clarification":
        requests = result["clarification"]["requests"]
        assert all("verify" in item["allowed_responses"] for item in requests)
        result = finish(workspace, {"action": "resume", "session_id": result["session_id"],
                                   "answers": [{"request_id": item["request_id"], "action": "verify",
                                                "reason": "TEST FIXTURE: retain deliberately generated synthetic observations."}
                                               for item in requests]})
    assert result["status"] == "delivered", result
    diagnostic = result["stats"]["regression_diagnostics"]
    assert warning in {item["code"] for item in diagnostic["warnings"]}
    assert warning in result["stats_block"]["required_limitations"]
    assert len(diagnostic["observations"]) == 60
    assert "Regression diagnostics" in result["report"]
DESIGN = {
    "id_column": "student_id",
    "independence": "Independent observations explicitly confirmed for this synthetic example.",
    "assignment": "Voluntary tutoring participation; not randomized.",
    "randomized": False,
    "typical_outcome": "score",
    "variables": {
        "score": {"type": "numeric", "range": [0, 100], "meaning": "Exam score."},
        "tutoring": {"type": "categorical", "levels": ["yes", "no"], "meaning": "Tutoring participation."},
    },
}


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "OUTPUT_DIR", tmp_path / "core_outputs")
    instance = Workspace(runtime_dir=tmp_path / "ui", configuration=CONFIGURATION)
    try:
        yield instance
    finally:
        instance.close()


def finish(workspace, payload, timeout=15):
    """Wait for a bounded mock job, surfacing its failure as the test evidence."""
    submitted = workspace.submit(payload)
    assert isinstance(submitted["job_id"], str) and submitted["job_id"]
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        job = workspace.job(submitted["job_id"])
        if job["status"] != "running":
            assert job["status"] == "completed", job
            return job["result"]
        time.sleep(.02)
    pytest.fail("The mock UI job did not finish within the bounded wait.")


def analyze(workspace, example="welch", **changes):
    return finish(workspace, {
        "action": "analyze", "example": example, "mode": "mock",
        "question": workspace.example(example)["question"], **changes,
    })


def fixture_answers(requests):
    """Explicit teaching-data decisions; never production defaults."""
    answers = []
    for request in requests:
        answer = {
            "request_id": request["request_id"],
            "reason": "TEST FIXTURE: checked the documented synthetic source.",
        }
        if request["check"] == "missing_value":
            answer["action"] = "exclude"
        elif request["check"] == "out_of_range":
            answer.update(action="correct", new_value="85")
        elif request["check"] == "invalid_label":
            answer.update(action="correct", new_value="yes")
        else:
            answer["action"] = "verify"
        answers.append(answer)
    return answers


def trace_nodes(result):
    return [item["node"] for item in result["trace"]]


@pytest.mark.parametrize("example,method", [
    ("welch", "welch_t_test"),
    ("pearson", "pearson_correlation"),
    ("chi_square", "chi_square_independence"),
    ("regression", "simple_linear_regression"),
])
def test_mock_examples_run_actual_methods_and_remain_labelled(workspace, example, method):
    result = analyze(workspace, example)
    assert result["status"] == "delivered", result
    assert result["mode"] == "mock"
    assert "MOCK" in result["report"]
    assert result["stats"]["method"] == method
    assert result["plan"]["method"] == method
    assert result["can_followup"]
    assert "run_statistical_test" in trace_nodes(result)
    assert "review_report" in trace_nodes(result)
    assert result["model_calls"] and all(call["mode"] == "MOCK" for call in result["model_calls"])
    # Strict JSON is a browser boundary requirement, including special statistical values.
    json.dumps(result, allow_nan=False)
    if example == "welch":
        assert result["stats"]["mean_difference"] == pytest.approx(6.9175)
        assert result["stats"]["p_value"] == pytest.approx(.000824240443)
        assert result["stats"]["n_included"] == 80
        assert result["stats_block"]["decision"] == "reject_H0"
        assert "causation" in result["report"].lower()


def test_other_group_examples_show_relevant_results(workspace):
    no_difference = analyze(workspace, "no_difference")
    assert no_difference["status"] == "delivered"
    assert no_difference["stats_block"]["decision"] == "do_not_reject_H0"
    unequal = analyze(workspace, "unequal_variance")
    assert unequal["status"] == "delivered"
    assert unequal["stats"]["var_equal"] is False
    assert unequal["stats"]["n_included"] == 80


def test_messy_data_requires_explicit_decisions_and_preserves_source(workspace):
    source = PROJECT / "examples" / "tutoring_scores_messy_synthetic.csv"
    source_before = source.read_bytes()
    result = analyze(workspace, "messy")
    assert result["status"] == "needs_clarification"
    assert not result["stats"] and not result["can_followup"]
    assert result["correction_log"] == [] and result["data_version"] == "v1"
    requests = result["clarification"]["requests"]
    assert {request["check"] for request in requests} >= {"missing_value", "invalid_label", "out_of_range"}
    answers = fixture_answers(requests)
    resumed = finish(workspace, {"action": "resume", "session_id": result["session_id"], "answers": answers})
    if resumed["status"] == "needs_clarification":
        # A confirmed correction can reveal another flag, which needs a new human decision.
        resumed = finish(workspace, {
            "action": "resume", "session_id": result["session_id"],
            "answers": fixture_answers(resumed["clarification"]["requests"]),
        })
    assert resumed["status"] == "delivered", resumed
    assert resumed["data_version"] != "v1"
    assert resumed["stats"]["n_included"] == 78
    assert source.read_bytes() == source_before
    assert "missing_data" in resumed["stats_block"]["required_limitations"]
    assert all(entry["reason"] and entry["source"] == "explicit user answer" for entry in resumed["correction_log"])
    assert sum(entry["action"] == "exclude" for entry in resumed["correction_log"]) == 2


@pytest.mark.parametrize("note_kind", ["blank", "missing", "none"])
def test_messy_decisions_accept_optional_notes_and_keep_explicit_audit(workspace, note_kind):
    source = PROJECT / "examples" / "tutoring_scores_messy_synthetic.csv"
    source_before = source.read_bytes()
    result = analyze(workspace, "messy")
    assert result["status"] == "needs_clarification"

    def optional_note_answers(requests):
        answers = fixture_answers(requests)
        for answer in answers:
            if note_kind == "missing":
                answer.pop("reason")
            else:
                answer["reason"] = "   " if note_kind == "blank" else None
        return answers

    resumed = finish(workspace, {
        "action": "resume", "session_id": result["session_id"],
        "answers": optional_note_answers(result["clarification"]["requests"]),
    })
    if resumed["status"] == "needs_clarification":
        resumed = finish(workspace, {
            "action": "resume", "session_id": result["session_id"],
            "answers": optional_note_answers(resumed["clarification"]["requests"]),
        })
    assert resumed["status"] == "delivered", resumed
    assert resumed["data_version"] != "v1"
    assert resumed["stats"]["n_included"] == 78
    assert source.read_bytes() == source_before
    assert "missing_data" in resumed["stats_block"]["required_limitations"]
    assert all(entry["reason"] == "" and entry["source"] == "explicit user answer"
               for entry in resumed["correction_log"])
    assert sum(entry["action"] == "exclude" for entry in resumed["correction_log"]) == 2
    corrected = {entry["new_value"] for entry in resumed["correction_log"] if entry["action"] == "correct"}
    assert corrected == {"85", "yes"}
    assert any(entry["action"] == "verify" for entry in resumed["correction_log"])


@pytest.mark.parametrize("invalid_input", ["impossible_correction", "missing_action", "missing_corrected_value", "missing_answer"])
def test_invalid_answer_cannot_apply_corrections_or_consume_the_pause(workspace, invalid_input):
    result = analyze(workspace, "messy")
    answers = fixture_answers(result["clarification"]["requests"])
    if invalid_input in ("impossible_correction", "missing_corrected_value"):
        correction = next(answer for answer in answers if answer.get("new_value") == "85")
        if invalid_input == "impossible_correction":
            correction["new_value"] = "999"
        else:
            correction.pop("new_value")
    elif invalid_input == "missing_action":
        answers[0].pop("action")
    else:
        answers.pop()
    jobs_before = len(workspace.jobs)
    with pytest.raises(ValueError):
        workspace.submit({"action": "resume", "session_id": result["session_id"], "answers": answers})
    session = workspace.sessions[result["session_id"]]
    assert not session["busy"] and len(workspace.jobs) == jobs_before
    assert session["state"]["data_version"] == "v1" and session["state"]["correction_log"] == []
    assert not session["state"].get("stat_result")
    # The same current request IDs remain usable after rejected input.
    valid = finish(workspace, {
        "action": "resume", "session_id": result["session_id"],
        "answers": [{"request_id": result["clarification"]["requests"][0]["request_id"], "action": "stop", "reason": ""}],
    })
    assert valid["status"] == "stopped"
    assert valid["data_version"] == "v1" and valid["correction_log"] == []
    assert not valid["stats"]


def test_followup_is_not_allowed_while_human_decision_is_pending(workspace):
    result = analyze(workspace, "messy")
    with pytest.raises(ValueError):
        workspace.submit({"action": "followup", "session_id": result["session_id"], "question": "Explain simply."})


def test_followup_reuses_statistics_or_recomputes_ci_as_requested(workspace):
    initial = analyze(workspace)
    explained = finish(workspace, {
        "action": "followup", "session_id": initial["session_id"], "question": "Please explain this simply."
    })
    assert explained["status"] == "delivered"
    assert explained["stats"] == initial["stats"]
    assert "run_statistical_test" not in trace_nodes(explained)
    assert "draft_report" in trace_nodes(explained) and "review_report" in trace_nodes(explained)
    interval = finish(workspace, {
        "action": "followup", "session_id": initial["session_id"], "question": "Report a 99% confidence interval."
    })
    assert interval["status"] == "delivered"
    assert "run_statistical_test" in trace_nodes(interval)
    assert "stat_diagnostics" not in trace_nodes(interval)
    assert interval["stats"]["ci_upper"] > initial["stats"]["ci_upper"]
    assert interval["stats"]["p_value"] == initial["stats"]["p_value"]
    assert interval["stats_block"]["values"]["alpha"] == initial["stats_block"]["values"]["alpha"]


def test_paired_design_stops_before_any_model_calls(workspace):
    result = analyze(workspace, "paired")
    assert result["status"] == "stopped"
    assert result["model_calls"] == [] and not result["stats"]
    assert not result["can_followup"]
    assert "paired" in result["report"].lower()


def upload_payload(**changes):
    return {
        "action": "analyze", "mode": "mock", "question": QUESTION,
        "csv": (PROJECT / "examples" / "tutoring_scores_clean_synthetic.csv").read_text(encoding="utf-8"),
        "design_info": copy.deepcopy(DESIGN), "design_confirmed": True,
        **changes,
    }


def test_uploaded_csv_uses_confirmed_metadata(workspace):
    result = finish(workspace, upload_payload())
    assert result["status"] == "delivered"
    assert result["stats"]["n_included"] == 80
    assert result["stats"]["mean_difference"] == pytest.approx(6.9175)


@pytest.mark.parametrize("changes", [
    {"design_confirmed": False},
    {"design_info": {}},
    {"design_info": "not an object"},
    {"csv": "score,score\n1,2\n"},
    {"csv": "score,tutoring\n1\n"},
    {"csv": "score,tutoring\n1,yes,extra\n"},
    {"csv": ""},
    {"csv": "score,tutoring\n"},
    {"csv": "x\n" + "a" * (5 * 1024 * 1024)},
    {"question": "   "},
    {"mode": "automatic-fallback"},
])
def test_invalid_upload_input_is_rejected_before_scheduling(workspace, changes):
    with pytest.raises(ValueError):
        workspace.submit(upload_payload(**changes))


def test_no_arbitrary_file_path_interface_or_unknown_session(workspace):
    with pytest.raises(ValueError):
        workspace.submit({"action": "analyze", "data_path": str(PROJECT / ".env"), "mode": "mock", "question": QUESTION})
    with pytest.raises(ValueError):
        workspace.submit({"action": "resume", "session_id": "not-a-session", "answers": []})
    with pytest.raises(ValueError):
        workspace.submit({"action": "followup", "session_id": "not-a-session", "question": "Explain."})


def test_real_setup_failure_is_a_failed_job_without_mock_fallback(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "OUTPUT_DIR", tmp_path / "outputs")
    seen = []

    def failed_factory(configuration):
        seen.append(configuration)
        raise RuntimeError("TEST provider unavailable with PRIVATE_TEST_DETAIL")

    workspace = Workspace(runtime_dir=tmp_path / "ui", configuration=CONFIGURATION, agents_factory=failed_factory)
    try:
        submitted = workspace.submit({"action": "analyze", "example": "welch", "mode": "real", "question": QUESTION})
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            job = workspace.job(submitted["job_id"])
            if job["status"] != "running":
                break
            time.sleep(.02)
        assert job["status"] == "failed", job
        assert not job.get("result")
        assert seen and seen[0]["mode"] == "real"
        assert "PRIVATE_TEST_DETAIL" not in str(job)
    finally:
        workspace.close()


@pytest.fixture
def http_ui(workspace):
    server = create_server(workspace, port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    address, port = server.server_address
    assert address == "127.0.0.1"
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)


def request(base, path="/", payload=None, headers=None):
    headers = headers or {}
    data = None
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers = {"Content-Type": "application/json", **headers}
    req = Request(base + path, data=data, headers=headers)
    try:
        with urlopen(req, timeout=5) as response:
            return response.status, dict(response.headers), response.read()
    except HTTPError as error:
        return error.code, dict(error.headers), error.read()


def strict_json(data):
    def reject_constant(value):
        raise AssertionError(f"Invalid JSON constant {value}")
    return json.loads(data, parse_constant=reject_constant)


@pytest.mark.parametrize("path,content_type", [
    ("/", "text/html"), ("/app.js", "javascript"), ("/style.css", "text/css"),
])
def test_serves_expected_browser_assets(http_ui, path, content_type):
    status, headers, data = request(http_ui, path)
    assert status == 200 and data
    assert content_type in headers["Content-Type"]
    assert headers.get("X-Content-Type-Options") == "nosniff"


def test_catalog_and_examples_are_json_and_unknown_routes_are_404(http_ui):
    status, _, data = request(http_ui, "/api/catalog")
    assert status == 200 and strict_json(data)
    status, _, data = request(http_ui, "/examples/messy.json")
    assert status == 200
    example = strict_json(data)
    assert "student_id" in example["columns"] and example["rows"] == 80
    assert "S006" in example["csv"]
    assert request(http_ui, "/api/jobs/not-a-job")[0] == 404
    assert request(http_ui, "/examples/not-a-case.json")[0] == 404
    assert request(http_ui, "/missing.html")[0] == 404


def test_http_post_enforces_local_origin_and_host(http_ui):
    payload = {"action": "analyze", "example": "welch", "mode": "mock", "question": QUESTION}
    assert request(http_ui, "/api", payload, {"Origin": "https://unrelated.example"})[0] == 403
    assert request(http_ui, "/api", payload, {"Host": "unrelated.example"})[0] == 403
    # Same-origin browser requests and local command-line requests are both supported.
    status, _, data = request(http_ui, "/api", payload, {"Origin": http_ui})
    assert status in (200, 202) and strict_json(data)["job_id"]
    status, _, data = request(http_ui, "/api", payload)
    assert status in (200, 202) and strict_json(data)["job_id"]


def test_http_rejects_invalid_json_numbers_and_non_object_requests(http_ui):
    status, _, data = request(http_ui, "/api", {"action": "analyze", "bad": float("nan")})
    assert status == 400 and "finite" in strict_json(data)["error"]
    assert request(http_ui, "/api", ["not", "an", "object"])[0] == 400
    assert request(http_ui, "/api", {}, {"Content-Type": "text/plain"})[0] == 415


def test_http_job_endpoint_delivers_a_strict_json_result(http_ui):
    status, _, data = request(http_ui, "/api", {
        "action": "analyze", "example": "welch", "mode": "mock", "question": QUESTION,
    })
    assert status == 202
    job_id = strict_json(data)["job_id"]
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        status, _, data = request(http_ui, f"/api/jobs/{job_id}")
        assert status == 200
        job = strict_json(data)
        if job["status"] != "running":
            break
        time.sleep(.02)
    assert job["status"] == "completed", job
    assert job["result"]["status"] == "delivered"
    assert job["result"]["stats"]["n_included"] == 80
