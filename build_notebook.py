from pathlib import Path
import textwrap
import nbformat as nbf
from scripts.notebook_artifacts import write_notebooks

ROOT = Path(__file__).resolve().parent
nb = nbf.v4.new_notebook()
nb.metadata = {"kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
               "language_info": {"name": "python", "version": "3.13"}}
cells = []
def md(text): cells.append(nbf.v4.new_markdown_cell(textwrap.dedent(text).strip()))
def code(text): cells.append(nbf.v4.new_code_cell(textwrap.dedent(text).strip()))

md('''
# Agentic Statistical Analysis Assistant — Python v2
**Jingcheng Zhou and Junliang Lyu · Module 6: Visualize Your Multi-Agent LangGraph**

This notebook compiles, visualizes and runs one real **17-node LangGraph StateGraph**.
Model A plans and explains; a different Model B reviews. Python/SciPy performs all v2
statistics and deterministic data checks. No R installation is needed for v2.
All example datasets are **synthetic**. Results are computed when cells run.

Run from this project folder after `pip install -r requirements.txt`. Configure `.env`
from `.env.example`: `LLM_MODE=real` uses two distinct local Ollama models; `mock` uses
explicitly labelled rule-based stand-ins to test orchestration. `auto` selects real when
configuration is available, otherwise mock. No fine-tuning or model training occurs.
The saved outputs state the actual mode. Human evaluation of report quality remains a
separate benchmark activity; these smoke examples are not an accuracy estimate.
''')
code('''
import os, sys, json, inspect
from pathlib import Path
from IPython.display import Image, Markdown, display

PROJECT = next((candidate for candidate in (Path.cwd(), *Path.cwd().parents)
                if (candidate / "stat_assistant").is_dir()), None)
if PROJECT is None:
    raise RuntimeError("Start Jupyter from within the project repository.")
sys.path.insert(0, str(PROJECT))
from stat_assistant.models import create_agents
from stat_assistant.workflow import build_graph
from stat_assistant.runtime import new_run, ask_followup, resume_answers, collect_answers
from stat_assistant.settings import DATA_DIR, OUTPUT_DIR
from stat_assistant.nodes import AnalysisState
import stat_assistant.workflow as graph_module

agent_a, agent_b, configuration = create_agents()
graph = build_graph(agent_a, agent_b, mode=configuration["mode"])
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
print(json.dumps(configuration, indent=2))
print("REAL LLM calls" if configuration["mode"] == "real" else "MOCK stand-ins; no LLM calls")
print("All statistical calculations use Python/SciPy.")
''')
md('''
## State, routers and graph construction
The source below is imported from the package used by these examples. `errors`, `trace`
and `model_calls` use append reducers and a request number. Other fields store the plan,
data version, diagnostics, protected numerical results, draft, review and session memory.
Every node has an explicit role; every conditional edge has a labelled path map.
''')
code('''
for obj in (AnalysisState, graph_module.entry_route, graph_module.plan_route,
            graph_module.diagnostic_route, graph_module.correction_route,
            graph_module.review_route, graph_module.followup_route, build_graph):
    print(inspect.getsource(obj))
''')
md('''
## Diagram rendered from the compiled graph
The `graph` object below is also used by every example. Rendering uses LangGraph's
`draw_mermaid_png()` and the Mermaid rendering service; this cell needs internet access.
''')
code('''
png_bytes = graph.get_graph().draw_mermaid_png()
artifact_dir = PROJECT / "artifacts"
artifact_dir.mkdir(parents=True, exist_ok=True)
(artifact_dir / "graph.png").write_bytes(png_bytes)
(artifact_dir / "graph.mmd").write_text(graph.get_graph().draw_mermaid(), encoding="utf-8")
display(Image(png_bytes))
''')
md('''
### What each node represents
| Step | Node | Actor and concrete output |
|---|---|---|
| Step 1 | `plan_analysis` | Model A maps the question and user-supplied variable meanings to one of four methods, roles, estimand, H0 and H1. The program checks roles and scope. |
| Step 2 | `prepare_data_summary` | Python reads the raw CSV, preserves missing entries and labels, and produces the shared descriptive summary. |
| Step 3 | `llm_diagnostics` | Model A reviews the summary, variable meanings, study design and goal alignment, with evidence for each concern. |
| Step 4 | `stat_diagnostics` | Python independently checks missing/nonfinite values, stated ranges and labels, duplicate IDs, sample size, degenerate variables, boxplot flags and method-specific conditions. |
| Step 5 | `merge_diagnostics` | Fixed rules combine both branches and select proceed, clarification or stop; Model A explains that decision and phrases questions. |
| Step 6 | `request_clarification` | LangGraph `interrupt()` pauses and presents each flagged record and allowed actions to the user. |
| Step 7 | `apply_corrections` | Python validates explicit answers and reasons, writes a new data version and logs changes/exclusions. The original CSV stays unchanged. |
| Step 8 | `run_statistical_test` | Python/SciPy computes the planned test, estimate, p-value and interval where implemented. |
| Step 9 | `build_stats_block` | Python formats protected numeric fields, H0/H1, decision at alpha and required limitations. |
| Step 10 | `draft_report` | Model A receives the plan and evidence and writes an interpretation using numeric placeholders. |
| Step 11 | `check_report` | Python checks placeholders, mandatory fields, literal numbers, common label/value swaps, declared direction, decision and required limitation IDs. |
| Step 12 | `review_report` | Different Model B independently checks the rendered draft against the original statistical/design evidence. Critical issues fail review. |
| Step 13 | `revise_report` | Model A receives B's specific critical comments and program-check failures and makes at most one revision. |
| Step 14 | `deliver_report` | Python presents a report only after both the program check and B's review pass. |
| Step 15 | `issue_notice` | Python explains why no validated inferential report was delivered. |
| Step 16 | `save_session` | The graph saves the latest successful analysis for follow-ups in this thread. Memory is in-process, not a persistent production database. |
| Step 17 | `handle_followup` | Model A classifies a follow-up; the program verifies reuse conditions and routes it. |

### What the edges and conditions mean
LangGraph merges routes that have the same source and destination in its rendering. Such
an edge may show only `error`; the full path maps above and conditions below also include
unsupported requests, user stops and exhausted revisions that share that destination.

- **START** routes `new_analysis` to planning and `followup` to follow-up handling.
- Planning routes `ready` to summary, `revise_plan_once` back to itself, or `stop`/`error` to the issue notice. One plan revision is allowed.
- Summary fans out to **LLM diagnostics and Python diagnostics concurrently**. A join edge waits for **both** before merging; neither branch reads the other's draft findings.
- Merge routes `proceed` to the statistical test, `needs_clarification` to the interrupt, or `stop`/`error` to the issue notice. A failed assumption never starts an unlimited method search.
- Clarification proceeds to applying answers. Valid answers route `recheck_data` back to summary; user stop or errors go to the issue notice. At most two answered diagnostic rounds are allowed. Invalid input is re-asked and never applied.
- Test → protected statistics → draft → program check → Model B review passes the outputs along in order.
- Review routes `review_passed` to delivery, `revise_once` to revision → program check → review, or `fail_after_revision`/`error` to the issue notice.
- Follow-up routes `new_confidence_level` to recomputation, `re_explain` to a new draft, `new_question` to fresh planning and diagnostics, or `stop`/`error` to the issue notice. A changed dataset or study-design description triggers fresh checks.
- Delivery and issue notice both go to save-session → END. A per-request model-call cap and guarded exceptions prevent uncontrolled retries; interruption is deliberately re-raised so LangGraph can pause.

### Actual handoffs and prompting
**A → B** occurs when `draft_report` passes Model A's draft through `check_report` to
`review_report`. B sees the rendered draft **and independent original evidence**, including
statistics, design and correction history. **B → A** occurs on `revise_once`: B's critical
sentences and proposed fixes become inputs to `revise_report`.
These are two different models, configured separately. Python tools and the human-input step
are not extra LLM agents.

Model A uses schema-constrained structured output; planning uses one-shot prompting
with a concrete example. Diagnosis and review use explicit evidence and a
rubric; revision is a bounded reflection step. The system does not require or expose hidden
chain-of-thought. Python tools execute the structured plan rather than arbitrary generated code.
Two models reduce one source of correlated error but do not guarantee a correct interpretation.
''')
code('''
TUTORING_DESIGN = {
    "id_column": "student_id", "randomized": False,
    "assignment": "Tutoring was voluntary and not randomized.",
    "independence": "Independent observations stated by the user; one record per independently sampled student.",
    "variables": {
        "tutoring": {"type": "categorical", "levels": ["yes", "no"], "meaning": "Attended tutoring"},
        "score": {"type": "numeric", "range": [0, 100], "meaning": "Exam score in points"},
    },
    "typical_outcome": "score",
}
STUDENT_DESIGN = {**TUTORING_DESIGN, "variables": {
    **TUTORING_DESIGN["variables"],
    "study_hours": {"type": "numeric", "range": [0, 24], "meaning": "Weekly study hours"},
    "passed": {"type": "categorical", "levels": ["yes", "no"], "meaning": "Passed the exam"},
}}
case_outputs = {}

def show_case(name, state):
    paused = bool(state.get("__interrupt__"))
    status = "paused_for_user" if paused else state.get("final_status")
    print(f"{name}: {status}; request {state['request_number']}; report revisions {state.get('revision_count', 0)}")
    current_trace = [t for t in state.get("trace", []) if t["request_number"] == state["request_number"]]
    print("Nodes:", " -> ".join(t["node"] for t in current_trace))
    if state.get("analysis_plan"):
        display(Markdown("**Analysis plan**"))
        print(json.dumps(state["analysis_plan"], indent=2, ensure_ascii=False))
    if paused:
        print(json.dumps(state["__interrupt__"][0].value, indent=2, ensure_ascii=False))
    else:
        display(Markdown(state.get("final_report", "No report.")))
    record = {"status": status, "request_number": state["request_number"],
              "method": state.get("analysis_plan", {}).get("method"),
              "revisions": state.get("revision_count", 0),
              "program_check": state.get("program_check"), "review": state.get("review_verdict"),
              "result": state.get("stat_result"), "final_report": state.get("final_report"),
              "trace": current_trace, "model_calls": [c for c in state.get("model_calls", []) if c["request_number"] == state["request_number"]],
              "errors": [e for e in state.get("errors", []) if e["request_number"] == state["request_number"]]}
    case_outputs[name] = record
    return state
''')
md('''
## Example 1 — compare two means
**Input:** “Compare the mean exam score for tutoring yes versus no.” One categorical
two-group variable and a numeric outcome imply a difference of means; two numeric variables
and a linear-association question would instead call for Pearson correlation.
The estimand is mean score in `yes` minus mean score in `no`; H0: difference = zero;
H1: difference is nonzero. Welch does not require equal variances. Shapiro-Wilk and
boxplot summaries describe risks; they do not select another estimand or prove validity.
''')
code('''
welch = show_case("welch", new_run(graph, DATA_DIR / "tutoring_scores_clean_synthetic.csv",
    "Compare the mean exam score for tutoring yes versus no.", TUTORING_DESIGN, thread_id="demo-welch"))
''')
md('''
## Examples 2–4 — the other three supported methods
The new 120-student file was generated with one fixed seed, with no significance-based
selection. Pearson describes linear association; chi-square compares categorical variables;
simple OLS estimates the score change associated with one additional study hour.
Chi-square uses **no Yates correction**, matching the teammate's SciPy implementation.
No interval for Cramer's V is implemented. Sparse expected counts stop the analysis.
''')
for name, question in [
    ('pearson', 'What is the Pearson correlation between study hours and score?'),
    ('chi_square', 'Is tutoring associated with whether a student passed? Use tutoring and passed.'),
    ('regression', 'Regress score on study hours: how much does score change per additional study hour?')]:
    code(f'''{name} = show_case("{name}", new_run(graph, DATA_DIR / "students_synthetic.csv",
        {question!r}, STUDENT_DESIGN, thread_id="demo-{name}"))''')
