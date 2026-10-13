# Frozen benchmark and evaluation adapter

The source catalog is the teammate repository snapshot `b7eff1c4a8035f196ac4bfc73ef3fe88956dadb5` (short name `b7eff1c`), copied into `examples/benchmark_v2/`. Its 31 CSV files, 31 JSON definitions, manifest, questions, source labels, notes, and source numeric references are preserved unchanged. The runner imports no teammate Python code and does not claim their existing scores as ours. All datasets are synthetic.

`benchmark_suite.py` loads the exported CSV/JSON objects and runs **our** `build_graph`, `new_run`, `resume_answers`, and `ask_followup` interfaces. Our method names and source data are adapted separately. `examples/benchmark_v2_adapted/` contains adapter declarations and source SHA-256 checksums after `--export-only`. Every actual run also writes `preregistered_cases.json` before creating live agents. That file fixes the selected cases, source hashes, metadata, expected primary behavior, and any synthetic continuation recipes before model results are known.

```
python benchmark_suite.py --export-only
python benchmark_suite.py --list
python benchmark_suite.py --mode offline --output offline_v2_first
python benchmark_suite.py --mode offline --resume-fixtures --output offline_v2_fixtures
python benchmark_suite.py --mode live --resume-fixtures --output live_v2_first
python benchmark_suite.py --mode live --case welch_clean --case regression_clean --output live_v2_selected
python benchmark_suite.py --mode offline --category stop --output offline_v2_stops
python benchmark_suite.py --mode offline --supplemental --resume-fixtures --output offline_followups
python benchmark_suite.py --mode live --supplemental --resume-fixtures --output live_followups
```

`mock` and `real` are aliases for `offline` and `live`. `--case` and `--category` can be repeated; the five source directories are `normal`, `boundary`, `clarification`, `stop`, and `followup`. `--stop-after N` retains the first N cases in the fixed catalog order and records both selected and completed counts. It is useful for bounded smoke runs and does not silently reduce the planned denominator. Existing output directory names are rejected. Omit `--output` for a timestamp and unique suffix. There is no resume/retry mechanism that can replace completed evidence; use a new output name for an explicitly separate run.

Offline is explicitly **MOCK**: source gold planning and rule-based stand-ins exercise graph mechanics, real Python statistics, pause/stop handling, and report validation. These results do not measure language-model accuracy. Live forces `create_agents({"mode": "real", ...})` with the two current configured models (`MODEL_A` and `MODEL_B`, or explicit `--model-a` and `--model-b`). It never uses automatic mode, trains weights, substitutes mocks after a failure, or sends source gold plans, expected roles, numeric references, labels, or results to the live agents. Provider/setup errors are retained for every affected case and the run continues. The per-request model-call cap defaults to the project's bound; `--max-model-calls` can lower or explicitly set it. The graph also retains its bounded plan repair, report revision, and clarification limits. Individual provider requests use the application's configured timeout.

Before any graph/tool/model input, the runner copies the exact source CSV bytes to `input.csv` in neutral directories identified by run and case hashes. The source category and case filename therefore cannot leak expected method, result, or safety behavior through `data_summary.data_path`. Source filenames and hashes are retained only in evaluator evidence. This blinding changes the harness input path; it does not alter the source data or the production prompts.

The planning input contains the unchanged source question, the source design declaration, and adapter metadata based on the visible CSV column representations. Numeric values remain numeric, source text labels remain categorical, and date strings are described as dates. This metadata is an evaluation declaration, not a model prediction or a source gold role assignment. No default outcome is supplied for regression. For Welch, the declared contrast is explicitly sorted-second minus sorted-first (treatment minus control), matching the source numerical effect. A live model that reverses this contrast is recorded as a deviation. Unknown independence cannot be inferred from data. Numeric category codes are not given invented textual meaning or source gold labels.

Our policy adaptations are registered separately from the unchanged source expectations:

| Source fixture | Registered behavior in our application | Reason |
|---|---|---|
| Missing cells | Pause before inference | Exclusion or correction needs an explicit answer. |
| IQR flags, including `welch_clean` | Pause before inference | Values outside the current fences require verification; “normal” is a source category, not permission to bypass a check. |
| `unknown_design` | Stop before planning/inference | Our independence check requires an explicit declaration. The source's synthetic answer is not a user response. |
| `ambiguous_outcome`, `regression_direction` | Safely stop with target unresolved | There is no arbitrary outcome or direction choice. If a live agent chooses one anyway, record the failure. |
| `chi_square_numeric_codes` | Stop pending confirmed semantics/new metadata | Codes alone do not confirm categorical meaning. If the user genuinely declares category levels, our tool can accept numeric-looking strings as labels; this fixture supplies no such confirmed declaration. |
| `regression_too_few` | Compute when otherwise valid | The source has four rows. Our minimum for identifiable regression is three; the source's higher threshold is not applied to ours. |
| `welch_extreme_small_group` | Pause about IQR flags | The source contains 25 observations per group. Our Welch minimum is two; an unverified extreme value remains a clarification issue. |
| Date-filter followups | Successful warmup, then unsupported stop | This application requires a new CSV to analyze a subset; it must not claim to have filtered rows. If warmup pauses or fails, the followup is explicitly unassessed. |

