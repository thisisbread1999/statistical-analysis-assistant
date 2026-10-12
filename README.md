# Agentic Statistical Analysis Assistant: Multi-Agent LangGraph (Module 6)

This folder holds the deliverables for *Visualize Your Multi-Agent LangGraph*:

| File | What it is |
|---|---|
| `stats_assistant_graph.ipynb` | Main notebook: dependencies, State, nodes, routers, graph build + compile, diagram, explanation, examples |
| `stats_assistant_langgraph.png` | Diagram rendered by `graph.get_graph().draw_mermaid_png()` from the compiled graph object |
| `r/stats_tools.R` | R tool called through `Rscript` (tasks: `summary`, `diagnostics`, `welch_test`) |
| `r/make_synthetic_data.R` | Recreates the synthetic CSV files |
| `data/*.csv` | Four synthetic datasets: messy, clean, no difference, unequal variances (see `data/README.md`) |
| `tests/run_checks.py` | Automated control-flow checks of the notebook's graph (labelled test inputs, mock mode) |
| `tests/check_real_mode_payloads.py` | Offline check that the real-mode requests for both providers can be built (nothing is sent) |
| `requirements.txt`, `.env.example` | Python dependencies (exact versions used) and model/key settings |
| `outputs/` | Created at run time: R request/result JSON, new data versions, session records, Mermaid text |

## How Python and R work together

LangGraph runs in Python. A node that needs statistics writes a request JSON file and runs
`Rscript r/stats_tools.R <task> request.json result.json`; R computes the result and writes a result JSON file; Python reads it back into the graph state.
RStudio is used only to develop and test the R script. The workflow itself never calls RStudio.

## Setup on Windows (PowerShell)

Run these from this folder (`...\agentic ai\langgraph_visualization`).

1. **R** (4.x) with `jsonlite`. If `Rscript` is not on PATH, use its full path:
   ```powershell
   & "C:\Program Files\R\R-4.4.1\bin\Rscript.exe" -e "install.packages('jsonlite', repos='https://cloud.r-project.org')"
   ```
2. **Python environment.** Create it in a short path; long OneDrive paths can hit the Windows path-length limit during `pip install`:
   ```powershell
   py -m venv "$env:USERPROFILE\.venvs\langgraph-viz"
   & "$env:USERPROFILE\.venvs\langgraph-viz\Scripts\python.exe" -m pip install -r requirements.txt
   ```
3. **Models.** Copy `.env.example` to `.env`. Model A and Model B are configured separately (`MODEL_A`, `MODEL_B`). The notebook refuses to run if both settings resolve to the same provider and model. Choose one option:
   * **Local models via Ollama** (free, no key; the default in `.env.example`). Install Ollama, for example with `winget install Ollama.Ollama`, then download the two models (about 13.4 GB in total):
     ```powershell
     ollama pull qwen3:8b
     ollama pull gemma3:12b
     ```
     That gives `MODEL_A=ollama:qwen3:8b` (Alibaba Qwen) and `MODEL_B=ollama:gemma3:12b` (Google Gemma). The Ollama app must be running when you use the notebook. Their "thinking" mode is off by default for speed; set `OLLAMA_THINKING=on` in `.env` to enable it.
   * **Cloud APIs.** Set `MODEL_A=openai:gpt-4.1-mini` and `MODEL_B=anthropic:claude-sonnet-5-5`, and fill in `OPENAI_API_KEY` and `ANTHROPIC_API_KEY`.

   If no usable model is configured, `LLM_MODE=auto` falls back to **mock mode**: rule-based stand-ins that test the control flow only.
4. *(Optional)* Recreate the synthetic data:
   ```powershell
   & "C:\Program Files\R\R-4.4.1\bin\Rscript.exe" r/make_synthetic_data.R
   ```
5. *(Optional)* Run the automated checks (mock mode, about 2 minutes) and the offline real-mode payload check:
   ```powershell
   & "$env:USERPROFILE\.venvs\langgraph-viz\Scripts\python.exe" tests/run_checks.py
   & "$env:USERPROFILE\.venvs\langgraph-viz\Scripts\python.exe" tests/check_real_mode_payloads.py
   ```
6. **Open and run the notebook** in JupyterLab, then use *Run → Run All Cells*:
   ```powershell
   & "$env:USERPROFILE\.venvs\langgraph-viz\Scripts\python.exe" -m jupyter lab stats_assistant_graph.ipynb
   ```
   The diagram cell needs internet access, because `draw_mermaid_png()` uses the mermaid.ink service.
   Example 4 stops and asks you to type an answer, with a reason, for each flagged record. That is the human-in-the-loop step. Examples 1–3 are normal paths that end with a delivered report.

## What was verified, and what was not

* **Mock mode.** The graph compiles, and the PNG is drawn from the same compiled object that runs the examples. `tests/run_checks.py` (18 checks, all passing on 2026-10-09) shows that every control-flow path reaches its expected end:
  * the three normal paths: significant difference, non-significant difference, unequal group sizes and variances
  * pause → answers (scripted TEST INPUT) → new data version → re-diagnosis → delivery
  * user "stop"
  * rejected answers shown again, and the round limit
  * stop for a missing column
  * a whole group with mis-cased labels is asked about, not stopped
  * duplicate IDs
  * exclusion reasons in the limitations
  * review fail → one revision → pass
  * review fail → one revision → stop
  * the program check's field, sign, rounding, required-content, decision-wording and limitation checks
* **Real local models** (Ollama: `qwen3:8b` as Model A, `gemma3:12b` as Model B), in the saved notebook run of 2026-10-09:
  * Examples 1–3 were delivered on the first draft.
  * Example 4 went through clarification → new data version v2 → re-diagnosis → delivery.
  * Example 5: Model B flagged the injected causal sentence (TEST INPUT), and Model A removed it in its single revision, after which the report was delivered.
  * Example 6: the injected wrong number (TEST INPUT) was caught by Model B and by the program check, and the run stopped after one revision.
  * Example 7 stopped at the diagnostics.
* **Adjustments made after watching the local models**, each found in a real run:
  * α is a fixed project setting added by the program, because `qwen3:8b` kept writing α = 0.
  * Model A gets the list of supported methods, because without it `qwen3:8b` planned a normality-based switch to Mann-Whitney.
  * Model B's rubric defines causal claims, missing results and unsupported claims, because `gemma3:12b` flagged plain "association" wording as causal.
  * A report can fail review only through a critical issue.
  * The program checks that the interpretation states t, p, the estimate and its CI, and that the limitations are exactly the required ones, because a draft once omitted the results and added an unsupported "normality" limitation.
  * The revision prompt lists the exact sentences to fix, because Model A once kept the flagged sentence.
* These are single runs with small local models, not an evaluation of their accuracy.
* In Example 4 of the saved notebook, the answers the user confirmed (on 2026-10-09, in chat) were entered at the notebook's input prompts by the assistant on the user's behalf. Re-run it in Jupyter to type the answers yourself.
* The **cloud API** path (OpenAI / Anthropic) was only checked offline: `tests/check_real_mode_payloads.py` builds the requests for every structured-output schema without sending them. No cloud API call has been made yet.
