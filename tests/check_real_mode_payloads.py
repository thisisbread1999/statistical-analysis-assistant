"""
Offline check of the REAL-mode code path for the CLOUD models (no network, no API call, no real key needed).

Run from the project folder:   python tests/check_real_mode_payloads.py

It loads the notebook's "graph-definition" cells with LLM_MODE=real and placeholder key strings,
then, for Model A and Model B and for every structured-output schema, BUILDS the request payload
that LangChain would send to the provider and prints a summary. Nothing is sent.
This confirms the configuration and schemas are accepted by langchain-openai / langchain-anthropic;
it does NOT show that the real models answer correctly. That needs a run with real keys.
"""
import os
import sys
from pathlib import Path

import nbformat

PROJECT_DIR = Path(__file__).resolve().parents[1]
os.chdir(PROJECT_DIR)
os.environ.update({"LLM_MODE": "real",
                   "MODEL_A": "openai:gpt-4.1-mini", "MODEL_B": "anthropic:claude-sonnet-5-5",
                   "OPENAI_API_KEY": os.getenv("OPENAI_API_KEY") or "placeholder-not-a-real-key",
                   "ANTHROPIC_API_KEY": os.getenv("ANTHROPIC_API_KEY") or "placeholder-not-a-real-key"})

nb = nbformat.read(PROJECT_DIR / "stats_assistant_graph.ipynb", as_version=4)
ns: dict = {}
for cell in nb.cells:
    if cell.cell_type == "code" and "graph-definition" in cell.metadata.get("tags", []):
        exec(compile(cell.source, "<notebook cell>", "exec"), ns)

from langchain_core.messages import HumanMessage, SystemMessage

messages = [SystemMessage("system"), HumanMessage("input")]
ok = True
for label, llm in [("Model A", ns["llm_model_a"]), ("Model B", ns["llm_model_b"])]:
    for schema in ["AnalysisPlan", "LLMDiagnosticReport", "MergeAssessment", "ReportDraft", "ReviewVerdict"]:
        chain = llm.with_structured_output(ns[schema], method="json_schema")
        binding = chain.first                         # the chat model bound with the output format
        payload = binding.bound._get_request_payload(messages, **binding.kwargs)
        has_format = bool(payload.get("response_format") or payload.get("output_config"))
        ok &= has_format and "temperature" not in payload
        print(f"{label} {type(llm).__name__:13s} {payload.get('model'):22s} {schema:20s} "
              f"structured-output format: {'yes' if has_format else 'MISSING'}; temperature sent: {'temperature' in payload}")
print("\nAll payloads built (nothing was sent)." if ok else "\nPROBLEM: see lines above.")
sys.exit(0 if ok else 1)
