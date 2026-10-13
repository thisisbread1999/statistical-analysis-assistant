"""Keep the full project demo and generate a focused, self-contained assignment."""
import base64
import copy
import json
import textwrap
import zlib
from pathlib import Path

import nbformat

ASSIGNMENT_DIRECTORY = Path("assignments/2026-10-12/langgraph")
EXAMPLE_FILES = ("tutoring_scores_clean_synthetic.csv",)


def standalone_notebook(project, notebook):
    """Embed the real package, actual graph and one optional synthetic smoke example."""
    project = Path(project)
    payload = {
        path.relative_to(project).as_posix(): path.read_text(encoding="utf-8")
        for path in sorted((project / "stat_assistant").glob("*.py"))
    }
    payload.update({f"examples/{name}": (project / "examples" / name).read_text(encoding="utf-8")
                    for name in EXAMPLE_FILES})
    encoded = base64.b64encode(zlib.compress(json.dumps(payload).encode("utf-8"), 9)).decode("ascii")
    wrapped = "\n".join(textwrap.wrap(encoded, width=100))
    bootstrap = '''# Collapsed bundle: the real Python package and one synthetic CSV; no credentials.
import base64, json, os, sys, tempfile, zlib
from pathlib import Path

for _name in tuple(sys.modules):
    if _name == "stat_assistant" or _name.startswith("stat_assistant."):
        del sys.modules[_name]
_submission_workspace = tempfile.TemporaryDirectory(prefix="sa_")
PROJECT = Path(_submission_workspace.name)
_encoded_files = """ENCODED_PAYLOAD"""
_files = json.loads(zlib.decompress(base64.b64decode(_encoded_files)))
for _relative_path, _content in _files.items():
    _target = PROJECT / _relative_path
    _target.parent.mkdir(parents=True, exist_ok=True)
    _target.write_text(_content, encoding="utf-8")
sys.path.insert(0, str(PROJECT))
os.environ.setdefault("LLM_MODE", "mock")
print("Embedded project source ready; no external project files required.")
'''.replace("ENCODED_PAYLOAD", wrapped)
    intro = '''# Agentic Statistical Analysis Assistant — LangGraph Visualization
**Jingcheng Zhou and Junliang Lyu · Module 6**

This notebook compiles and visualizes our actual **17-node StateGraph**, then explains
its nodes and conditional handoffs. Model A plans and drafts; different Model B reviews.
Python tools calculate statistics. The final synthetic example is optional.

**Setup:** use a Python 3.13 notebook kernel. If needed, install the following packages
in the kernel before running the cells (this command is not run automatically):

```python
%pip install langgraph==1.2.14 langgraph-checkpoint==4.2.0 langchain-core==1.6.9 pydantic==2.14.0 pandas==3.0.6 scipy==1.18.1 numpy==2.5.3 requests==2.34.2 ipython==9.17.1
```

Run in order. This focused submission uses **explicit mock agents**, the real graph and
real Python/SciPy statistics. No LLM service or API key is required. Leave `LLM_MODE`
unset or set it to `mock`; other modes are rejected to prevent accidental provider calls.
The PNG-rendering cell uses Mermaid's rendering service and needs internet access.
The collapsed next cell bundles our actual runtime source so this notebook works without
the repository. It contains no credentials, user uploads or benchmark scores. The graph
builder itself is displayed separately below. Mock execution checks control flow, not
the accuracy of a real LLM.
'''
    source_intro = '''## Actual graph implementation
The output below is the embedded package's actual `build_graph` source. It shows the
node callbacks, parallel join, labelled conditional edges and `compile()`.
The same compiled graph is used for the image and optional execution.
'''
    source_cell = '''import inspect
from IPython.display import Image, display
from stat_assistant.models import create_agents
from stat_assistant.workflow import build_graph

print(inspect.getsource(build_graph))
'''
    compile_cell = '''# Explicit offline mode: two role-specific stand-ins; no LLM calls.
if os.environ["LLM_MODE"] != "mock":
    raise ValueError("This submission uses LLM_MODE=mock. Use demo.ipynb for real-model runs.")
agent_a, agent_b, configuration = create_agents({"mode": "mock"})
graph = build_graph(agent_a, agent_b, mode="mock")
print("Compiled 17 workflow nodes. Mode:", configuration["mode"])
'''
    image_intro = '''## Built-in visualization
This image comes directly from the compiled graph. The cell also saves that same image
as `graph.png` in the notebook's working directory for submission.
'''
    image_cell = '''display(Image(png_bytes := graph.get_graph().draw_mermaid_png()))
graph_path = Path.cwd() / "graph.png"
graph_path.write_bytes(png_bytes)
print("Saved:", graph_path.name)
'''
    explanation = '''## Nodes and handoffs
| Node | Actor and output |
|---|---|
| `plan_analysis` | A proposes method, variables, estimand, H0/H1; code validates scope. |
| `prepare_data_summary` | Python reads the CSV and produces a shared summary. |
| `llm_diagnostics` | A checks variable meanings, design and goal alignment. |
| `stat_diagnostics` | Python checks data and method conditions; OLS includes influence, leverage and variance diagnostics. |
| `merge_diagnostics` | Code chooses proceed, clarification or stop; A explains feedback. |
| `request_clarification` | `interrupt()` pauses for the user's data decisions. |
| `apply_corrections` | Code validates answers, logs changes and creates a data version. |
| `run_statistical_test` | Python/SciPy computes the planned analysis. |
| `build_stats_block` | Code protects numeric results, hypothesis decisions and limitations. |
| `draft_report` | A drafts an interpretation using numeric placeholders. |
| `check_report` | Code checks placeholders, numbers, claims and limitation fields. |
| `review_report` | B checks the rendered draft against original evidence. |
| `revise_report` | A revises once using code failures and B's comments. |
| `deliver_report` | Code delivers only after both checks pass. |
| `issue_notice` | Code explains why no validated analysis was delivered. |
| `save_session` | Code stores the latest successful analysis in thread memory. |
| `handle_followup` | A classifies a follow-up; code verifies reuse conditions. |

**Edges and conditions:**

- `START` routes a new analysis to planning or a follow-up to `handle_followup`.
- Planning goes to summary when ready, retries itself once for an invalid plan, or stops on an unsupported request/error.
- Summary sends inputs to A's diagnostics and Python diagnostics **in parallel**. Their join waits for both before merging.
- Merge proceeds to the test when checks permit, pauses for clarification when user decisions are needed, or stops. Valid corrections return to summary for rechecking; user stop/errors lead to `issue_notice`. At most two answered clarification rounds are allowed.
- The normal chain is test → protected statistics → draft → program check → B review. Review passes to delivery, sends one failed draft to revision → program check → B review, or stops after that revision/error.
- Follow-ups send a changed confidence level to recomputation, re-explanation to drafting, or a new question to fresh planning. Unsupported requests/errors stop.
- Delivery and issue notices both lead to session memory → `END`.

**A → B:** `draft_report` → `check_report` → `review_report`. B receives A's rendered
draft plus original statistical results, study design and correction history.
**B → A:** failed review → `revise_report`; B's specific comments are A's revision input.
These are separately configured models in real mode, and separately implemented stand-ins
in this saved mock run. Python tools and the human-input node are not extra LLM agents.

The shared state passes the question, plan, data version, findings, results, draft and
review between nodes. The graph demonstrates routing, tool use, parallelization, bounded
reflection and memory. Routes sharing a destination may be merged in the diagram;
their full conditions remain explicit in the builder and explanation above.
'''
    example_intro = '''## Optional short execution check
**Synthetic input:** “Compare the mean exam score for tutoring yes versus no.” The user
states independent observations and voluntary, non-random participation. The graph runs
a two-sided Welch test with real Python/SciPy calculations and explicit mock responses.
This illustrates execution and is not a model evaluation.
'''
    example_cell = '''from stat_assistant.runtime import new_run

design = {
    "id_column": "student_id", "randomized": False,
    "assignment": "Tutoring was voluntary and not randomized.",
    "independence": "Independent observations stated by the user; one record per independently sampled student.",
    "variables": {
        "tutoring": {"type": "categorical", "levels": ["yes", "no"], "meaning": "Attended tutoring"},
        "score": {"type": "numeric", "range": [0, 100], "meaning": "Exam score in points"},
    },
    "typical_outcome": "score",
}
example = new_run(graph, PROJECT / "examples/tutoring_scores_clean_synthetic.csv",
    "Compare the mean exam score for tutoring yes versus no.", design, thread_id="hw6")
print("Status:", example["final_status"])
print("Method:", example["analysis_plan"]["method"])
print("Checks:", example["program_check"]["passed"], example["review_verdict"]["passed"])
print("Executed nodes:", " → ".join(item["node"] for item in example["trace"]))
'''
    result = nbformat.v4.new_notebook()
    result.metadata = copy.deepcopy(notebook.metadata)
    result.cells = [
        nbformat.v4.new_markdown_cell(intro),
        nbformat.v4.new_code_cell(bootstrap, metadata={"jupyter": {"source_hidden": True}, "collapsed": True}),
        nbformat.v4.new_markdown_cell(source_intro),
        nbformat.v4.new_code_cell(source_cell),
        nbformat.v4.new_code_cell(compile_cell),
        nbformat.v4.new_markdown_cell(image_intro),
        nbformat.v4.new_code_cell(image_cell),
        nbformat.v4.new_markdown_cell(explanation),
        nbformat.v4.new_markdown_cell(example_intro),
        nbformat.v4.new_code_cell(example_cell),
    ]
    result.metadata["stat_assistant"] = {"layout": "standalone", "source": "demo.ipynb", "purpose": "langgraph_visualization"}
    return result


def write_notebooks(project, notebook):
    project = Path(project)
    nbformat.write(notebook, project / "demo.ipynb")
    directory = project / ASSIGNMENT_DIRECTORY
    directory.mkdir(parents=True, exist_ok=True)
    nbformat.write(standalone_notebook(project, notebook), directory / "LangGraph_Submission.ipynb")
    graph_path = project / "artifacts" / "graph.png"
    if graph_path.exists():
        (directory / "graph.png").write_bytes(graph_path.read_bytes())
