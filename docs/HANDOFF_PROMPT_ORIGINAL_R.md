# Handoff prompt for continuing this project in Codex

You are taking over a student course project: **Agentic Statistical Analysis Assistant** (SMU Agentic AI course; team: Jingcheng Zhou + Junliang Lyu). Reply to me in **Chinese**. Write code, comments, node names and notebook text in **English**.

## Location and environment (Windows 11)
- Project (git repo, branch `main`): `C:\Users\62703\OneDrive\Desktop\SMU\26fall\agentic ai\langgraph_visualization`
- Python venv: `C:\Users\62703\.venvs\langgraph-viz` (Python 3.13; langgraph 1.2.14, langchain 1.4.4, langchain-ollama 1.1.0, scipy, pytest, jupyterlab)
- R: `C:\Program Files\R\R-4.4.1\bin\Rscript.exe` (+ jsonlite). Python calls R via `Rscript r/stats_tools.R <task> request.json result.json`. RStudio is only a development environment, never a tool the agents call.
- Local LLMs via Ollama (running): Model A = `ollama:qwen3:8b`, Model B = `ollama:gemma3:12b`. Configured in `.env` (no API keys yet; `.env` is gitignored). Ollama "thinking" is off by default (`OLLAMA_THINKING=on` enables it).
- Design source of truth: `C:\Users\62703\OneDrive\Desktop\SMU\26fall\agentic ai\agentic-ai-case-study.pdf`. Assignment: `...\agentic ai\LangGraph_Visualization_Assignment.docx`.
- Teammate's repo (read-only reference, cloned): `C:\Users\62703\code\statistical-analysis-assistant` (DeepSeek, SciPy, 4 methods, UI, 85 pytest tests; separate venv `C:\Users\62703\.venvs\sa-teammate`).

## Current state
1. **v1 is finished and frozen**: git tag `module6-submission-v1`. This is the Module 6 "Visualize Your Multi-Agent LangGraph" submission:
   - `stats_assistant_graph.ipynb`, all code in tagged notebook cells
   - `stats_assistant_langgraph.png`
   - `r/stats_tools.R` (v1: Welch only)
   - `data/*.csv` (synthetic)
   - `tests/run_checks.py` (18 mock checks, all pass) and `tests/check_real_mode_payloads.py`

   The graph has 16 nodes with these features:
   - parallel LLM + R diagnostics, joined at `merge_diagnostics`
   - `interrupt()` for record-level user clarification, then a new data version, a correction log and re-diagnosis
   - Welch test in R and a protected statistics block
   - Model A drafts, a program check runs, Model B (a different LLM) reviews, Model A revises at most once, then deliver or `issue_notice`, then `save_session`

   The notebook was executed with the local models, 7 examples, all ending as designed. Zip: `...\agentic ai\Zhou_Lyu_Module6_LangGraph_submission.zip`. **Do not break v1.**
2. **v2 is in progress (unfinished, not yet committed).** It extends our version with five features taken from the teammate's strengths:
   - (a) more methods: Pearson correlation, chi-square independence, simple linear regression, plus the existing Welch; all computed in R; variable roles chosen by Model A instead of fixed column names
   - (b) placeholder number protection: Model A writes `{p_value}` etc., and the program fills in the R values
   - (c) error handling: a failed LLM or R call is recorded in `state["errors"]`; later nodes skip their work; the next router goes to `issue_notice`; model calls are capped per request
   - (d) follow-up questions on the same `thread_id`: change the confidence level (e.g. a 99% CI), re-explain, or ask a new question
   - (e) engineering: a Python package instead of notebook-only code, pytest, CI

   Files already written for v2:
   - `docs/R_TOOLS_SPEC.md`: the R interface contract; read it first
   - `stats_assistant/settings.py`
   - `stats_assistant/methods.py`: method registry, placeholders, rounding, hypotheses
   - `stats_assistant/r_bridge.py`
   - `stats_assistant/schemas.py`: Pydantic; plain str fields with "" for unused values
   - `stats_assistant/models.py`: model config, `create_agents()`
   - `stats_assistant/agents.py`: prompts, real and mock agents
   - `stats_assistant/report.py`: `render()`, `check_report()`, `format_stats_block()`

   **A background AI job may have been rewriting** `r/stats_tools.R` (to the v2 spec, keeping a `welch_test` alias for v1), `r/make_synthetic_data.R` (adds `data/students_synthetic.csv`: 120 students with tutoring, study_hours, score, passed) and `tests/test_r_tools.py` (cross-checks against scipy). Check `git status` / `git diff` first. Verify that these files exist and pass. The md5 of the 4 existing data files must stay unchanged. If the job is incomplete, finish it.

