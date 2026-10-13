# Alignment with the teammate's Python implementation

Reference reviewed: [Junliang-Lyu/statistical-analysis-assistant](https://github.com/Junliang-Lyu/statistical-analysis-assistant), commit `b7eff1c4a8035f196ac4bfc73ef3fe88956dadb5`.

Historical reference-verification record: the local reference checkout and fresh reference clone had the same commit. SHA-256 comparisons matched for `stat_assistant/tools.py`, `additional_tools.py`, `agents.py`, `workflow.py`, and `tests/test_four_methods.py`. The reference repository was not edited or pushed to. These checks identify the source snapshot; they do not describe current benchmark outcomes.

Our v2 uses Python throughout: LangGraph for orchestration and NumPy/SciPy for statistics. The frozen Module 6 v1 notebook and its historical R tool remain available separately. Migrating the statistical tool does not change the project's two-model review or user-confirmation requirements.

## File and folder alignment

Historical layout-stage check: the main branch was checked on 2026-10-12 and remained
at the reviewed reference commit. Our primary project names match its conventions:

| Teammate convention | Our current path |
|---|---|
| Python package | `stat_assistant/` |
| Agent/workflow/statistical modules | `stat_assistant/agents.py`, `stat_assistant/workflow.py`, `stat_assistant/tools.py` |
| CLI and teaching notebook | `demo.py`, `demo.ipynb` |
| Local browser server and frontend | `ui_server.py`, `ui/index.html`, `ui/app.js`, `ui/style.css` |
| Notebook builder | Root `build_notebook.py` |
| Synthetic examples | `examples/` |
| Diagram artifacts | `artifacts/graph.png`, `artifacts/graph.mmd` |
| Exact runtime pins | `requirements-lock.txt`, included by `requirements.txt` |
| Four-method benchmark entry point | Root `benchmark_suite.py`; frozen source cases in `examples/benchmark_v2/` and our policy adapter in `examples/benchmark_v2_adapted/` |
| Interpretation challenge entry point | Root `interpretation_benchmark.py`; controlled drafts in `examples/interpretation_checks/` |
| Current LangGraph assignment | `assignments/2026-10-12/langgraph/LangGraph_Submission.ipynb` and `graph.png` |

The complete old-to-new mapping is in [PROJECT_STRUCTURE.md](PROJECT_STRUCTURE.md).
Additional modules supporting our review and user-confirmation requirements remain
separate. The five original project CSVs keep their original filenames and provenance.
The additional 31 source CSV/JSON benchmark fixtures are frozen from reviewed commit
`b7eff1c`; source declarations and checksums are separate from our adapter and newly
computed results. No teammate result scores or model weights are adopted. The standalone
assignment embeds this project's implementation and the datasets selected by its builder.

Historical layout-stage verification: canonical `demo.ipynb` and the assignment notebook
were executed with explicitly labelled mock outputs. Earlier live outputs remain
separately preserved in `artifacts/verification/`, including the pre-layout notebook and
historical JSON evidence. Current evaluation outcomes must be read from newly saved
run artifacts and `docs/VERIFICATION.md`; a naming/layout change itself establishes no
new real-model evaluation result.

The local browser interface follows the teammate's filenames and visual layout, with
an adapter for our workflow. Leverage, Cook's distance, approximate Koenker
Breusch-Pagan diagnostics and the adapted 31-case benchmark are now implemented.
Date-filtering support and hosted deployment remain outside this project.

## Browser interface adaptation

The interface runs through `python ui_server.py --port 8765` at
[http://127.0.0.1:8765](http://127.0.0.1:8765), using Python's standard-library HTTP
server bound to `127.0.0.1`. The frontend retains the question, example/upload,
report and execution-trail structure while the backend uses our own 17-node graph.
The teammate's reviewed graph and state schema are not substituted for our implementation.

Execution modes are explicitly **mock** (rule-based agents with real Python statistics)
or **real** (two configured distinct models, locally defaulting to Ollama `qwen3:8b`
and `gemma3:12b`). The ten built-in scenarios use our five original synthetic CSVs
plus the source `regression_influential.csv` and `regression_heteroscedastic.csv`
benchmark fixtures. They exercise four methods, messy data, non-significance,
unequal variances, an unsupported design and regression diagnostics. These browser
scenarios are demonstrations; the separate benchmark runner covers the 31-case
catalog and records its evaluation evidence.

Uploaded CSVs require explicitly reviewed study/variable metadata JSON. The browser
shows our per-record clarification requests and collects explicit permitted actions
with optional source/reason notes. Corrections require valid replacement values.
An omitted note is stored as an empty string and shown as "No note provided" in the
UI. It does not silently apply `dropna()`, generate user confirmations or invent
reasons. Follow-ups reuse
or recompute evidence according to our existing policy. Date filters still require a
new CSV. Submitted jobs are polled by the browser; graph session memory clears on server
restart. Uploads and session files are stored locally in ignored `artifacts/runtime/ui/`,
alongside the core runtime correction/audit files. UI adapter checks are kept in
`tests/test_ui_server.py`; their executed results are recorded separately in the
verification record.

## Method mapping and numerical conventions

| Our canonical method | Teammate's result name / accepted tool alias | Shared calculation and interpretation |
|---|---|---|
| `welch_t_test` | `welch_t_test` | Two-sided independent-group Welch test; unequal variances allowed. |
| `pearson_correlation` | `pearson` | Pearson linear correlation, two-sided null test, Fisher-z confidence interval. |
| `chi_square_independence` | `chi_square` | Pearson chi-square independence test without Yates correction; uncorrected Cramer's V. |
| `simple_linear_regression` | `linear_regression` | One numeric predictor, numeric outcome, intercept, ordinary slope t-test and interval. |

The tool also accepts `welch` and `welch_ttest` as method aliases. Plans, memory and reports use our canonical names. The legacy task name `welch_test` is separate from these method aliases and is accepted only for Welch.

### Welch comparison

Both implementations use `scipy.stats.ttest_ind(..., equal_var=False)`. Our `group_labels=[group_1, group_2]` defines the signed difference as mean(group_1) minus mean(group_2). The teammate's code sorts observed labels and subtracts the first from the second. We retain explicit order from the analysis plan instead of adopting the sorting convention. A comparison against the teammate's output must therefore align the contrast before comparing signs and interval endpoints.

Our confidence interval uses the requested `conf_level`, including a follow-up request for 99%. Alpha remains the prespecified 0.05 in the graph. Changing only the confidence level does not change the null hypothesis, p-value or decision threshold.

### Pearson correlation

Both implementations use SciPy's two-sided Pearson test. Our interval explicitly applies the Fisher transformation, `atanh(r) +/- z_critical / sqrt(n - 3)`, and then transforms back with `tanh`. This agrees with the default non-bootstrap interval from `pearsonr(...).confidence_interval(...)` on ordinary data.

At a numerically perfect sample correlation, the tool reports the boundary interval, a null t-statistic with an explanatory note, and a warning that a zero-width limiting interval does not establish a deterministic population relationship. The report must retain this warning.

### Chi-square independence

Both use `scipy.stats.chi2_contingency(observed, correction=False)`, including 2-by-2 tables. This explicitly replaces the Yates-corrected 2-by-2 default described in the earlier R interface draft. Cramer's V uses the same uncorrected statistic:

`V = sqrt(chi_square / (n * min(number_of_rows - 1, number_of_columns - 1)))`.

V is unsigned association strength. No V confidence interval is implemented, so the report must not invent one and a confidence-level follow-up is stopped for this method. Both implementations stop when any expected cell count is below one or more than twenty percent of expected counts are below five. This is the documented approximation policy, not proof that every accepted table has an accurate approximation. There is no automatic Fisher-exact fallback.

### Simple linear regression

The teammate uses `scipy.stats.linregress`. Our tool calculates centered ordinary least squares with NumPy and uses SciPy's t distribution for slope inference. Both fit `y = intercept + slope * x`, use residual degrees of freedom `n - 2`, and report slope, standard error, intercept, R-squared, two-sided p-value and a slope confidence interval. The interval is not a prediction interval. Our critical value uses the requested confidence level instead of a fixed 95%. Added descriptive diagnostics do not change this estimator, p-value or interval.

Historical selected-case numerical verification: a normal-data check compared our centered implementation with `linregress`; the largest absolute difference among the checked slope, p-value and interval endpoints was approximately `1.6e-15`. Welch and Pearson checks at 99% confidence and a 2-by-2 chi-square/V check also matched direct SciPy references in that check. This record is numeric verification of selected cases, not an assessment of model reasoning accuracy or a current benchmark score.

## Deliberate differences retained

- **Two different models.** Model A plans, diagnoses and writes; Model B independently receives the report and original evidence for review. The teammate's reviewed version uses one configured DeepSeek model for planning and interpretation, with a deterministic critique step. We do not replace our separate reviewer with that arrangement.
- **No silent complete-case deletion.** The teammate's preparation function uses `dropna()`. Our raw CSV is preserved, missing values block inference, and the graph requires an explicit permitted user action before exclusion. Source/reason notes are optional under the user's updated policy. Approved data changes create new versions; the correction log records actions, affected cells/records, old/new values and any supplied notes without generating reasons. Boxplot flags lead to verification, not automatic deletion.
- **User-supplied study design.** Independence and randomization cannot be inferred from a CSV. Unconfirmed or unsupported designs stop the analysis. Observational comparisons do not establish causal effects.
- **Bounded revision.** The graph retains one automatic plan revision and one report revision, plus explicit clarification and model-call limits. Both program checks and Model B must accept a delivered report.
- **Evidence-preserving follow-ups.** Re-explanation reuses a completed result; a new confidence level recomputes its interval on unchanged validated data. Changes of variables, data or design require the appropriate fresh plan/diagnostics. A requested subset or date filter is unsupported in this stage and requires a new CSV.
- **Our result schema.** Names such as `p_value`, `ci_lower`, `group_1`, `data_version` and the correction log remain stable. An identical internal dictionary layout is not required to use the same statistical methods.

## Diagnostic policy differences

The teammate's minimum of five observations per Welch group and five regression observations is its service policy. Our current computational minimum is two observations per Welch group, four pairs for Pearson's Fisher interval and three pairs for regression. These minima do not certify valid inference or adequate power, and tiny samples provide weak diagnostic information. Zero/nonfinite variation and degenerate regression residual variance stop inference.

Our normality checks are descriptive and do not select a different estimand or method.
Regression retains residual Shapiro-Wilk and the descriptive Spearman spread check,
and now returns row-linked leverage and Cook's distance plus approximate Koenker
studentized Breusch-Pagan LM. Leverage is `1/n + (x_i-mean(x))^2/Sxx`, with threshold
`2p/n = 4/n` for `p = 2`; Cook's distance uses internally standardized residuals and
threshold `4/n`. The variance LM is `n * R_squared` from squared residuals regressed
on an intercept and x, with an asymptotic chi-square p-value and one degree of freedom.
This is the Koenker variant rather than the original normal-error BP statistic.

Our `regression_diagnostics` object preserves original record IDs and source row
numbers after explicit exclusions. Undefined Cook distances at numerically unit
leverage and unavailable auxiliary variance tests use null with an explanation;
we do not replace a singular Cook denominator with epsilon. All such warnings are
nonblocking, add no new verification findings and never remove a record. Existing
IQR flags still require the graph's explicit human decision. Influence, leverage,
heteroscedasticity and unavailable-measure limitations are required in reports;
program checks reject omissions, and the browser displays diagnostic numbers, IDs
and warnings. No diagnostic proves independence, the correct linear model,
normality or constant variance. The exact schema is in [PYTHON_TOOLS_SPEC.md](PYTHON_TOOLS_SPEC.md).

Program checks protect required numeric placeholders, reject literal numbers and simple field swaps, and check declared direction/decision and required limitation IDs. They do not provide complete semantic validation. Model B addresses meaning and unsupported claims, but agreement between two models is not a correctness guarantee. Independent human evaluation remains separate and unscored until real labels are supplied.

## Evaluation alignment and provenance

Root `benchmark_suite.py` executes the frozen 31-case catalog across normal,
boundary, clarification, stop and follow-up categories. It keeps the source CSV/JSON
declarations and source README score statements intact as historical provenance at
`b7eff1c`. Our adapter records deliberate differences: unresolved missing/IQR issues
pause; unknown or ambiguous targets stop; date filters require a new CSV; and the
source four-row regression fixture can compute under our minimum-three policy.
Optional `--resume-fixtures` continuations use predeclared, labelled synthetic TEST
recipes; the original pause is retained and no real user verification is claimed.
Source gold plans support only labelled offline mechanics and independent evaluation,
not live planning inputs.

Root `interpretation_benchmark.py` contains 16 controlled challenges: four valid
templates and twelve authored mutations adapted to this project's report schema.
Python recalculates the statistical evidence. Program checks and Model B review run
independently on every prepared draft, including drafts the program rejects; the
reviewer does not receive expected labels or checker feedback. Live mode calls Model
B on controlled drafts and makes no claim about Model A's generation error rate.

New outputs belong to `artifacts/benchmark_v2/<run>/` and
`artifacts/interpretation_checks/<run>/`. Offline and live runs have separate evidence
directories, mode labels, configurations and per-case evidence. Failures remain
visible. Numerical agreement, mechanical behavior and controlled detector coverage
are reported separately from semantic correctness. Human review fields remain blank;
source scores are not imported, and evaluation does not train or change model weights.
Read saved run artifacts and [VERIFICATION.md](VERIFICATION.md) for executed outcomes;
this alignment document does not state current pass totals or promise live scores.
