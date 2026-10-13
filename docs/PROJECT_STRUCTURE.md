# Project structure and teammate naming alignment

Reference: [Junliang-Lyu/statistical-analysis-assistant at `b7eff1c4a8035f196ac4bfc73ef3fe88956dadb5`](https://github.com/Junliang-Lyu/statistical-analysis-assistant/tree/b7eff1c4a8035f196ac4bfc73ef3fe88956dadb5).
The reference's main branch was checked on 2026-10-12. This project uses the same primary
folder and entry-point names while retaining its own two-model workflow and data policies.

## Current layout

```text
langgraph_visualization/
├── README.md
├── demo.py
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
│   └── tutoring_scores_messy_synthetic.csv
├── artifacts/
│   ├── graph.png
│   ├── graph.mmd
│   ├── verification/             # historical evidence and current layout audit
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
│   └── other offline tests
├── data/                         # preserved pre-layout synthetic CSVs
├── r/                            # frozen v1 tools
├── legacy/                       # unfinished R v2 reference/bridge
├── stats_assistant_graph.ipynb    # frozen Module 6 v1
└── stats_assistant_langgraph.png  # frozen Module 6 v1 diagram
```

`demo.ipynb` imports the local `stat_assistant` package. The dated assignment notebook
embeds this project's source and datasets so its two-file deliverable can be run with the
Python dependencies installed. Both canonical notebooks have fresh, labelled mock outputs.
Their mock agents are rule-based stand-ins; this is execution evidence for the workflow
and calculations rather than measured real-model semantic accuracy.

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
this project's fixed-seed Python dataset. They retain their descriptive filenames instead
of adopting the teammate's different `student_study_demo.csv` dataset name. The teammate's
synthetic data, saved outputs and assignment content are not the source of our examples.

Supporting modules such as schemas, settings, runtime, report checks and the tool bridge
remain separate files because the two-model/user-confirmation implementation uses them.
`scripts/run_notebook.py`, `scripts/notebook_artifacts.py`, data-generation helpers and
`tests/test_reports.py` remain useful extensions to the shared layout. Names that identify
frozen v1 material are kept for provenance.

## Local browser interface

The browser interface uses the teammate's root `ui_server.py` and `ui/index.html`,
`ui/app.js`, `ui/style.css` filenames. Its adapter invokes our existing 17-node
workflow and exposes our own result schema and user-confirmation policy. It does
not replace the statistical package or change the submitted notebooks and midterm
artifacts.

Run `python ui_server.py --port 8765` from the project directory and open
[http://127.0.0.1:8765](http://127.0.0.1:8765). The standard-library server binds to
`127.0.0.1`. The browser polls analysis jobs, offers explicitly labelled mock and
real modes, and presents our synthetic cases plus a CSV upload with reviewed
study/variable metadata JSON. Data corrections, exclusions and verification need
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

The layout refactor updates imports, relative paths, builders, entry points and documentation.
It keeps the four statistical methods and the existing human-confirmation/review policies.
The subsequent browser interface adapts the teammate's layout to our own workflow.
Deployment setup, date filtering, extra regression diagnostics and the 31-case
benchmark remain outside this implementation. See [TEAM_ALIGNMENT.md](TEAM_ALIGNMENT.md)
for the implementation comparison and [VERIFICATION.md](VERIFICATION.md) for executed
evidence.
