# Alignment with the teammate's Python implementation

Reference reviewed: [Junliang-Lyu/statistical-analysis-assistant](https://github.com/Junliang-Lyu/statistical-analysis-assistant), commit `b7eff1c4a8035f196ac4bfc73ef3fe88956dadb5`.

The existing local reference checkout and the fresh reference clone had the same commit. SHA-256 comparisons also matched for `stat_assistant/tools.py`, `additional_tools.py`, `agents.py`, `workflow.py`, and `tests/test_four_methods.py`. The reference repository was not edited or pushed to.

Our v2 uses Python throughout: LangGraph for orchestration and NumPy/SciPy for statistics. The frozen Module 6 v1 notebook and its historical R tool remain available separately. Migrating the statistical tool does not change the project's two-model review or user-confirmation requirements.

## File and folder alignment

The main branch was checked again on 2026-10-12 and remained at the reviewed reference
commit. Our primary project names now match its conventions:

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
| Current LangGraph assignment | `assignments/2026-10-12/langgraph/LangGraph_Submission.ipynb` and `graph.png` |

The complete old-to-new mapping is in [PROJECT_STRUCTURE.md](PROJECT_STRUCTURE.md).
Additional modules supporting our review and user-confirmation requirements remain
separate. Active examples keep our original synthetic filenames and are byte-identical
copies of the preserved files in `data/`; the teammate's data and outputs are not used.
The standalone assignment embeds our own source and datasets.

Canonical `demo.ipynb` and the assignment notebook have fresh, explicitly labelled mock
outputs. Earlier live outputs remain separately preserved in `artifacts/verification/`,
including the pre-layout notebook and historical JSON evidence. A naming/layout change
does not establish new real-model evaluation results.

The local browser interface now follows the teammate's filenames and visual layout,
with an adapter for our workflow. Date-filtering support, extra regression diagnostics,
hosted deployment and the 31-case benchmark remain outside this project.

## Browser interface adaptation

The interface runs through `python ui_server.py --port 8765` at
[http://127.0.0.1:8765](http://127.0.0.1:8765), using Python's standard-library HTTP
server bound to `127.0.0.1`. The frontend retains the question, example/upload,
report and execution-trail structure while the backend uses our own 17-node graph.
The teammate's reviewed graph and state schema are not substituted for our implementation.

Execution modes are explicitly **mock** (rule-based agents with real Python statistics)
or **real** (two configured distinct models, locally defaulting to Ollama `qwen3:8b`
and `gemma3:12b`). Built-ins use our five synthetic CSVs to exercise four methods,
messy data, non-significance, unequal variances and an unsupported design.
They do not constitute the teammate's 31-case benchmark or an accuracy evaluation.

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

The teammate uses `scipy.stats.linregress`. Our tool calculates centered ordinary least squares with NumPy and uses SciPy's t distribution for slope inference. Both fit `y = intercept + slope * x`, use residual degrees of freedom `n - 2`, and report slope, standard error, intercept, R-squared, two-sided p-value and a slope confidence interval. The interval is not a prediction interval. Our critical value uses the requested confidence level instead of a fixed 95%.

An independent normal-data check compared our centered implementation with `linregress`: the largest absolute difference among the checked slope, p-value and interval endpoints was approximately `1.6e-15`. Independent Welch and Pearson checks at 99% confidence and a 2-by-2 chi-square/V check matched the direct SciPy references in that check. This is numeric verification of selected cases, not an assessment of model reasoning accuracy.

## Deliberate differences retained

- **Two different models.** Model A plans, diagnoses and writes; Model B independently receives the report and original evidence for review. The teammate's reviewed version uses one configured DeepSeek model for planning and interpretation, with a deterministic critique step. We do not replace our separate reviewer with that arrangement.
- **No silent complete-case deletion.** The teammate's preparation function uses `dropna()`. Our raw CSV is preserved, missing values block inference, and the graph requires an explicit permitted user action before exclusion. Source/reason notes are optional under the user's updated policy. Approved data changes create new versions; the correction log records actions, affected cells/records, old/new values and any supplied notes without generating reasons. Boxplot flags lead to verification, not automatic deletion.
- **User-supplied study design.** Independence and randomization cannot be inferred from a CSV. Unconfirmed or unsupported designs stop the analysis. Observational comparisons do not establish causal effects.
- **Bounded revision.** The graph retains one automatic plan revision and one report revision, plus explicit clarification and model-call limits. Both program checks and Model B must accept a delivered report.
- **Evidence-preserving follow-ups.** Re-explanation reuses a completed result; a new confidence level recomputes its interval on unchanged validated data. Changes of variables, data or design require the appropriate fresh plan/diagnostics. A requested subset or date filter is unsupported in this stage and requires a new CSV.
- **Our result schema.** Names such as `p_value`, `ci_lower`, `group_1`, `data_version` and the correction log remain stable. An identical internal dictionary layout is not required to use the same statistical methods.

## Diagnostic policy differences

The teammate's minimum of five observations per Welch group and five regression observations is its service policy. Our current computational minimum is two observations per Welch group, four pairs for Pearson's Fisher interval and three pairs for regression. These minima do not certify valid inference or adequate power, and tiny samples provide weak diagnostic information. Zero/nonfinite variation and degenerate regression residual variance stop inference.

Our normality checks are descriptive and do not select a different estimand or method. Regression currently includes a descriptive rank correlation of absolute residuals with fitted values. The teammate's Cook's-distance and heteroscedasticity diagnostics are not represented as implemented here. Neither diagnostic set establishes independence, a correct linear model, normality or constant error variance.

Program checks protect required numeric placeholders, reject literal numbers and simple field swaps, and check declared direction/decision and required limitation IDs. They do not provide complete semantic validation. Model B addresses meaning and unsupported claims, but agreement between two models is not a correctness guarantee. Offline human evaluation remains a separate task.
