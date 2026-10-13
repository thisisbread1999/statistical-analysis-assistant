# Continue this project — current Python handoff

Reply to the user in Chinese. Write code, notebook text and technical documentation in English.
The user's instructions on 2026-10-12 made active v2 all Python and requested naming/layout
alignment with [the teammate's repository](https://github.com/Junliang-Lyu/statistical-analysis-assistant/tree/b7eff1c4a8035f196ac4bfc73ef3fe88956dadb5).
The reviewed reference is `b7eff1c4a8035f196ac4bfc73ef3fe88956dadb5`. Historical R-only
requirements in `HANDOFF_PROMPT_ORIGINAL_R.md` are retained as context.

## Working locations

- Project: `C:\Users\62703\OneDrive\Desktop\SMU\26fall\agentic ai\langgraph_visualization`.
- Python: `C:\Users\62703\.venvs\langgraph-viz\Scripts\python.exe`.
- Branch recorded at the earlier handoff: `codex/python-v2`; frozen v1 tag: `module6-submission-v1`. Inspect current state before assuming the branch is unchanged.
- Model A: `ollama:qwen3:8b`; Model B: `ollama:gemma3:12b`. Configuration is in ignored `.env`.
- Read `README.md`, `docs/PROJECT_STRUCTURE.md`, `docs/PYTHON_TOOLS_SPEC.md`, `docs/TEAM_ALIGNMENT.md` and `docs/VERIFICATION.md` first.

## Implemented architecture and names

`stat_assistant/` implements the 17-node graph, four NumPy/SciPy methods, parallel semantic
and statistical diagnostics, explicit human interrupts, bounded revisions, protected
statistical fields, model-call limits and same-thread follow-ups. Two distinct underlying
models remain required; evaluation has not replaced the graph or reviewer. Public workflow
and statistical modules are `stat_assistant/workflow.py` and `stat_assistant/tools.py`.

Accepted OLS results and diagnostics share `regression_diagnostics`, containing original
record IDs/row numbers, leverage, Cook's distance, screening thresholds, approximate
Koenker studentized Breusch-Pagan LM, and structured warnings. Cook's threshold is
`4/n`; leverage's is `2p/n = 4/n` with `p = 2` (intercept and slope). BP uses
`n * auxiliary_R_squared` for residual-squared on intercept+x and an asymptotic
chi-square(1) p-value, not a robust covariance correction. Numerically unit leverage
produces null Cook's distance; unavailable auxiliary tests produce null LM/p-value
with warnings. Do not invent huge Cook values by nudging singular denominators.
Warnings do not block inference, add verification findings, exclude rows, or change
OLS estimates/p-values/intervals. Existing IQR verification still needs explicit
permitted user actions. Diagnostic warnings become required report limitations and
appear in the UI; the program rejects omitted required limitations. The exact schema
and null behavior are in `docs/PYTHON_TOOLS_SPEC.md`.

Use root `demo.py`, project-linked `demo.ipynb`, root `build_notebook.py` and active CSVs in
`examples/`. `artifacts/graph.png` and `artifacts/graph.mmd` must come from the compiled
workflow used by the demo. `requirements.txt` includes exact `requirements-lock.txt` pins.
Ignored runtime files go to `artifacts/runtime/`. Existing v1 `outputs/` stays ignored.

The standalone assignment is
`assignments/2026-10-12/langgraph/LangGraph_Submission.ipynb` with `graph.png`. It embeds
our implementation and datasets selected by the builder. Historical layout-stage
canonical notebooks were executed in mock mode and labelled accordingly. Historical
real-run evidence is preserved separately at `artifacts/verification/`, including
`python_v2_pre_layout.ipynb` and byte-preserved JSON evidence. Read current saved outputs
and `docs/VERIFICATION.md` for later execution outcomes; the naming refactor itself
did not conduct a fresh real-model run.

Preserve the frozen v1 notebook/image, all pre-layout CSVs in `data/` and `r/stats_tools.R`.
The unfinished R v2 extension and bridge in `legacy/` are historical references. Preserve
the original R handoff/specification and `docs/V1_README.md`. The five original project
CSVs retain their provenance. An additional 31 frozen source benchmark CSV/JSON cases
were adopted from `b7eff1c`, with source declarations and source README scores preserved
as historical provenance. Our adapter and new result artifacts are separate; do not
present source scores as our outcomes. Date filtering remains unsupported.

Root `ui_server.py` and `ui/` expose ten scenarios: eight use the original five CSVs,
and two use source boundary `regression_influential.csv` and
`regression_heteroscedastic.csv`. The browser displays protected results, diagnostic
warnings and limitations, and still pauses for outstanding record verification.

## Current evaluation entry points

- `benchmark_suite.py`: 31 frozen source cases in `examples/benchmark_v2/`, with
  project-specific policy declarations/checksums in `examples/benchmark_v2_adapted/`.
  Offline mode uses explicitly labelled prespecified stand-ins and real Python
  calculations. Live mode runs this project's two distinct configured models; gold
  source plans are not live planning inputs. Preserve deliberate primary pauses,
  unresolved-design/target stops, unsupported date filtering and our minimum of
  three OLS pairs. Optional `--resume-fixtures` continuations use predeclared labelled
  synthetic TEST recipes, not real human verification.
- `interpretation_benchmark.py`: 16 controlled challenges in
  `examples/interpretation_checks/` (four valid templates and twelve authored
  mutations). Statistics are recomputed, and program checks and reviewer B are
  evaluated independently. Live mode calls Model B on controlled drafts; Model A
  is not called, so this is detector coverage rather than Model A generation accuracy.
- Newly computed evidence belongs to separate offline/live run directories under
  `artifacts/benchmark_v2/` and `artifacts/interpretation_checks/`. Keep configurations,
  per-case inputs/results/checks/verdicts, failures and summaries. Never overwrite
  existing run directories or import source score totals. Human review fields remain
  blank until independent labels are actually supplied. No evaluation trains or
  changes model weights. Do not promise current pass totals or live scores before
  inspecting the saved run and verification record.

## Rules to keep

- Model A and B must be distinct underlying models. Label mock stand-ins explicitly.
- Statistical tools, program checks and save steps are not LLM agents.
- Never automatically edit, delete, impute or exclude observations. Require an explicit user selection of a currently permitted action. Source or reason is optional for verification, exclusion and correction; correction still requires a valid replacement value. Preserve the source CSV, write new versions for approved data changes, and log actions, affected cells/records, old/new values and any supplied note. Store an omitted reason as an empty string, display "No note provided" in the UI, and never invent a reason. Tests may use labelled TEST INPUT fixtures.
- Welch does not require equal variance. Shapiro-Wilk is descriptive rather than a method switch. Do not change the estimand to rescue a failed assumption check.
- OLS accepts at least three identifiable nondegenerate pairs under current computational policy; this is not a reliability guarantee. Keep the Koenker BP approximation and influence diagnostics descriptive, and retain required warning limitations.
- Compute active statistics in Python. Do not tune synthetic data to desired p-values.
- Keep confidence level separate from alpha. Avoid causal claims for observational analyses.
- Keep review/check failures visible; after one revision, stop rather than loop indefinitely.
- Do not present offline stand-ins as live LLM evaluation, numeric agreement as human semantic accuracy, or smoke runs as a completed benchmark. Controlled interpretation labels are authored test expectations, not human ratings.
- Keep secrets local. A public push, PR or release requires the user's authorization.

## Commands

```powershell
python demo.py --mode mock
python -m pytest -q --basetemp=artifacts/pytest
python scripts/run_notebook.py --mode mock
python scripts/run_notebook.py --mode mock --submission
python benchmark_suite.py --list
python benchmark_suite.py --mode offline --output offline_mechanics_new
python benchmark_suite.py --mode offline --resume-fixtures --output offline_fixture_continuation_new
python interpretation_benchmark.py --mode offline --name offline_interpretation_new
```

The CLI also accepts `--mode real` or `--live`, `--csv`, `--question`, `--design-json` and
`--interactive`. An external CSV requires `--design-json` pointing to confirmed design metadata;
never infer independence or study design from its values.
The notebook runner accepts `--mode real` and `--output`. `python build_notebook.py`
regenerates canonical notebook source and clears saved outputs; execute after rebuilding.
Headless messy-data execution intentionally pauses. Do not invent user answers.

Evaluation output names must be new. `benchmark_suite.py --mode live` accepts optional
`--model-a`/`--model-b`; `interpretation_benchmark.py --mode live` uses the configured
reviewer. Run those only within the authorized evaluation scope, preserve any failed
or incomplete case, and keep their evidence separate from offline runs. No live
score or human accuracy claim follows merely from the presence of these commands.

Legacy `tests/run_checks.py` still requires R/jsonlite. On this machine its subprocess may
need `R_LIBS_USER=C:\Users\62703\AppData\Local\R\win-library\4.4` to see the existing
library. Active Python code needs no R environment.
