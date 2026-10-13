# LangGraph coursework package — 2026-10-12

The current deliverables use the teammate's dated assignment layout and filenames:

- `langgraph/LangGraph_Submission.ipynb`: standalone notebook with this project's embedded Python implementation, synthetic datasets, actual graph rendering and node/edge/agent-handoff explanation.
- `langgraph/graph.png`: PNG exported from the compiled graph that the standalone notebook executes.

The notebook contains a fresh, explicitly labelled **mock-mode** execution. The statistical
calculations and LangGraph are real; its named rule-based agents are test stand-ins. These
saved outputs demonstrate mechanics and numerical behavior, not real-model semantic
accuracy. The examples retain this project's own data and workflow, including two-model
roles, parallel diagnostics, user-confirmation interrupts and bounded review. The package
does not contain the teammate's data or saved model outputs.

## Inspect or rerun

Open the notebook in Jupyter or a compatible notebook viewer. Install the dependencies
listed in the root `requirements-lock.txt` in a Python 3.13 environment; the notebook embeds
the implementation and data, so it does not need the project `stat_assistant/` or `examples/`
folders alongside it. Run cells in order from an otherwise empty working directory.
The notebook materializes its embedded source/data for execution and exports its graph.
PNG rendering requires access to the Mermaid renderer. A saved PNG is included for inspection.

From the repository, regenerate and execute with:

```powershell
python build_notebook.py
python scripts/run_notebook.py --mode mock --submission
```

Rebuilding clears saved outputs. The runner's `--output` option saves an alternate executed
notebook instead of replacing this canonical copy. A deliberate `--mode real --submission`
run requires two distinct locally configured models and records its selected mode. This
layout refactor did not conduct a new real-model run.

The messy-data case intentionally pauses for a human in headless execution. Any resumed
answers must come from verified user information; a scripted test answer is not an actual
user decision. A 99% confidence follow-up retains alpha at 0.05. Re-explanation reuses
validated statistics, and unsupported designs stop visibly.

## Artifact provenance

Root `demo.ipynb` is the project-linked teaching notebook. The standalone notebook is
generated from our current source by root `build_notebook.py`. Both use the same workflow;
each diagram is exported from its own executed compiled graph.

Earlier v2 real-run evidence is retained separately under `artifacts/verification/`,
including `python_v2_pre_layout.ipynb`, the full initial run and targeted rerun JSONs.
Those development runs predate this naming/layout change and are not one fresh real
execution of this assignment notebook. Frozen Module 6 v1 remains in its original root
notebook/image and `data/`/`r/` files. Verification and limits are documented in
[docs/VERIFICATION.md](../../docs/VERIFICATION.md).