The primary outcome always preserves the first pause or stop. `--resume-fixtures` adds a separate, bounded **TEST FIXTURE** continuation stage. Its recipe is calculated independently from the frozen source values before agent execution: deliberately planted missing cells can exclude their exact source row; source-generated IQR observations can be retained with an explicit synthetic verification reason. Answers are only matched to registered exact row/field/check tuples and permitted actions. No other clarification is answered automatically. These are test answers justified by a synthetic dataset recipe, **not human responses, real-data verification, or human semantic review**. Without this flag, the graph remains paused. Continued states and approved exclusions are kept alongside the original state. The source CSV is never rewritten.

Numerical validation uses independent SciPy Welch/correlation calculations, an explicit chi-square table formula, and a separate least-squares design matrix with an intercept for OLS. It uses the actual runtime data path, confidence level, and approved exclusions. It checks sample counts, contrast order, estimate, p-value, interval, degrees of freedom, and method-specific fields. It does not reuse the source's stored numeric references, the application computation function, or an oracle for a guessed target. A reversed or changed target cannot receive a passing numeric score by recomputing its preferred answer. Regression warning checks retain influential-observation and heteroscedasticity diagnostics when numerical inference is reached. Agreement of calculations does not establish distributional assumptions.

Each unique `artifacts/benchmark_v2/<output>/` directory contains category JSON files, `results.json`, `REPORT.md`, the preregistration, protected tool audit files, and frozen report text files. Case evidence and the aggregate are saved after every case, including failures. Records include actual status, first clarification, model-call metadata, original diagnostics, continued stages, raw statistical results, report drafts, review verdicts, revisions, and errors. Credentials are redacted from serialized provider exception strings. Results distinguish method/safety/numeric mechanics from report delivery after program checks and Model B review. Correct statistics can be retained while a report is withheld. Neither code acceptance nor Model B is an independent human accuracy label.

`human_review.csv` is generated from frozen actual report texts and includes their hashes and file paths. It includes delivered reports and rendered drafts withheld by the gates, marked with their actual stage. Its human method, numeric, semantic, reviewer, date, and notes fields are deliberately blank. Filling those fields requires an independent reviewer; the runner never fabricates them.

Guarded model/tool exceptions cannot receive a passing mechanical score merely because an expected-stop fixture ended with status `stopped`. The `no_core_errors` check fails, and a safety behavior interrupted by an analysis-stage error is marked unassessed. Aggregate counts retain the unassessed denominator and infrastructure failures. Method/numerical evidence and report delivery remain available separately, including correct statistics when text was withheld.

`--supplemental` runs five of our own followup fixtures in a separate output directory and denominator: a correlation interval at 99%, a regression re-explanation, a regression interval at 99% after a labelled missing-row exclusion, a Welch re-explanation carrying missing-data limitations, and an interval request on a replacement regression CSV. The replacement file omits exactly the first frozen source row and retains all other values. Its fingerprint must trigger version `v2` and fresh diagnostics; unchanged data must retain its approved exclusions/version. Re-explanation must retain identical statistics. These are extra cases and do not turn the source's 31 into 36. A paused or failed warmup leaves the supplemental followup unassessed unless its preregistered TEST FIXTURE answers were explicitly enabled.

Runtime tool audits use short hashed directories under `artifacts/runtime/bench/`, and each row records that directory. Short thread tags prevent Windows filename length failures on the project path. Infrastructure errors carry a separate `failure_class`; they are not human semantic labels.

Git attributes disable line-ending normalization for frozen source fixtures and hashed
evaluation evidence so their byte checksums survive both Windows and Linux clones.
For the blank manual rating fields, use [the human evaluation rubric](HUMAN_EVALUATION_RUBRIC.md).

The shared helpers are `load_cases`/`cases`, `adapted_plan`, `fixture_tool_request`, and `build_protected_context`. Gold-plan helpers are for explicitly controlled synthetic/offline evaluation only. Calling `build_protected_context(case)` returns safe planning input; passing a computed `state` produces the application's protected drafting context. The controlled interpretation benchmark documents any direct tool execution separately from full graph safety-policy evaluation.