## What remains for v2
1. `stats_assistant/nodes.py` and `stats_assistant/graph.py`. Planned design: 17 nodes.
   - Nodes:
     - `plan_analysis`: Model A; a self-loop labelled `revise_plan_once` for at most 1 plan revision; `stop` for an unsupported question
     - `prepare_data_summary`
     - `llm_diagnostics` ∥ `r_diagnostics`, joined at `merge_diagnostics`
     - `request_clarification` (interrupt) → `apply_corrections` → back to `prepare_data_summary`
     - `run_statistical_test` (R, uses `conf_level`)
     - `build_stats_block`
     - `draft_report` (placeholders)
     - `check_report` (program)
     - `review_report` (Model B; routes `review_passed` / `revise_once` / `fail_after_revision` / `error`)
     - `revise_report`
     - `deliver_report`
     - `issue_notice`
     - `save_session`
     - `handle_followup`: Model A; routes `new_confidence_level` → `run_statistical_test`, `re_explain` → `draft_report`, `new_question` → `plan_analysis`, `stop`
   - An entry router at `START`: `new_analysis` vs `followup`.
   - Every conditional edge uses a dict `path_map`, so the PNG shows labels; every node has `metadata={"role": ...}`, with no parentheses in role text (they break mermaid.ink).
   - Wrap nodes in a guard:
     - Skip the node if `state["errors"]` has an entry for the current `request_number`.
     - Catch exceptions into `errors`, but re-raise `langgraph.errors.GraphBubbleUp` (interrupt).
     - `issue_notice` and `save_session` are not skipped.
   - Errors, model calls and trace are `Annotated[list, operator.add]`, tagged with `request_number`.
   - A `new_question` follow-up keeps the value corrections but resets exclusions and verified IDs.
   - Model B fails a report only through a critical issue.
   - Required limitations come from the design (non-random), the correction log (missing vs other exclusions) and the method (`METHODS[...].limitation`).
   - TEST INPUT faults (`causal_claim`, `wrong_number`, `model_failure` at a named node) must be clearly labelled.
2. Run helpers: `new_run`, `ask_followup`, answer collection with `input()` that is validated and re-asked on bad input. User confirmations must never be invented.
3. Tests: port the 18 v1 checks to pytest for the package, and add tests for the new methods, placeholders, error routing, follow-up and the model-call cap. Add `pytest.ini` (`pythonpath = .`) and `.github/workflows/ci.yml` (setup-python, setup-r, jsonlite, pytest in mock mode).
4. New notebook `stats_assistant_v2.ipynb`:
   - show the source of State, routers and `build_graph`
   - `display(Image(graph.get_graph().draw_mermaid_png()))` and save the PNG; the image must come from the SAME compiled graph that runs the examples
   - an English explanation of every node, every edge and condition, and the A→B / B→A handoffs
   - examples: the 4 methods, follow-up (99% CI, re-explain), messy-data clarification, TEST faults, a model failure
   - run it with the local models; README updates
5. Commit v2 on a branch, not over the tag.

## Verified API notes (checked against installed langgraph 1.2.14 and R 4.4.1)
- **Do NOT use `add_node(error_handler=...)`.** In 1.2.14 the handler runs inside a parallel fan-out, but `invoke()` still re-raises the original exception at the end. The handler node is also drawn as an orphan box, and the edge its `Command(goto=...)` takes is not drawn. Use the try/except guard described above, which writes to an `errors` reducer list.
- Follow-up: a new `invoke()` on the same `thread_id` restarts at START with the saved state. `add_conditional_edges(START, router, {...})` works and shows labels. Reducer keys passed in the input are appended, not replaced; plain keys are overwritten. Keep per-request fields as plain keys, or tag list entries with `request_number`.
- `RetryPolicy` (`langgraph.types`) does not retry ValueError/RuntimeError by default. Don't set `timeout=` on sync nodes.
- R: add `Sys.setenv(LANGUAGE="en")`, because R messages on this machine are in Chinese. Detect conditions structurally (e.g. `any(ct$expected < 5)`), not by matching message text. Check `is.finite` before computing. A constant x makes `lm` drop the slope, and zero variance makes `cor.test` return NA. Wrap variable-length vectors in `I()`. Use `always_decimal=TRUE`. Cast numbers with `float()` in Python.
- Chi-square: R's 2x2 default uses the Yates correction; the teammate's SciPy code does not. Decide which to use, state it in the report, and keep Cramér's V consistent with that choice.
- Our R script reads the raw CSV on purpose (with `na.strings=character(0)`, `strip.white=FALSE`), so that blanks and `"yes "` stay visible as findings. Do not pre-clean the data in Python.
- Research notes and reusable R check scripts: `C:\Users\62703\AppData\Local\Temp\claude\C--Users-62703-OneDrive-Desktop-SMU-Zhang-s-project-collbra\36136ecf-0afb-46cb-bd21-312c5a8bd937\scratchpad\rcheck\` (temporary folder; it may be cleaned up).

## Rules you must keep (the user's explicit requirements)
- Model A and Model B must be different underlying models, configured separately. Never fake a second model with two roles of one model.
- R scripts, program checks and save steps are tools/steps, not agents.
- Never auto-delete, edit or impute data. Every change or exclusion needs a user answer plus a reason, and is logged. The original CSV stays unchanged.
- Welch does not assume equal variances. Shapiro-Wilk is descriptive only and never switches the method. Never switch to a method that answers a different question. No causal claims for non-randomized designs.
- Synthetic data is labelled as such. Results are computed by R, never hard-coded or tuned to the PDF numbers.
- Be honest: label mock / TEST INPUT clearly; never claim that unverified things (e.g. cloud APIs, which are only checked offline) work.
- Before any push, PR, or other outward-facing action, ask me first.

## How to check
- `C:\Users\62703\.venvs\langgraph-viz\Scripts\python.exe tests\run_checks.py` (v1, must stay 18/18)
- `... -m pytest -q`
- Headless notebook run: `nbclient`. Typed input is impossible headless, so the clarification example stays paused unless the user provides answers.
