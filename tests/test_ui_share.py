"""Exercise the temporary HTTPS sharing boundary with real mock statistics.

The origin and Host are simulated against a loopback HTTP server; no tunnel or
external account is needed. Existing test_ui_server.py covers ordinary local use.
"""
from __future__ import annotations

import http.client
import json
import threading
import time
from http.cookies import SimpleCookie
from urllib.parse import urlencode, urlsplit

import pytest

from stat_assistant import settings
from ui_server import Workspace, create_server


PUBLIC_ORIGIN = "https://class-demo.trycloudflare.com"
PUBLIC_HOST = urlsplit(PUBLIC_ORIGIN).netloc
SHARE_CODE = "TEST-only-share-code-0123456789"
QUESTION = "Compare the mean score for tutoring yes versus no."
CONFIGURATION = {"model_a": "ollama:qwen3:8b", "model_b": "ollama:gemma3:12b"}


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "OUTPUT_DIR", tmp_path / "core")
    instance = Workspace(runtime_dir=tmp_path / "ui", configuration=CONFIGURATION)
    try:
        yield instance
    finally:
        instance.close()


@pytest.fixture
def shared_ui(workspace):
    server = create_server(workspace, port=0, public_origin=PUBLIC_ORIGIN + "/", share_token=SHARE_CODE)
    assert server.server_address[0] == "127.0.0.1"
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server.server_port
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)


def request(port, path="/", *, payload=None, form=None, cookie=None, host=PUBLIC_HOST, origin=None):
    """Avoid redirect following so the login's cookie and status stay visible."""
    headers = {"Host": host}
    if cookie:
        headers["Cookie"] = cookie
    if origin is not None:
        headers["Origin"] = origin
    body = None
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    elif form is not None:
        body = urlencode(form).encode("utf-8")
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    try:
        connection.request("POST" if body is not None else "GET", path, body=body, headers=headers)
        response = connection.getresponse()
        return response.status, dict(response.getheaders()), response.read()
    finally:
        connection.close()


def login(port):
    status, headers, data = request(port, "/share-login", form={"code": SHARE_CODE}, origin=PUBLIC_ORIGIN)
    assert status == 303
    assert headers["Location"] == "/"
    assert SHARE_CODE.encode() not in data
    cookie = SimpleCookie()
    cookie.load(headers["Set-Cookie"])
    morsel = cookie["sa_share"]
    assert morsel.value and morsel.value != SHARE_CODE
    assert morsel["secure"] and morsel["httponly"]
    assert morsel["samesite"].lower() == "strict"
    assert morsel["path"] == "/"
    return f"sa_share={morsel.value}"


def wait_job(port, job_id, cookie, timeout=15):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        status, _, data = request(port, f"/api/jobs/{job_id}", cookie=cookie)
        assert status == 200
        job = json.loads(data)
        if job["status"] != "running":
            assert job["status"] == "completed", job
            return job["result"]
        time.sleep(.02)
    pytest.fail("The authenticated mock job did not finish in the bounded wait.")


@pytest.mark.parametrize("origin", [
    "http://class-demo.trycloudflare.com", "https://user:password@class-demo.trycloudflare.com",
    PUBLIC_ORIGIN + "/unexpected", PUBLIC_ORIGIN + "?query=1", PUBLIC_ORIGIN + "#fragment",
])
def test_invalid_public_origin_is_rejected_before_listening(workspace, origin):
    with pytest.raises(ValueError):
        server = create_server(workspace, port=0, public_origin=origin, share_token=SHARE_CODE)
        server.server_close()


def test_public_origin_requires_a_nontrivial_shared_code(workspace):
    for code in (None, "short"):
        with pytest.raises(ValueError):
            server = create_server(workspace, port=0, public_origin=PUBLIC_ORIGIN, share_token=code)
            server.server_close()


def test_login_gate_does_not_expose_assets_catalog_examples_or_jobs(shared_ui, capsys):
    status, headers, data = request(shared_ui)
    assert status == 200 and "text/html" in headers["Content-Type"]
    assert b"/share-login" in data and b"password" in data
    assert SHARE_CODE.encode() not in data
    for path in ("/app.js", "/api/catalog", "/examples/welch.json", "/api/jobs/not-a-job"):
        assert request(shared_ui, path)[0] == 401
    payload = {"action": "analyze", "example": "welch", "mode": "mock", "question": QUESTION}
    assert request(shared_ui, "/api", payload=payload, origin=PUBLIC_ORIGIN)[0] == 401
    status, _, data = request(shared_ui, "/share-login", form={"code": "wrong-code"}, origin=PUBLIC_ORIGIN)
    assert status == 401 and b"wrong-code" not in data
    cookie = login(shared_ui)
    assert request(shared_ui, "/api/catalog", cookie=cookie)[0] == 200
    assert request(shared_ui, "/examples/welch.json", cookie=cookie)[0] == 200
    assert SHARE_CODE not in capsys.readouterr().err


