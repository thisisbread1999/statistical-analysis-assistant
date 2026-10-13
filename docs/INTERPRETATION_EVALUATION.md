# Interpretation challenge evaluation

`interpretation_benchmark.py` evaluates sixteen controlled drafts: four valid templates and twelve authored mutations. It measures coverage of the existing program checker and independent reviewer on known planted errors. The labels are authored fixture expectations, not human ratings, and the drafts are not real Model A outputs. Counts must not be presented as semantic accuracy or a real model error rate.

Challenge categories and mutations are adapted from the teammate's `interpretation_benchmark.py` at commit `b7eff1c`. This port uses this project's `ReportDraft`, protected placeholders, structured direction and decision claims, and limitation ids. It imports no teammate code, computed results or detector scores. The shared source CSV files and case metadata are loaded through the local `benchmark_suite.py` adapter.

The valid templates cover Welch's independent-samples t-test, Pearson correlation, chi-square independence and simple linear regression. Each receives an unsupported p-value literal mutation and an unqualified causal-claim mutation. Four additional challenges plant a wrong method name for Welch, a correlation interpreted as an eighty-percent increase, a frequentist confidence interval interpreted as probability for a fixed parameter, and a claim of no relationship for U-shaped data with near-zero Pearson correlation.

The runner calls the actual Python statistical tool for diagnostics and inference, builds the current protected report context, and calls `MockAnalysisAgentA.draft` to produce the original controlled template. It retains the original results and protected values, then mutates only the authored draft. It does not invoke real Model A. The protected context uses the current production limitation rules, including any regression diagnostic warnings.

These are isolated interpretation tests, not full workflow routing tests. They call `execute('run_test', request)` directly; the tool enforces blocking record and method requirements. Non-blocking verification flags are retained in each case. The runner does not fabricate a human verification, exclusion or correction, and `correction_log` stays empty for these source cases. An end-to-end workflow may pause for clarification on the same synthetic records; this evaluation makes no claim about that route.

Run from the project directory:

```powershell
python interpretation_benchmark.py --mode offline
python interpretation_benchmark.py --mode live
python interpretation_benchmark.py --mode live --case welch_clean_valid --case welch_wrong_method
```

`offline` uses `MockReviewAgentB`, the existing rule-based stand-in. Its results establish deterministic detector behavior; they are not evidence of LLM review performance. `live` uses `models.create_agents` with explicit real mode and the project's current `MODEL_A`/`MODEL_B` configuration or existing Ollama defaults. The returned real Model A is never invoked. Only real Model B reviews each rendered challenge. Model setup still uses the production readiness and distinct-model checks. No cloud provider is selected or configured by this runner.

For each draft the existing `report.check_report` runs against the original protected block. The renderer fills placeholders from that block. Reviewer B receives the production evidence fields: rendered `report_draft`, original statistics in `stat_result`, original `protected_statistics`, `analysis_plan`, `design_info`, `correction_log` and `required_limitations`. The report version is the neutral `v1` for every challenge. The fixture name, authored label and mutation code remain in the enclosing evaluator artifact; B receives none of them or the program check result. The source filesystem path is omitted from B's `stat_result` projection because its filename identifies the fixture; the complete original tool result including that path stays in the artifact. All numerical fields and protected evidence remain unchanged. B is called even when the program rejects a numerical literal or another check fails. No automatic revision removes the planted mutation before either detector is measured.

The report counts program acceptance, reviewer acceptance and combined acceptance separately. Combined acceptance requires both detectors to accept the draft. Each detector reports valid-template acceptance and false alarms, planted-error catches and misses, and unassessed cases. An exception, malformed output, preparation failure or inconsistent failed verdict with no issues is unassessed and earns no detection credit. Critical reviewer issues determine acceptance as in production; minor suggestions do not reject a draft.

Every run creates a unique directory under `artifacts/interpretation_checks/`. `--name NAME` supplies a specific new directory name; an existing directory is never overwritten. Each case JSON retains the descriptor, original draft, mutation, actual statistical request/results/diagnostics, protected values, exact reviewer evidence, program check and raw/normalized reviewer verdict. `results.json` and `REPORT.md` are updated after every case so later failures preserve completed evidence. Preparation and reviewer failures are saved per case as unassessed results. `--case` may be repeated to select challenges.

The sixteen inputs in `examples/interpretation_checks/` contain descriptor labels and mutation names, without imported scores. Inspect the saved report and evidence to distinguish a detector blind spot from a valid-template false alarm or a failed reviewer call. A separate human review of actual model outputs is needed for semantic quality claims; this runner creates no human labels.
