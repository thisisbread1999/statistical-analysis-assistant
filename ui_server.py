"""Local browser entry point, using the teammate's ui_server.py / ui/ convention.

The UI is an adapter to our existing seventeen-node workflow. CSV inputs and audit
files stay in ignored artifacts/runtime; graph memory lasts for this process only.
"""
from __future__ import annotations

import argparse
import copy
import csv
import io
import json
import math
import os
import secrets
import threading
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from demo import SYNTHETIC_DESIGN
from stat_assistant import settings
from stat_assistant.models import DEFAULT_MODEL_A, DEFAULT_MODEL_B, create_agents, load_env
from stat_assistant.nodes import validate_answers
from stat_assistant.runtime import ask_followup, new_run, resume_answers
from stat_assistant.workflow import ROLES, build_graph

PROJECT_DIR = Path(__file__).resolve().parent
UI_DIR = PROJECT_DIR / "ui"
MAX_CSV_BYTES = 4 * 1024 * 1024
MAX_BODY_BYTES = 5 * 1024 * 1024
MAX_ROWS, MAX_COLUMNS, MAX_SESSIONS, MAX_JOBS = 100_000, 100, 50, 250


def _examples():
    student = copy.deepcopy(SYNTHETIC_DESIGN)
    student["variables"].update({
        "study_hours": {"type": "numeric", "range": [0, 24], "meaning": "Hours of study per day"},
        "passed": {"type": "categorical", "levels": ["yes", "no"], "meaning": "Passed the exam"},
    })
    paired = copy.deepcopy(SYNTHETIC_DESIGN)
    paired["independence"] = "Paired repeated measurements from the same students (unsupported teaching scenario)."
    definitions = [
        ("welch", "Two-group mean comparison", "clean", "Compare the mean score for tutoring yes versus no.", SYNTHETIC_DESIGN,
         "Welch t-test; two independent groups, numeric score, nonrandom participation."),
        ("messy", "Data issues and user confirmation", "messy", "Compare the mean score for tutoring yes versus no.", SYNTHETIC_DESIGN,
         "Pause before inference for missing values, invalid labels and unusual observations. Choose an action; supporting notes are optional."),
        ("pearson", "Correlation of study hours and score", "students", "What is the Pearson correlation between study hours and score?", student,
         "Pearson correlation; linear association, with a confidence interval and causal restraint."),
        ("chi_square", "Association of tutoring and passing", "students", "Are tutoring and passed associated?", student,
         "Chi-square independence test; no confidence interval for Cramer's V in this stage."),
        ("regression", "Score change per additional study hour", "students", "Regress score on study hours: how does score change per additional study hour?", student,
         "Simple regression with one predictor and an intercept; observational association."),
        ("no_difference", "Non-significant mean comparison", "no_difference", "Compare the mean score for tutoring yes versus no.", SYNTHETIC_DESIGN,
         "A non-significant result must not be described as proof of equal population means."),
        ("unequal_variance", "Unequal variances and group sizes", "unequal_variance", "Compare the mean score for tutoring yes versus no.", SYNTHETIC_DESIGN,
         "Welch does not require equal variances; it still compares population means."),
        ("paired", "Unsupported paired study design", "clean", "Compare the mean score before and after for the same students.", paired,
         "Stop before model calls: paired or repeated observations require a method outside this prototype."),
    ]
    examples = {key: {"id": key, "title": title, "description": expected, "question": question,
                  "design_info": copy.deepcopy(design), "expected": expected,
                  "followup": "Explain the result in simpler words.",
                  "filename": "students_synthetic.csv" if data == "students" else f"tutoring_scores_{data}_synthetic.csv"}
            for key, title, data, question, design, expected in definitions}
    regression_design = {"id_column": None, "independence": "Independent observations, explicitly stated for this synthetic fixture.",
                         "randomized": False, "assignment": "Synthetic observational regression example.",
                         "variables": {"x": {"type": "numeric", "meaning": "Predictor"},
                                       "y": {"type": "numeric", "meaning": "Outcome"}}}
    for key, title, expected in [
        ("regression_influential", "Regression with an influential observation", "Inspect Cook's distance and leverage after resolving any data verification flags. No automatic deletion."),
        ("regression_heteroscedastic", "Regression with unequal error variance", "Inspect the Koenker Breusch–Pagan diagnostic and the limitations of ordinary OLS inference.")]:
        examples[key] = {"id": key, "title": title, "description": expected, "expected": expected,
                         "question": "Fit simple regression with predictor x and outcome y.", "design_info": copy.deepcopy(regression_design),
                         "followup": "Explain the regression diagnostics and their limitations.",
                         "filename": f"benchmark_v2/boundary/{key}.csv"}
    return examples


