"""Run the two-model course workflow using the teammate's demo.py entry convention."""
import argparse
import json
from pathlib import Path

from stat_assistant.models import create_agents
from stat_assistant.runtime import collect_answers, new_run, resume_answers
from stat_assistant.settings import DATA_DIR
from stat_assistant.workflow import build_graph

SYNTHETIC_DESIGN = {
    "id_column": "student_id", "randomized": False,
    "assignment": "Synthetic teaching scenario: tutoring was voluntary and not randomized.",
    "independence": "Synthetic teaching design: one independent record per simulated student.",
    "variables": {
        "tutoring": {"type": "categorical", "levels": ["yes", "no"], "meaning": "Attended tutoring"},
        "score": {"type": "numeric", "range": [0, 100], "meaning": "Exam score in points"},
    },
    "typical_outcome": "score",
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--mode", choices=("mock", "real"), default=None)
    modes.add_argument("--live", action="store_true", help="Alias for --mode real.")
    parser.add_argument("--csv", type=Path, help="Optional input CSV; also supply --design-json.")
    parser.add_argument("--question", default="Compare the mean exam score for tutoring yes versus no.")
    parser.add_argument("--design-json", type=Path, help="JSON containing your confirmed design and variable meanings.")
    parser.add_argument("--interactive", action="store_true", help="Answer data clarification requests in the terminal.")
    args = parser.parse_args()
    if args.csv is not None and args.design_json is None:
        parser.error("An external CSV requires --design-json; independence and design cannot be inferred from its values.")
    design = json.loads(args.design_json.read_text(encoding="utf-8")) if args.design_json else SYNTHETIC_DESIGN
    mode = "real" if args.live else args.mode or "mock"
    import os
    os.environ["LLM_MODE"] = mode
    agent_a, agent_b, configuration = create_agents()
    print(json.dumps(configuration, indent=2))
    graph = build_graph(agent_a, agent_b, mode=mode)
    state = new_run(graph, args.csv or DATA_DIR / "tutoring_scores_clean_synthetic.csv", args.question, design)
    while state.get("__interrupt__"):
        prompt = state["__interrupt__"][0].value
        print(json.dumps(prompt, indent=2, ensure_ascii=False))
        if not args.interactive:
            print("Paused for user clarification. No answers were supplied automatically.")
            return
        answers = collect_answers(prompt["requests"])
        if answers is None:
            return
        state = resume_answers(graph, state["run_id"], answers)
    print(state.get("final_report", "No validated report was delivered."))
    print("Status:", state.get("final_status"))


if __name__ == "__main__":
    main()