md('''
## Follow-ups — what is reused and what is recomputed
On the successful Welch thread, changing to a **99% confidence interval** reuses the verified
file, variable mapping, design and diagnostics, but reruns the statistical tool and both report
checks. Alpha remains 0.05; a 99% CI and that decision threshold answer different conventions.
A re-explanation reuses the numerical result and generates/reviews fresh prose.
A new question gets a new plan and data checks. Filtering “only last year's data” is currently
unsupported: supply a new CSV; the assistant must not pretend it filtered the original data.
''')
code('''
ci99 = show_case("ci99", ask_followup(graph, "demo-welch", "Report a 99% confidence interval for the same mean difference."))
explanation = show_case("re_explain", ask_followup(graph, "demo-welch", "Explain whether we can say tutoring caused higher scores."))
''')
md('''
## Messy data — pause for real user decisions
The uploaded file contains missing scores, an out-of-range score, an unexpected group label
and unusual values. The exact findings are computed, not hard-coded. The workflow presents
feedback before any inferential test. The human can correct a value with a source, explicitly
exclude a record with a reason, verify a merely unusual value, or stop. A missing or invalid
value cannot be made valid by clicking “verify”.

**This headless example stops at the interrupt. No user answers are invented.** For a live
Jupyter demonstration, set `INTERACTIVE = True` and enter actual answers. Scripted answers
exist only in automated tests and are identified as test input. After answers, both diagnostic
branches run again; repeated unresolved problems stop after the configured limit.
''')
code('''
messy = show_case("messy", new_run(graph, DATA_DIR / "tutoring_scores_messy_synthetic.csv",
    "Compare the mean score for tutoring yes versus no.", TUTORING_DESIGN, thread_id="demo-messy"))
INTERACTIVE = False
if INTERACTIVE:
    while messy.get("__interrupt__"):
        answers = collect_answers(messy["__interrupt__"][0].value["requests"])
        if answers is None:
            break
        messy = show_case("messy_after_answers", resume_answers(graph, "demo-messy", answers))
''')
md('''
## Controlled faults — TEST INPUT, not naturally occurring model mistakes
These test hooks deliberately append a causal assertion, replace the p-value placeholder
with an incorrect literal, or raise a model-call error. They demonstrate revision/stop routes.
The first two are rechecked after at most one revision; acceptance is not forced. A model
failure ends with an issue notice. In mock mode the agents are rule-based stand-ins.
''')
for name, fault in [('causal_fault', {'kind':'causal_claim'}), ('numeric_fault', {'kind':'wrong_number'}),
                    ('model_failure', {'kind':'model_failure','node':'plan_analysis'})]:
    code(f'''{name} = show_case("{name}", new_run(graph, DATA_DIR / "tutoring_scores_clean_synthetic.csv",
        "Compare the mean score for tutoring yes versus no.", TUTORING_DESIGN,
        thread_id="demo-{name}", test_fault={fault!r}))''')
