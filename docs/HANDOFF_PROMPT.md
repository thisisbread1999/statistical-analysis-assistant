# Continue this project — current Python v2 handoff

Reply to the user in Chinese. Write code, notebook text and technical documentation in English.
The user's instruction on 2026-10-12 changed the active v2 implementation to **all Python**,
aligned with https://github.com/Junliang-Lyu/statistical-analysis-assistant. This supersedes
R-only requirements in `HANDOFF_PROMPT_ORIGINAL_R.md`, which is retained as historical context.

## Working locations
- Project: `C:\Users\62703\OneDrive\Desktop\SMU\26fall\agentic ai\langgraph_visualization`
- Python: `C:\Users\62703\.venvs\langgraph-viz\Scripts\python.exe`
- Active branch: `codex/python-v2`; v1 tag: `module6-submission-v1`.
- Model A: `ollama:qwen3:8b`; Model B: `ollama:gemma3:12b`. Config in ignored `.env`.
- Read README, `docs/PYTHON_TOOLS_SPEC.md`, `docs/TEAM_ALIGNMENT.md` and `docs/VERIFICATION.md` first.

## Implemented architecture
The executable `stats_assistant` package implements the 17-node graph, four SciPy methods,
parallel semantic/statistical diagnostics, explicit human interrupts, bounded revisions,
protected statistical fields, error/model-call limits and same-thread follow-ups.
The notebook and PNG are `stats_assistant_v2.ipynb` and `stats_assistant_v2_langgraph.png`.
Its diagram must always come from the same compiled graph used by its examples.
`docs/VERIFICATION.md` records actual test/model evidence and anything unverified.

Preserve the frozen v1 notebook, image, four original CSVs and R tool. The unfinished R v2
extension/bridge are historical files in `legacy/` and are not dependencies of active v2.

## Rules to keep
- Model A and B must be distinct underlying models. Mock stand-ins must be labelled.
- Statistical tools, program checks and save steps are not LLM agents.
- Never auto-edit, delete, impute or exclude observations. Require a user answer and reason,
  preserve the source file, and log confirmed changes. Tests may use explicit TEST INPUT fixtures.
- Welch does not require equal variance. Shapiro-Wilk is descriptive, not an automatic
  method switch. Do not change the estimand to rescue a failed assumption check.
- Compute all v2 statistics in Python. Do not tune synthetic data to desired p-values.
- Keep confidence level separate from alpha. Never make causal claims from an observational analysis.
- Keep reviewer and program failures visible; after one revision stop rather than loop indefinitely.
- Do not present mock tests as LLM evaluation, or smoke runs as an accuracy benchmark.
- Do not read, print, commit or share secrets. Ask the user before a push, PR or public release.

## Commands
```
python -m pytest -q --basetemp=outputs/pytest
python scripts/run_notebook.py --mode mock
python scripts/run_notebook.py --mode real
```
`build_notebook.py` regenerates the notebook and clears outputs: rerun after any use.
Headless execution intentionally leaves messy-data clarification paused. Do not invent answers.
Legacy `tests/run_checks.py` still requires R/jsonlite; on this machine its subprocess may
need `R_LIBS_USER=C:\Users\62703\AppData\Local\R\win-library\4.4` to see the existing library.