EXAMPLES = _examples()


def parse_csv(text):
    """Validate layout without interpreting, deleting or recoding any values."""
    if not isinstance(text, str) or not text.strip():
        raise ValueError("Supply a nonempty UTF-8 CSV file.")
    if len(text.encode("utf-8")) > MAX_CSV_BYTES:
        raise ValueError("CSV uploads are limited to 4 MiB.")
    if "\x00" in text:
        raise ValueError("The CSV contains a null character.")
    try:
        reader = csv.reader(io.StringIO(text.lstrip("\ufeff")), strict=True)
        columns = next(reader, [])
        if not columns or any(not name.strip() for name in columns) or len(set(columns)) != len(columns):
            raise ValueError("CSV headers must be nonempty and unique.")
        if len(columns) > MAX_COLUMNS:
            raise ValueError("CSV uploads are limited to 100 columns.")
        preview, count = [], 0
        for row in reader:
            if len(row) != len(columns):
                raise ValueError("Each CSV row must contain exactly the columns in the header.")
            count += 1
            if count > MAX_ROWS:
                raise ValueError("CSV uploads are limited to 100,000 rows.")
            if len(preview) < 6:
                preview.append(dict(zip(columns, row)))
        if not count:
            raise ValueError("The CSV contains no data rows.")
        return {"columns": columns, "rows": count, "preview": preview}
    except csv.Error as exc:
        raise ValueError("The CSV has invalid quoting or field structure.") from exc


def validate_design(design, columns):
    if not isinstance(design, dict) or not isinstance(design.get("variables"), dict):
        raise ValueError("Design metadata must be an object with a variables object.")
    for name, spec in design["variables"].items():
        if name not in columns or not isinstance(spec, dict):
            raise ValueError("Every metadata variable must name an existing CSV column and have an object definition.")
        if spec.get("type") not in ("numeric", "categorical"):
            raise ValueError("Metadata variable types must be numeric or categorical.")
        if "range" in spec:
            bounds = spec["range"]
            if (not isinstance(bounds, list) or len(bounds) != 2 or
                    any(isinstance(v, bool) or not isinstance(v, (float, int)) or not math.isfinite(v) for v in bounds) or
                    bounds[0] > bounds[1]):
                raise ValueError("Numeric ranges must contain two finite ordered numbers.")
        if "levels" in spec and (not isinstance(spec["levels"], list) or not spec["levels"] or
                                any(not isinstance(v, str) or not v for v in spec["levels"]) or
                                len(set(spec["levels"])) != len(spec["levels"])):
            raise ValueError("Categorical levels must be unique nonempty strings.")
    if design.get("id_column") and design["id_column"] not in columns:
        raise ValueError("id_column must name an existing CSV column.")
    for key in ("independence", "assignment"):
        if key in design and not isinstance(design[key], str):
            raise ValueError(f"{key} must be text describing the study.")
    if "randomized" in design and design["randomized"] is not None and not isinstance(design["randomized"], bool):
        raise ValueError("randomized must be true, false or null; use null when unknown.")
    # Unknown/unsupported independence remains a workflow issue, not an invented fact.
    return copy.deepcopy(design)


def _question(value):
    if not isinstance(value, str) or not value.strip() or len(value) > 10_000:
        raise ValueError("Enter a research question of 1 to 10,000 characters.")
    return value.strip()


def _json_safe(value):
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    return value


