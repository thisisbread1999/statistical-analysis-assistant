"""Generate project-linked and standalone notebooks from one current implementation."""
import copy
from pathlib import Path

import nbformat

ASSIGNMENT_DIRECTORY = Path("assignments/2026-10-12/langgraph")
EXAMPLE_FILES = (
    "students_synthetic.csv",
    "tutoring_scores_clean_synthetic.csv",
    "tutoring_scores_messy_synthetic.csv",
    "tutoring_scores_no_difference_synthetic.csv",
    "tutoring_scores_unequal_variance_synthetic.csv",
)


def standalone_notebook(project, notebook):
    """Embed source and synthetic examples only; never embed .env or runtime records."""
    payload = {
        str(path.relative_to(project)).replace("\\", "/"): path.read_text(encoding="utf-8")
        for path in sorted((project / "stat_assistant").glob("*.py"))
    }
    payload.update({f"examples/{name}": (project / "examples" / name).read_text(encoding="utf-8")
                    for name in EXAMPLE_FILES})
    result = copy.deepcopy(notebook)
    bootstrap = '''# Standalone workspace: own Python source and synthetic data, no credentials.
import os, sys, tempfile
from pathlib import Path

# A second Run All must import the new embedded workspace, including new path settings.
for _module_name in tuple(sys.modules):
    if _module_name == "stat_assistant" or _module_name.startswith("stat_assistant."):
        del sys.modules[_module_name]
_submission_workspace = tempfile.TemporaryDirectory(prefix="stat_assistant_submission_")
PROJECT = Path(_submission_workspace.name)
EMBEDDED_FILES = PAYLOAD
for _relative_path, _content in EMBEDDED_FILES.items():
    _target = PROJECT / _relative_path
    _target.parent.mkdir(parents=True, exist_ok=True)
    _target.write_text(_content, encoding="utf-8")
os.environ.setdefault("LLM_MODE", "mock")
print("Standalone Python workspace initialized; source and data are embedded.")
'''.replace("PAYLOAD", repr(payload))
    result.cells.insert(1, nbformat.v4.new_code_cell(bootstrap))
    setup = next(cell for cell in result.cells if cell.cell_type == "code"
                 and "from stat_assistant.models import create_agents" in cell.source)
    original = '''PROJECT = next((candidate for candidate in (Path.cwd(), *Path.cwd().parents)
                if (candidate / "stat_assistant").is_dir()), None)
if PROJECT is None:
    raise RuntimeError("Start Jupyter from within the project repository.")'''
    if original not in setup.source:
        raise ValueError("Notebook setup no longer matches the standalone generator.")
    setup.source = setup.source.replace(original, "# PROJECT was initialized by the standalone bootstrap above.")
    result.cells[0].source = result.cells[0].source.replace(
        "Run from this project folder after `pip install -r requirements.txt`. Configure `.env`\n"
        "from `.env.example`:",
        "Install the packages from `requirements-lock.txt` in your notebook kernel. Configure the kernel environment:"
    )
    result.cells[0].source += (
        "\n\n**Standalone submission:** this file embeds our Python package and five synthetic CSVs. "
        "Install the packages from the repository's `requirements-lock.txt` in the notebook kernel first. "
        "It runs without other project files and defaults to explicitly labelled mock agents. "
        "Set `LLM_MODE=real` in the kernel environment to use two configured models. "
        "No API key or `.env` file is embedded. Outputs are written to the temporary workspace."
    )
    result.metadata["stat_assistant"] = {"layout": "standalone", "source": "demo.ipynb"}
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
