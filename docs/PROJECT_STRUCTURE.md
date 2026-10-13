# Project structure and teammate naming alignment

Reference: [Junliang-Lyu/statistical-analysis-assistant at `b7eff1c4a8035f196ac4bfc73ef3fe88956dadb5`](https://github.com/Junliang-Lyu/statistical-analysis-assistant/tree/b7eff1c4a8035f196ac4bfc73ef3fe88956dadb5).
Historical alignment check: the reference's main branch was checked on 2026-10-12. This project uses the same primary
folder and entry-point names while retaining its own two-model workflow and data policies.

## Current layout

```text
langgraph_visualization/
├── README.md
├── demo.py
├── benchmark_suite.py            # 31 frozen source cases + our policy adapter
├── interpretation_benchmark.py   # 16 controlled interpretation challenges
├── ui_server.py
├── ui/
│   ├── index.html
│   ├── app.js
│   └── style.css
├── demo.ipynb
├── build_notebook.py
├── requirements.txt
├── requirements-lock.txt
├── .env.example
├── stat_assistant/
│   ├── agents.py
│   ├── workflow.py
│   ├── tools.py
│   ├── __init__.py
│   └── supporting Python modules
├── examples/
│   ├── README.md
│   ├── students_synthetic.csv
│   ├── tutoring_scores_clean_synthetic.csv
│   ├── tutoring_scores_no_difference_synthetic.csv
│   ├── tutoring_scores_unequal_variance_synthetic.csv
│   ├── tutoring_scores_messy_synthetic.csv
│   ├── benchmark_v2/             # 31 frozen source CSV/JSON fixtures + manifest
│   ├── benchmark_v2_adapted/     # our policy declarations and source checksums
│   └── interpretation_checks/    # 4 valid templates + 12 authored mutations
├── artifacts/
│   ├── graph.png
│   ├── graph.mmd
│   ├── verification/             # historical evidence and current layout audit
│   ├── benchmark_v2/             # our evaluation runs, offline/live separated
│   ├── interpretation_checks/    # our detector evidence, offline/live separated
│   ├── pytest/                   # ignored test temporary files
│   └── runtime/                  # ignored generated state/logs/temp files
├── assignments/
│   └── 2026-10-12/
│       ├── README.md
│       ├── midterm/
│       │   ├── Midterm_Presentation_Final.pptx
│       │   ├── Midterm_Writeup.docx
│       │   └── Midterm_Writeup.pdf
│       └── langgraph/
│           ├── LangGraph_Submission.ipynb
│           └── graph.png
├── docs/
├── scripts/
├── tests/
│   ├── test_ui_server.py
│   ├── test_regression_diagnostics.py
│   ├── test_regression_review.py
│   ├── test_benchmark_suite.py
│   ├── test_interpretation_benchmark.py
│   └── other offline tests
├── data/                         # preserved pre-layout synthetic CSVs
├── r/                            # frozen v1 tools
├── legacy/                       # unfinished R v2 reference/bridge
├── stats_assistant_graph.ipynb    # frozen Module 6 v1
└── stats_assistant_langgraph.png  # frozen Module 6 v1 diagram
```

`demo.ipynb` imports the local `stat_assistant` package. The dated assignment notebook
embeds this project's source and the datasets selected by `build_notebook.py` so its
two-file deliverable can run with the Python dependencies installed. Historical
layout-stage notebook execution produced labelled mock outputs. Mock agents are
rule-based stand-ins; those outputs demonstrate workflow and calculations rather
than measured real-model semantic accuracy. Read the current saved outputs and
`docs/VERIFICATION.md` for later execution evidence.

## Rename and location mapping

| Previous active path | Current canonical path | Reason |
|---|---|---|
| `stats_assistant/` | `stat_assistant/` | Match the teammate's package name. |
| `stats_assistant/graph.py` | `stat_assistant/workflow.py` | Match the workflow module name. |
| `stats_assistant/statistics.py` | `stat_assistant/tools.py` | Match the statistical-tool module name. |
| `scripts/build_notebook.py` | `build_notebook.py` | Match the root notebook builder entry point. |
| `stats_assistant_v2.ipynb` | `demo.ipynb` | Match the root teaching notebook name. |
| `stats_assistant_v2_langgraph.png` | `artifacts/graph.png` | Match the graph artifact location and name. |
| Graph Mermaid source | `artifacts/graph.mmd` | Export directly from the same compiled workflow. |
| `docs/verification/*.json` | `artifacts/verification/*.json` | Preserve historical JSON evidence byte for byte in the artifact folder. |
| Pre-layout v2 notebook with historical outputs | `artifacts/verification/python_v2_pre_layout.ipynb` | Preserve historical output provenance before producing the fresh canonical notebooks. |
| Active CSVs under `data/` | Copies under `examples/` | Match the example folder while retaining the original filenames and all source CSVs. |
| Active runtime `outputs/` | `artifacts/runtime/` | Keep generated execution files together and ignored by Git. |
| Pins in `requirements.txt` | `requirements-lock.txt`, included by `requirements.txt` | Match the dependency file convention. |
| Project-specific v2 deliverable | `assignments/2026-10-12/langgraph/` | Match the dated assignment convention. |
| `tests/test_statistics.py` | `tests/test_four_methods.py` | Match the teammate's four-method test name. |
| `tests/test_workflow.py` | `tests/test_mvp.py` | Match the teammate's workflow/MVP test name. |

The four tutoring datasets originated in this project's v1. `students_synthetic.csv` is
this project's fixed-seed Python dataset. These five original CSVs retain their descriptive
filenames instead of adopting the teammate's `student_study_demo.csv` name. The additional
31 source benchmark CSV/JSON fixtures in `examples/benchmark_v2/` retain provenance from
commit `b7eff1c4a8035f196ac4bfc73ef3fe88956dadb5`. Their source declarations, README score
statements and checksums are preserved; our adapter and newly computed outputs are separate.
No teammate output score or model training weight is used as our own result.

Supporting modules such as schemas, settings, runtime, report checks and the tool bridge
remain separate files because the two-model/user-confirmation implementation uses them.
`scripts/run_notebook.py`, `scripts/notebook_artifacts.py`, data-generation helpers and
`tests/test_reports.py` remain useful extensions to the shared layout. Names that identify
frozen v1 material are kept for provenance.

## Evaluation entry points and evidence

`benchmark_suite.py` runs the 31 frozen cases with this project's 17-node graph,
four methods, two distinct live models and explicit confirmation policy. The
adapter in `examples/benchmark_v2_adapted/` documents expected pauses and stops,
unsupported date filtering, source contrast conventions and our minimum of three
regression pairs. Source gold plans are confined to labelled offline mechanics
and the evaluator. Optional synthetic TEST fixture continuations retain the primary
pause; they are not human decisions.

`interpretation_benchmark.py` recomputes Python statistics for 16 controlled drafts:
four valid templates and twelve authored mutations. It measures program-check and
reviewer detector behavior; live mode calls Model B on controlled drafts, without
calling Model A. Its categories are adapted from the same reviewed source snapshot,
but source detector scores are not imported.

Each new evaluation run writes its own configuration, per-case evidence, failures,
summary and report beneath `artifacts/benchmark_v2/` or
`artifacts/interpretation_checks/`. Offline and live runs remain separately labelled
and saved, and existing evidence directories are not overwritten. The benchmark's
human-review sheet has blank labels for later independent review. Mechanical/numeric
checks and controlled detector coverage do not supply human semantic accuracy, and
these evaluations do not train or alter model weights. This document describes
capabilities rather than current pass totals or live scores.

## Local browser interface

The browser interface uses the teammate's root `ui_server.py` and `ui/index.html`,
`ui/app.js`, `ui/style.css` filenames. Its adapter invokes our existing 17-node
workflow and exposes our own result schema and user-confirmation policy. It does
not replace the statistical package or change the submitted notebooks and midterm
artifacts.

Run `python ui_server.py --port 8765` from the project directory and open
[http://127.0.0.1:8765](http://127.0.0.1:8765). The standard-library server binds to
`127.0.0.1`. The browser polls analysis jobs, offers explicitly labelled mock and
real modes, and presents ten scenarios plus a CSV upload with reviewed
study/variable metadata JSON. Eight scenarios use the five original project CSVs;
two use `benchmark_v2/boundary/regression_influential.csv` and
`regression_heteroscedastic.csv`. Regression results show row-linked Cook's
distance/leverage, approximate Koenker Breusch-Pagan diagnostics and required
warnings/limitations. Data corrections, exclusions and verification need
explicit user selections of currently permitted actions before inference can
continue. Source or reason is optional; corrections still require valid replacement
values. The source CSV is retained, approved data changes create new versions, and
audit records include the action, affected cells/records, old/new values and notes
when supplied. Omitted notes remain empty and appear as "No note provided" in the
browser; the system does not generate reasons.

Session graph memory clears when the server restarts. Uploads and session files
are written to ignored `artifacts/runtime/ui/`; core correction versions and audit
logs remain under ignored `artifacts/runtime/`. `tests/test_ui_server.py` contains
the local UI adapter checks; executed verification belongs in
[VERIFICATION.md](VERIFICATION.md).

## Change scope

The historical layout refactor updated imports, relative paths, builders, entry points
and documentation while retaining the four methods and human-confirmation/review
policies. Subsequent work adds the browser adapter, frozen-case evaluation,
controlled interpretation challenges and regression diagnostics. Cook's screening
threshold is `4/n`; leverage uses `2p/n = 4/n` with intercept and slope (`p = 2`).
Warnings are nonblocking, never delete records or change ordinary OLS inference,
and become required report limitations. Numerically unavailable measures are
explicitly displayed as unavailable. Deployment setup and date filtering remain
outside this implementation. See [TEAM_ALIGNMENT.md](TEAM_ALIGNMENT.md) for the
comparison, [PYTHON_TOOLS_SPEC.md](PYTHON_TOOLS_SPEC.md) for the diagnostic schema,
and [VERIFICATION.md](VERIFICATION.md) for executed evidence.
