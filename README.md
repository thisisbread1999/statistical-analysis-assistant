# Agentic Statistical Analysis Assistant — Python v2

A course-scale statistical assistant with **two distinct LLMs**, **17 real LangGraph nodes**,
and **Python/SciPy statistical tools**. Model A plans and explains; Model B reviews against
original evidence. The user resolves data issues before inference. No R installation is
required for v2. No model training or paid API is required when using installed local Ollama models.

## Open these files

| File | Purpose |
|---|---|
| `stats_assistant_v2.ipynb` | Main v2 deliverable: executable graph, actual diagram, node/edge/handoff explanation and examples |
| `stats_assistant_v2_langgraph.png` | LangGraph-rendered image from the same graph that runs the examples |
| `stats_assistant/` | Python package: agents, graph, statistics, report guards and session helpers |
| `docs/TEAM_ALIGNMENT.md` | Verified alignment with the teammate's repository and intentional differences |
| `docs/PYTHON_TOOLS_SPEC.md` | Tool contract and specific statistical/data checks |
| `docs/VERIFICATION.md` | What was actually tested, including limitations of the evidence |
| `tests/test_*.py` | Offline pytest tests; LLMs are explicitly mocked |
| `scripts/` | Reproducible synthetic-data generation, notebook generation and headless execution |

The original Module 6 v1 is preserved at Git tag `module6-submission-v1`. Its notebook,
diagram, four original CSV files and R tool are retained. `docs/V1_README.md` is its historical
setup guide. The unfinished R v2 extension and bridge are archived in `legacy/`; active v2
code does not import or execute them.

## Run on Windows

From this project folder:

```powershell
py -m venv "$env:USERPROFILE\.venvs\langgraph-viz"
& "$env:USERPROFILE\.venvs\langgraph-viz\Scripts\python.exe" -m pip install -r requirements.txt
```

If that environment already exists, reuse it. Copy `.env.example` to `.env` only if `.env`
does not already exist. Never upload API keys. Choose:

- `LLM_MODE=mock`: fully offline orchestration tests using named rule-based stand-ins. Statistical calculations remain real.
- `LLM_MODE=real`: two actual models. The defaults are `ollama:qwen3:8b` for A and `ollama:gemma3:12b` for B. Start Ollama and install those models (`ollama pull qwen3:8b`, `ollama pull gemma3:12b`) if needed.
- `LLM_MODE=auto`: use real when the configured model setup is available, otherwise mock. The notebook displays the selected mode explicitly; it never silently substitutes a mock after a real call fails.

Model names, local endpoint, context size, output token cap and timeout are configurable in
`.env.example`. Identical provider/model names, default-tag aliases and identical Ollama
weight digests are rejected for the A/B pair. Cloud provider adapters are optional and have
not been validated with live cloud calls in this v2 run. Google support additionally needs
its provider package; it is not part of the pinned course runtime.

```powershell
& "$env:USERPROFILE\.venvs\langgraph-viz\Scripts\python.exe" -m jupyter lab stats_assistant_v2.ipynb
```

Use **Restart Kernel and Run All** for a fresh run; examples use fixed thread IDs and cannot
be started twice in the same graph session. The diagram cell requires internet access for
Mermaid rendering. The notebook's messy-data example remains paused in headless mode.
Set `INTERACTIVE = True` in that cell to enter your own verified answers in Jupyter.

```powershell
# Offline tests; the explicit temporary folder also works in restricted Windows sandboxes.
& "$env:USERPROFILE\.venvs\langgraph-viz\Scripts\python.exe" -m pytest -q --basetemp=outputs/pytest
# Execute and save all notebook outputs (select mock or real explicitly).
& "$env:USERPROFILE\.venvs\langgraph-viz\Scripts\python.exe" scripts/run_notebook.py --mode mock
& "$env:USERPROFILE\.venvs\langgraph-viz\Scripts\python.exe" scripts/run_notebook.py --mode real
```

`python scripts/build_notebook.py` rebuilds notebook source and **clears saved outputs**.
Use it only when intentionally updating the notebook, then rerun it. CI is configured for
Python 3.13 and mock pytest; it has not run on GitHub until the branch is pushed.

## What the assistant does

1. **Plan:** map the question to variable roles, estimand and hypotheses. Supported methods are two-sided Welch t, Pearson correlation, chi-square independence and simple OLS with an intercept.
2. **Diagnose in parallel:** Model A checks semantics/design/goal alignment from a shared descriptive summary; Python checks raw values and method-specific computability. The branches join before routing.
3. **Clarify if needed:** missing scores, invalid labels, impossible values or unusual observations are shown to the user. Each correction/exclusion/verification needs an explicit answer and reason. The original file stays unchanged. The system never fills in missing values or drops rows silently.
4. **Compute and explain:** Python produces the numerical result. Model A writes a placeholder-based explanation. A program checks required values, common field bindings and decision consistency; Model B checks the rendered meaning against original evidence. One report revision is allowed, then delivery or an issue notice.
5. **Follow up:** a changed confidence level reruns statistics; re-explanation reuses validated numbers; a new question replans and rechecks. A changed file cannot reuse stale diagnostics. Metadata-only changes keep the correction history. Memory currently lasts only for the running graph process.

At most one plan revision, one report revision, two answered clarification rounds and fifteen
model calls per request are permitted. Invalid clarification input is re-asked without changing
data. A tool/model exception is recorded and routed to an issue notice. These limits are policy
settings, not statistical validity guarantees.

The method is chosen from the question and data roles, not from whether its p-value is
significant. Welch does not assume equal variances. Normality diagnostics are descriptive,
not a switch to a rank test. A sparse contingency table stops because an exact-test fallback
is outside this stage. Correlations and observational group differences do not establish
causation. A new confidence level does not change alpha (fixed at 0.05).

## Scope and evaluation

This is a runnable course prototype, not a general statistical consulting product. It does
not implement automatic filtering, missing-data imputation, paired/clustered models, multiple
regression, arbitrary code generation, causal adjustment or persistent multi-user storage.
For “only last year's data”, supply a new CSV and run a new analysis.

Placeholder checks constrain numeric output, but cannot prove arbitrary prose is correct.
Two different LLMs can still share errors. Keep a separate human-scored benchmark with clean,
ambiguous and failing cases, checking method/estimand alignment, effect and uncertainty,
missingness disclosure, non-significance wording and causal restraint. Human evaluation scores
the whole system; it does not train either model. See the verification record for measured
results rather than assuming these demos establish accuracy.