def test_authenticated_public_posts_still_require_exact_host_and_origin(shared_ui):
    cookie = login(shared_ui)
    payload = {"action": "analyze", "example": "welch", "mode": "mock", "question": QUESTION}
    assert request(shared_ui, host="unrelated.example", cookie=cookie)[0] == 403
    local_host = f"127.0.0.1:{shared_ui}"
    assert request(shared_ui, host=local_host)[0] == 403
    assert request(shared_ui, "/api", payload=payload, host=local_host,
                   origin=f"http://{local_host}")[0] == 403
    for origin in (None, "https://unrelated.example", "http://" + PUBLIC_HOST):
        assert request(shared_ui, "/api", payload=payload, cookie=cookie, origin=origin)[0] == 403
    assert request(shared_ui, "/api", payload=payload, cookie=cookie,
                   host="unrelated.example", origin=PUBLIC_ORIGIN)[0] == 403
    assert request(shared_ui, "/share-login", form={"code": SHARE_CODE})[0] == 403


def test_each_authenticated_browser_owns_its_jobs_and_followups(shared_ui):
    owner_a, owner_b = login(shared_ui), login(shared_ui)
    assert owner_a != owner_b
    payload = {"action": "analyze", "example": "welch", "mode": "mock", "question": QUESTION}
    status, _, data = request(shared_ui, "/api", payload=payload, cookie=owner_a, origin=PUBLIC_ORIGIN)
    assert status == 202
    job_id = json.loads(data)["job_id"]
    result = wait_job(shared_ui, job_id, owner_a)
    assert result["status"] == "delivered" and result["mode"] == "mock"
    assert result["stats"]["n_included"] == 80
    assert result["stats"]["mean_difference"] == pytest.approx(6.9175)
    assert "MOCK" in result["report"]
    assert request(shared_ui, f"/api/jobs/{job_id}", cookie=owner_b)[0] == 404
    followup = {"action": "followup", "session_id": result["session_id"], "question": "Explain simply."}
    status, _, data = request(shared_ui, "/api", payload=followup, cookie=owner_b, origin=PUBLIC_ORIGIN)
    assert status in (400, 404) and b"6.9175" not in data
    status, _, data = request(shared_ui, "/api", payload=followup, cookie=owner_a, origin=PUBLIC_ORIGIN)
    assert status == 202
    explained = wait_job(shared_ui, json.loads(data)["job_id"], owner_a)
    assert explained["status"] == "delivered" and explained["stats"] == result["stats"]


def test_another_browser_cannot_answer_an_owners_data_clarification(shared_ui):
    owner_a, owner_b = login(shared_ui), login(shared_ui)
    payload = {"action": "analyze", "example": "messy", "mode": "mock", "question": QUESTION}
    status, _, data = request(shared_ui, "/api", payload=payload, cookie=owner_a, origin=PUBLIC_ORIGIN)
    assert status == 202
    paused = wait_job(shared_ui, json.loads(data)["job_id"], owner_a)
    assert paused["status"] == "needs_clarification"
    stop = {"action": "resume", "session_id": paused["session_id"],
            "answers": [{"request_id": paused["clarification"]["requests"][0]["request_id"], "action": "stop"}]}
    assert request(shared_ui, "/api", payload=stop, cookie=owner_b, origin=PUBLIC_ORIGIN)[0] in (400, 404)
    status, _, data = request(shared_ui, "/api", payload=stop, cookie=owner_a, origin=PUBLIC_ORIGIN)
    assert status == 202
    assert wait_job(shared_ui, json.loads(data)["job_id"], owner_a)["status"] == "stopped"


def test_ordinary_local_server_still_supports_requests_without_login(workspace):
    server = create_server(workspace, port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    port = server.server_port
    host = f"127.0.0.1:{port}"
    try:
        assert request(port, "/api/catalog", host=host)[0] == 200
        assert request(port, host="unrelated.example")[0] == 403
        payload = {"action": "analyze", "example": "welch", "mode": "mock", "question": QUESTION}
        status, _, data = request(port, "/api", payload=payload, host=host)
        assert status == 202 and json.loads(data)["job_id"]
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)