class Workspace:
    """One local workspace; requests queue to avoid concurrent mutations of a thread."""
    def __init__(self, runtime_dir=None, configuration=None, agents_factory=None):
        load_env()
        self.configuration = configuration or {
            "model_a": os.getenv("MODEL_A", DEFAULT_MODEL_A),
            "model_b": os.getenv("MODEL_B", DEFAULT_MODEL_B),
        }
        self.runtime_dir = Path(runtime_dir or settings.OUTPUT_DIR / "ui").resolve()
        self.runtime_dir.mkdir(parents=True, exist_ok=True)
        self.agents_factory = agents_factory or create_agents
        self.sessions, self.jobs = {}, {}
        self.lock = threading.RLock()
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="browser-analysis")

    def catalog(self):
        return {"examples": [{k: copy.deepcopy(v) for k, v in example.items() if k != "filename"}
                             for example in EXAMPLES.values()],
                "models": {k: self.configuration[k] for k in ("model_a", "model_b")}, "default_mode": "mock"}

    def example(self, key):
        if not isinstance(key, str) or key not in EXAMPLES:
            raise ValueError("Unknown example.")
        example = EXAMPLES[key]
        text = (settings.DATA_DIR / example["filename"]).read_text(encoding="utf-8")
        return {**copy.deepcopy(example), "csv": text, **parse_csv(text)}

    def submit(self, payload):
        if not isinstance(payload, dict):
            raise ValueError("The request must be a JSON object.")
        action = payload.get("action")
        with self.lock:
            if len(self.jobs) >= MAX_JOBS:
                raise ValueError("This local server has reached its request limit. Restart it for a new session.")
            if action == "analyze":
                if len(self.sessions) >= MAX_SESSIONS:
                    raise ValueError("This local server has reached its session limit. Restart it for a new session.")
                mode = payload.get("mode", "mock")
                if mode not in ("mock", "real"):
                    raise ValueError("Choose mock or real explicitly.")
                question = _question(payload.get("question"))
                if "csv" in payload and "example" in payload:
                    raise ValueError("Choose one source: a built-in example or an uploaded CSV.")
                if "csv" in payload:
                    if payload.get("design_confirmed") is not True:
                        raise ValueError("Review and explicitly confirm the uploaded CSV's design metadata first.")
                    text = payload["csv"]
                    preview = parse_csv(text)
                    design = validate_design(payload.get("design_info"), preview["columns"])
                else:
                    example = self.example(payload.get("example"))
                    text, preview = example["csv"], {k: example[k] for k in ("columns", "rows", "preview")}
                    design = validate_design(payload.get("design_info", example["design_info"]), preview["columns"])
                sid = secrets.token_urlsafe(24)
                directory = self.runtime_dir / sid
                directory.mkdir()
                path = directory / "input.csv"
                path.write_text(text.lstrip("\ufeff"), encoding="utf-8", newline="")
                session = {"session_id": sid, "mode": mode, "data_path": path, "question": question,
                           "design_info": design, "preview": preview, "graph": None, "state": {}, "busy": True}
                self.sessions[sid] = session
                operation = lambda: self._analyze(session)
            elif action in ("resume", "followup"):
                sid = payload.get("session_id")
                session = self.sessions.get(sid) if isinstance(sid, str) else None
                if session is None:
                    raise ValueError("Unknown or expired session. Start a new analysis.")
                if session["busy"]:
                    raise ValueError("This session already has an analysis running.")
                if session["graph"] is None:
                    raise ValueError("The session could not start. Run a new analysis after checking model setup.")
                state = session["state"]
                if action == "resume":
                    if not state.get("__interrupt__"):
                        raise ValueError("This session is not waiting for data clarification.")
                    answers = validate_answers(state["__interrupt__"][0].value["requests"], payload.get("answers"))
                    operation = lambda: resume_answers(session["graph"], session["session_id"], answers)
                else:
                    if state.get("__interrupt__"):
                        raise ValueError("Answer the outstanding data clarification before a follow-up.")
                    if not state.get("session_memory", {}).get("last_success"):
                        raise ValueError("A follow-up needs an earlier successful analysis.")
                    question = _question(payload.get("question"))
                    operation = lambda: ask_followup(session["graph"], session["session_id"], question)
                session["busy"] = True
            else:
                raise ValueError("Unknown action. Use analyze, resume or followup.")
            job_id = secrets.token_urlsafe(24)
            self.jobs[job_id] = {"status": "running"}
            self.executor.submit(self._execute, job_id, session, operation)
            return {"job_id": job_id}

    def _analyze(self, session):
        config = {**self.configuration, "mode": session["mode"]}
        agent_a, agent_b, _ = self.agents_factory(config)
        session["graph"] = build_graph(agent_a, agent_b, mode=session["mode"])
        return new_run(session["graph"], session["data_path"], session["question"], session["design_info"],
                       thread_id=session["session_id"])

    def _execute(self, job_id, session, operation):
        try:
            state = operation()
            result = self._public(session, state)
            with self.lock:
                session["state"] = state
                session["busy"] = False
                self.jobs[job_id] = {"status": "completed", "result": result}
        except Exception:
            # Provider exceptions can contain credentials, response bodies or local paths.
            # Keep a brief user-facing failure without substituting a mock result.
            with self.lock:
                session["busy"] = False
                self.jobs[job_id] = {"status": "failed", "error":
                    "The analysis could not start or finish. Check the configured models and local server setup, then run a new analysis. No mock fallback was used."}
        finally:
            with self.lock:
                session["busy"] = False

    def _public(self, session, state):
        number = state["request_number"]
        interrupts = state.get("__interrupt__", [])
        status = "needs_clarification" if interrupts else state.get("final_status", "stopped")
        errors = [{"node": e["node"], "type": e["type"], "message": "This step failed; no validated report was delivered."}
                  for e in state.get("errors", []) if e["request_number"] == number]
        report = state.get("final_report", "") if not errors else (
            "No validated inferential report was delivered. A workflow step failed. "
            "Check the model/service configuration and retry; no mock fallback was used.")
        preview = parse_csv(Path(state["data_path"]).read_text(encoding="utf-8"))
        inference = status == "delivered"
        return _json_safe({"session_id": session["session_id"], "mode": session["mode"],
            "models": {k: self.configuration[k] for k in ("model_a", "model_b")},
            "status": status, "request_number": number,
            "question": state.get("followup_question") if state.get("request_kind") == "followup" else state["research_question"],
            "plan": state.get("analysis_plan", {}), "data_summary": state.get("data_summary", {}),
            "llm_diagnostics": state.get("llm_diagnostics", {}), "stat_diagnostics": state.get("stat_diagnostics", {}),
            "stats": state.get("stat_result", {}) if inference else {},
            "stats_block": state.get("stats_block", {}) if inference else {}, "report": report,
            "interpretation": state.get("rendered_draft", {}) if inference else {},
            "program_check": state.get("program_check", {}), "review": state.get("review_verdict", {}),
            "trace": [{**t, "role": ROLES.get(t["node"], "")} for t in state.get("trace", []) if t["request_number"] == number],
            "model_calls": [c for c in state.get("model_calls", []) if c["request_number"] == number],
            "correction_log": state.get("correction_log", []), "data_version": state.get("data_version", "v1"),
            "errors": errors, "clarification": interrupts[0].value if interrupts else {"requests": [], "previous_rejections": []},
            "can_followup": not interrupts and bool(state.get("session_memory", {}).get("last_success")),
            "preview": preview})

    def job(self, job_id):
        with self.lock:
            if job_id not in self.jobs:
                raise ValueError("Unknown job.")
            return copy.deepcopy(self.jobs[job_id])

    def close(self):
        self.executor.shutdown(wait=True)


