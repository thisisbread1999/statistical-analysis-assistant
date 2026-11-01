"""Generate the active project-linked demo only; never rewrite dated submissions."""
from pathlib import Path
from textwrap import dedent

import nbformat as nbf


ROOT = Path(__file__).resolve().parent


def build_notebook():
    cells = []

    def md(text):
        cells.append(nbf.v4.new_markdown_cell(dedent(text).strip()))

    def code(text):
        cells.append(nbf.v4.new_code_cell(dedent(text).strip()))

    md("""
    # Agentic Statistical Analysis Assistant: current project demo

    **Run provenance is printed below.** New builds clear previous outputs.
    This notebook imports the current 21-node graph and six supported statistical methods.
    Model A scopes, plans, and explains; a different Model B reviews. Python computes the
    numbers. The human selects one question and confirms the plan.

    **Project-linked, not standalone:** keep the full `stat_assistant/`,
    `examples/public_reproductions/`, and supporting assets. Start Jupyter inside this
    repository with its installed requirements. Dated submissions are not regenerated.

    Default **mock** mode uses rule-based agents, the real graph and Python tools, and no
    LLM calls. Running all cells with decision fields left as `None` pauses before
    inference. A pause is not a delivered or approved report.
    """)
    code("""
    import json
    import os
    import sys
    from pathlib import Path
    from IPython.display import Image, Markdown, display

    PROJECT = next((p for p in (Path.cwd(), *Path.cwd().parents)
                    if (p / "stat_assistant").is_dir()), None)
    if PROJECT is None:
        raise RuntimeError("Start Jupyter from inside the full project repository.")
    sys.path.insert(0, str(PROJECT))
    from stat_assistant.models import create_agents, load_env, DEFAULT_MODEL_A, DEFAULT_MODEL_B
    from stat_assistant.workflow import build_graph, ROLES
    from stat_assistant.methods import METHODS
    from stat_assistant.runtime import new_run, resume_plan, resume_answers

    MODE = os.getenv("STAT_ASSISTANT_DEMO_MODE", "mock")  # Default is offline; the runner sets this explicitly.
    if MODE not in ("mock", "real"):
        raise ValueError("Choose mock or real explicitly; this notebook does not use auto mode.")
    load_env()
    configuration = {"mode": MODE,
                     "model_a": os.getenv("MODEL_A", DEFAULT_MODEL_A),
                     "model_b": os.getenv("MODEL_B", DEFAULT_MODEL_B)}
    agent_a, agent_b, configuration = create_agents(configuration)
    graph = build_graph(agent_a, agent_b, mode=MODE)
    print("Mode:", MODE, "| actual nodes:", len(ROLES), "| supported methods:", len(METHODS))
    print("Rule-based agents; no LLM calls." if MODE == "mock" else "Real models; no mock fallback.")
    """)
    md("""
    ## One graph, grouped for teaching

    These groups account for the actual nodes imported from `workflow.py`; they are not
    21 separate agents. The data summary fans out to semantic and statistical checks,
    then joins both. Explicit data decisions loop through fresh checks. One report
    revision must pass the program check and independent model review again.
    """)
    code("""
    groups = {
        "Question, guidance, plan, approval": ["scope_request", "request_scope_confirmation",
            "retrieve_method_guidance", "plan_analysis", "approve_analysis_plan"],
        "Parallel checks and data decisions": ["prepare_data_summary", "llm_diagnostics",
            "stat_diagnostics", "merge_diagnostics", "request_clarification", "apply_corrections"],
        "Calculate and protect": ["run_statistical_test", "build_stats_block"],
        "Draft, check, review, revise, deliver": ["draft_report", "check_report", "review_report",
            "revise_report", "deliver_report"],
        "Stop and memory": ["issue_notice", "save_session"],
        "Followup routing": ["handle_followup"],
    }
    grouped_names = [name for names in groups.values() for name in names]
    if len(grouped_names) != len(ROLES) or set(grouped_names) != set(ROLES):
        raise RuntimeError("Update teaching groups to match the current graph.")
    rows = [f"| {group} ({len(names)}) | " + "; ".join(f"`{name}`" for name in names) + " |"
            for group, names in groups.items()]
    display(Markdown(f"**{len(ROLES)} executable nodes**\\n\\n| Group | Actual nodes |\\n|---|---|\\n" + "\\n".join(rows)))
    display(Markdown("**Methods:** " + "; ".join(spec.label for spec in METHODS.values())))
    """)
    md("""
    ## Diagram from this compiled graph

    Display a cached PNG only when its Mermaid source exactly matches the compiled
    graph. Otherwise show current Mermaid text. Optional rendering is off by default;
    the rendering service may need network access. This cell does not rewrite assets.
    """)
    code("""
    compiled_mermaid = graph.get_graph().draw_mermaid()
    cached_source = PROJECT / "artifacts" / "graph.mmd"
    cached_image = PROJECT / "artifacts" / "graph.png"
    RENDER_DIAGRAM = False
    cache_matches = (cached_source.is_file() and cached_image.is_file()
                     and cached_source.read_text(encoding="utf-8") == compiled_mermaid)
    if cache_matches:
        display(Image(filename=str(cached_image)))
    elif RENDER_DIAGRAM:
        display(Image(graph.get_graph().draw_mermaid_png()))
    else:
        print("Cached diagram is absent or mismatched; current Mermaid follows.")
        display(Markdown("```mermaid\\n" + compiled_mermaid + "\\n```"))
    """)
    md("""
    ## Choose one published example

    Set `CASE_ID` to `student_sleep`, `berkeley_admissions`, or `anscombe_quartet`.
    Read its manifest question and design before approving. This notebook runs one case.

    - **Sleep:** historical observations; preserve the same ten patients' paired
      measurements. A modern reanalysis is not current treatment advice.
    - **Berkeley:** historical aggregate counts for six departments, expanded for the
      tool. Generated row labels are not applicant IDs. Pooled association is not a
      department-adjusted causal analysis.
    - **Anscombe:** published constructed teaching data from 1973, not observed subjects.
      Four plots have nearly identical summaries; the workflow analyzes only `x1`, `y1`.

    A source-data plot is an illustration, not this notebook run's computed report.
    """)
    code("""
    CASE_ID = "student_sleep"
    CASE_DIR = PROJECT / "examples" / "public_reproductions"
    manifest = json.loads((CASE_DIR / "manifest.json").read_text(encoding="utf-8"))
    cases = {item["id"]: item for item in manifest["cases"]}
    if CASE_ID not in cases:
        raise ValueError(f"Choose an available CASE_ID: {', '.join(cases)}")
    case = cases[CASE_ID]
    design = json.loads((CASE_DIR / case["design_file"]).read_text(encoding="utf-8"))
    QUESTION = case["question"]
    print("Selected:", case["title"], "\\nQuestion:", QUESTION)
    print("Source:", case["source_name"], "|", case["documentation_url"])
    print("Citation:", case["citation"])
    print("Units:", case["unit"], "\\nTransformation:", case["derivation"])
    print("Claim boundary:", case["claim_not_supported"])
    print("Study metadata:", json.dumps(design, indent=2, ensure_ascii=False))
    source_plot = CASE_DIR / "classroom_plots" / f"{CASE_ID}.png"
    if source_plot.is_file():
        display(Image(filename=str(source_plot)))
    """)
    md("""
    ## Propose the plan, then pause

    Multi-target or ambiguous requests first trigger scope selection. Choose one target
    per run; edits are scoped again. Then approve its plan. There is no all-tests batch
    or automatic method fallback. The UI and CLI also require plan confirmation; the
    low-level `new_run` default remains `False`, so this notebook explicitly enables it.

    **Real mode:** Model A uses native `bind_tools` and returns an allowlisted name,
    arguments, and call ID. Checks and human approval precede execution. Drafting then
    receives the result in a `ToolMessage` paired with that ID. Mock planning is
    rule-based; it does not demonstrate native LLM tool calling.

    Retrieval searches six project-authored method cards with primary-source links,
    returning positive lexical matches only. It is neither a CSV summary nor textbook
    embedding/vector search. Program checks plus Model B review the explanation; one
    revision or a stop finalizes it. The RAG lesson's final node is `doc_finalizer`,
    not an added summarizer.
    """)
    code("""
    def show_state(current):
        pauses = current.get("__interrupt__", [])
        decision = pauses[0].value if pauses else {}
        print("Status:", "paused for user" if pauses else current.get("final_status"))
        print("Statistical result present:", bool(current.get("stat_result")))
        if decision.get("kind") == "scope_selection":
            print(decision["message"], json.dumps(decision["tasks"], indent=2))
        if current.get("analysis_plan"):
            print("Plan:", json.dumps(current["analysis_plan"], indent=2, ensure_ascii=False))
        for number, step in enumerate(decision.get("steps", []), 1):
            print(f"{number}. {step}")
        for reference in current.get("retrieved_references", []):
            print("Guidance:", reference["title"], "|", reference["text"], "|", reference["source"])
        if decision.get("plan_id"):
            print("Pending plan_id:", decision["plan_id"])
        if decision.get("requests"):
            print("Record decisions:", json.dumps(decision["requests"], indent=2, ensure_ascii=False))
        if current.get("selected_tool_call"):
            print("Native selection:", json.dumps(current["selected_tool_call"], indent=2))
        if not pauses:
            print(current.get("final_report", "No report was delivered."))
        return decision

    state = new_run(graph, CASE_DIR / case["data_file"], QUESTION, design,
                    require_plan_confirmation=True)
    pending = show_state(state)
    """)
    md("""
    ## Optional: supply one explicit scope or plan decision

    Leave `USER_DECISION = None` for a headless run. To continue, inspect the pause, edit
    the appropriate example below, and rerun this cell. After selecting a target or
    changing the question, inspect the new plan before approving it. The helper checks
    the kind of pending pause. No input prompt blocks notebook execution.
    """)
    code("""
    USER_DECISION = None
    # After reviewing a pending plan:
    # USER_DECISION = {"action": "approve", "plan_id": pending["plan_id"]}
    # At scope selection, choose a displayed id; optionally edit the question:
    # USER_DECISION = {"action": "select", "task_id": "task_1", "question": "Your one question"}
    # USER_DECISION = {"action": "change_question", "question": "Your revised question"}
    # USER_DECISION = {"action": "stop"}
    if USER_DECISION is not None:
        state = resume_plan(graph, state["run_id"], USER_DECISION)
        pending = show_state(state)
    else:
        print("No user decision supplied. The graph remains at its current pause.")
    """)
    md("""
    ## Optional: answer record questions manually

    Inspect each request's allowed actions and value. Supply your own correction,
    exclusion, verification, or stop; nothing is chosen automatically. Source/reason
    notes are optional. The original CSV is retained. A further pause needs a new decision.
    """)
    code("""
    USER_ANSWERS = None
    # Fill only at a record-clarification pause, with displayed request ids:
    # USER_ANSWERS = [{"request_id": "...", "action": "correct", "new_value": "...", "reason": ""}]
    if USER_ANSWERS is not None:
        state = resume_answers(graph, state["run_id"], USER_ANSWERS)
        pending = show_state(state)
    else:
        print("No record decisions supplied; no automatic data changes.")
    """)
    md("""
    ## Evidence and limits

    Dated saved mock runs under `examples/public_reproductions/evidence/` use rule-based
    agents and real Python tools. Live-model attempts are separate; a pause or stop is
    not delivery. This generated notebook claims no fresh test count or live-model
    success. Inspect actual outputs and mode after running.

    Paired t and explicitly planned two-sided Fisher exact extend the earlier four
    methods to six. Fisher requires a two-by-two table; no effect confidence interval
    is implemented. Filtering needs a new prepared CSV. A later request can re-explain
    validated evidence, recompute a supported confidence interval, or scope and approve
    a new question. Model review does not prove statistical validity.

    See [course alignment](docs/COURSE_ALIGNMENT_2026-11-01.md),
    [three-slide story](docs/THREE_SLIDE_STORY.md), and the
    [source manifest](examples/public_reproductions/manifest.json). This generator
    writes only the active `demo.ipynb`; it leaves dated assignments untouched.
    """)
    return nbf.v4.new_notebook(cells=cells, metadata={
        "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
        "language_info": {"name": "python", "version": "3.13"},
        "execution_status_at_generation": "not_executed_yet",
    })


def main():
    destination = ROOT / "demo.ipynb"
    nbf.write(build_notebook(), destination)
    print(f"Wrote active demo only: {destination}")


if __name__ == "__main__":
    main()