md('''
## Evidence and evaluation boundary
The final cell writes the actual mode, per-case statuses, model call records, checks and results.
`pytest` separately covers numerical agreement with SciPy and workflow edge cases, including
borderline/degenerate data, sparse tables, error routing, limits and memory reuse.
Those tests are **not** a human evaluation of LLM accuracy. A future blinded rubric evaluation
should score interpretation fidelity, uncertainty, causality, missingness and inappropriate
method switching on predefined clean, ambiguous and failing cases. Human raters judge the
whole system's outputs; they are not training Model A or Model B unless a separate fine-tuning
study is explicitly undertaken. Cloud-provider calls have not been validated by this notebook.
''')
code('''
from datetime import datetime, timezone
verification = {"executed_at": datetime.now(timezone.utc).isoformat(), "configuration": configuration,
                "cases": case_outputs}
evidence_path = OUTPUT_DIR / f"v2_notebook_{configuration['mode']}_evidence.json"
evidence_path.write_text(json.dumps(verification, indent=2, ensure_ascii=False, allow_nan=False), encoding="utf-8")
print("Saved:", evidence_path)
for name, item in case_outputs.items():
    print(f"{name:18} {item['status']:18} revisions={item['revisions']} errors={len(item['errors'])}")
''')
nb.cells = cells
write_notebooks(ROOT, nb)
print('Created demo.ipynb and assignments/2026-10-12/langgraph/LangGraph_Submission.ipynb')