def create_server(workspace, port=8765):
    class Handler(BaseHTTPRequestHandler):
        def _local(self):
            expected = f"127.0.0.1:{self.server.server_port}"
            return self.headers.get("Host") == expected

        def _send(self, status, body, content_type="application/json; charset=utf-8"):
            data = json.dumps(_json_safe(body), ensure_ascii=False, allow_nan=False).encode("utf-8") if isinstance(body, (dict, list)) else body
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            if not self._local():
                return self._send(403, {"error": "Use this server's 127.0.0.1 address."})
            path = urlsplit(self.path).path
            assets = {"/": ("index.html", "text/html; charset=utf-8"),
                      "/app.js": ("app.js", "text/javascript; charset=utf-8"),
                      "/style.css": ("style.css", "text/css; charset=utf-8")}
            try:
                if path in assets:
                    name, mime = assets[path]
                    return self._send(200, (UI_DIR / name).read_bytes(), mime)
                if path == "/api/catalog":
                    return self._send(200, workspace.catalog())
                if path.startswith("/examples/") and path.endswith(".json"):
                    return self._send(200, workspace.example(path[len("/examples/"):-5]))
                if path.startswith("/api/jobs/"):
                    return self._send(200, workspace.job(path[len("/api/jobs/"):]))
            except (ValueError, FileNotFoundError):
                pass
            self._send(404, {"error": "Not found."})

        def do_POST(self):
            origin = self.headers.get("Origin")
            if not self._local() or origin not in (None, f"http://127.0.0.1:{self.server.server_port}"):
                return self._send(403, {"error": "Requests must come from this local UI."})
            if self.path != "/api":
                return self._send(404, {"error": "Not found."})
            if self.headers.get("Content-Type", "").split(";")[0].strip() != "application/json":
                return self._send(415, {"error": "Use application/json."})
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= MAX_BODY_BYTES:
                    return self._send(413, {"error": "Requests are limited to 5 MiB."})
                def reject_constant(value):
                    raise ValueError("JSON numbers must be finite.")
                payload = json.loads(self.rfile.read(length).decode("utf-8"), parse_constant=reject_constant)
                result = workspace.submit(payload)
            except (ValueError, UnicodeDecodeError) as exc:
                return self._send(400, {"error": str(exc)})
            self._send(202, result)

        def log_message(self, format, *args):
            # Request path/status only; never log CSV contents, questions or answers.
            super().log_message(format, *args)

    return ThreadingHTTPServer(("127.0.0.1", port), Handler)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    workspace = Workspace()
    server = create_server(workspace, args.port)
    print(f"Statistical Analysis Lab: http://127.0.0.1:{server.server_port}", flush=True)
    print("Mock and real modes are selected explicitly in the UI. Ctrl+C stops the server.", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        workspace.close()


if __name__ == "__main__":
    main()
