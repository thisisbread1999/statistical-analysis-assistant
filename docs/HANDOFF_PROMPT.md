# Continue this project — current Python handoff

Reply to the user in Chinese. Write code, notebook text and technical documentation in English.
The user's instructions on 2026-10-12 made active v2 all Python and requested naming/layout
alignment with [the teammate's repository](https://github.com/Junliang-Lyu/statistical-analysis-assistant/tree/b7eff1c4a8035f196ac4bfc73ef3fe88956dadb5).
The reviewed reference is `b7eff1c4a8035f196ac4bfc73ef3fe88956dadb5`. Historical R-only
requirements in `HANDOFF_PROMPT_ORIGINAL_R.md` are retained as context.

## Working locations

- Project: `C:\Users\62703\OneDrive\Desktop\SMU\26fall\agentic ai\langgraph_visualization`.
- Python: `C:\Users\62703\.venvs\langgraph-viz\Scripts\python.exe`.
- Active branch: `codex/python-v2`; v1 tag: `module6-submission-v1`.
- Model A: `ollama:qwen3:8b`; Model B: `ollama:gemma3:12b`. Configuration is in ignored `.env`.
- Read `README.md`, `docs/PROJECT_STRUCTURE.md`, `docs/PYTHON_TOOLS_SPEC.md`, `docs/TEAM_ALIGNMENT.md` and `docs/VERIFICATION.md` first.

## Implemented architecture and names

`stat_assistant/` implements the 17-node graph, four NumPy/SciPy methods, parallel semantic
and statistical diagnostics, explicit human interrupts, bounded revisions, protected
statistical fields, model-call limits and same-thread follow-ups. Its public workflow and
statistical modules are `stat_assistant/workflow.py` and `stat_assistant/tools.py`.

Use root `demo.py`, project-linked `demo.ipynb`, root `build_notebook.py` and active CSVs in
`examples/`. `artifacts/graph.png` and `artifacts/graph.mmd` must come from the compiled
workflow used by the demo. `requirements.txt` includes exact `requirements-lock.txt` pins.
Ignored runtime files go to `artifacts/runtime/`. Existing v1 `outputs/` stays ignored.

The standalone assignment is
`assignments/2026-10-12/langgraph/LangGraph_Submission.ipynb` with `graph.png`. It embeds
our own implementation and synthetic data. Canonical notebooks were freshly executed in
mock mode and label that mode. Historical real-run evidence is preserved separately at
`artifacts/verification/`, including `python_v2_pre_layout.ipynb` and the byte-preserved
JSON evidence. The naming refactor did not conduct a fresh real-model run.

Preserve the frozen v1 notebook/image, all pre-layout CSVs in `data/` and `r/stats_tools.R`.
The unfinished R v2 extension and bridge in `legacy/` are historical references. Preserve
the original R handoff/specification and `docs/V1_README.md`. Layout alignment does not
mean adopting the teammate's UI, date filtering, benchmark data or saved results.

## Rules to keep

- Model A and B must be distinct underlying models. Label mock stand-ins explicitly.
- Statistical tools, program checks and save steps are not LLM agents.
- Never automatically edit, delete, impute or exclude observations. Require a verified user answer and reason, preserve the source file, and log confirmed changes. Tests may use labelled TEST INPUT fixtures.
- Welch does not require equal variance. Shapiro-Wilk is descriptive rather than a method switch. Do not change the estimand to rescue a failed assumption check.
- Compute active statistics in Python. Do not tune synthetic data to desired p-values.
- Keep confidence level separate from alpha. Avoid causal claims for observational analyses.
- Keep review/check failures visible; after one revision, stop rather than loop indefinitely.
- Do not present mock tests as LLM evaluation, numeric agreement as semantic accuracy, or smoke runs as a benchmark.
- Keep secrets local. A public push, PR or release requires the user's authorization.

## Commands

```powershell
python demo.py --mode mock
python -m pytest -q --basetemp=artifacts/pytest
python scripts/run_notebook.py --mode mock
python scripts/run_notebook.py --mode mock --submission
```

The CLI also accepts `--mode real` or `--live`, `--csv`, `--question`, `--design-json` and
`--interactive`. An external CSV requires `--design-json` pointing to confirmed design metadata;
never infer independence or study design from its values.
The notebook runner accepts `--mode real` and `--output`. `python build_notebook.py`
regenerates canonical notebook source and clears saved outputs; execute after rebuilding.
Headless messy-data execution intentionally pauses. Do not invent user answers.

Legacy `tests/run_checks.py` still requires R/jsonlite. On this machine its subprocess may
need `R_LIBS_USER=C:\Users\62703\AppData\Local\R\win-library\4.4` to see the existing
library. Active Python code needs no R environment.
