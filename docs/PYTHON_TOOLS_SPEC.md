# Python statistical-tool interface (v2)

The active graph in `stat_assistant/workflow.py` calls Python functions in `stat_assistant/tools.py`; it does not launch R. These module names follow the teammate's layout. The historical R specification is retained as v1/design history. See `docs/PROJECT_STRUCTURE.md` for the path mapping.

```python
from stat_assistant.tools import execute
result = execute("diagnostics", request)

# The graph uses this wrapper to retain input/output JSON for audit:
from stat_assistant.tool_bridge import run_stat_tool
result = run_stat_tool("diagnostics", request, tag="example-request")
```

`execute(task, request)` reads the CSV and returns a JSON-compatible dictionary. `run_stat_tool` additionally saves uniquely named request/result files beneath ignored `artifacts/runtime/stat_io`; it records unexpected failures as `tool_error` before raising `StatToolError`. No LLM arithmetic or generated executable analysis code is used.

## Tasks and request

The tasks are `summary`, `diagnostics` and `run_test`. `welch_test` remains a legacy task alias restricted to a Welch request. New callers should use `run_test` and supply explicit roles.

```json
{
  "data_path": "C:/project/examples/students_synthetic.csv",
  "data_version": "v1",
  "excluded_ids": [],
  "id_column": "student_id",
  "method": "welch_t_test",
  "roles": {"outcome": "score", "group": "tutoring"},
  "group_labels": ["yes", "no"],
  "valid_ranges": {"score": [0, 100]},
  "valid_levels": {"tutoring": ["yes", "no"]},
  "conf_level": 0.95,
  "alpha": 0.05
}
```

| Field | Meaning |
|---|---|
| `data_path` | CSV file to read; never overwritten by this tool. |
| `data_version` | Caller-assigned version, echoed in the result. The graph separately checks the file fingerprint. |
| `excluded_ids` | Explicitly approved record IDs omitted from this request; default empty. |
| `id_column` | ID column, or null. Without a usable ID, diagnostic references use `row N`, with one-based data row numbering. |
| `method` | One of the four canonical methods below, or a supported alias. |
| `roles` | Distinct existing columns appropriate for that method; the ID column cannot serve as a role. |
| `group_labels` | Welch only: two labels in subtraction order, group 1 minus group 2. |
| `valid_ranges` | Optional user-stated numeric bounds, inclusive. |
| `valid_levels` | Optional user-stated, exact categorical labels. |
| `conf_level` | Finite number strictly between zero and one; defaults to 0.95. |
| `alpha` | Finite number strictly between zero and one; defaults to 0.05. The graph fixes this at 0.05. |

| Canonical method | Required roles | Tool aliases |
|---|---|---|
| `welch_t_test` | `outcome`: numeric; `group`: categorical | `welch`, `welch_ttest` |
| `pearson_correlation` | `x`, `y`: numeric | `pearson` |
| `chi_square_independence` | `x`, `y`: categorical | `chi_square` |
| `simple_linear_regression` | `x`: numeric predictor; `y`: numeric outcome | `linear_regression` |

The tool validates structure and data; it does not authenticate a user's approval. The graph must supply only exclusions backed by validated answers and log entries. Independence, variable meanings and study design are also graph/user responsibilities, not facts established by numeric parsing.

## Raw data and result status

The CSV reader preserves cells as strings, including whitespace and capitalization, and checks nonempty unique headers and row width. Blank/whitespace-only cells and the literal `NA` are treated as missing. Numeric roles are parsed explicitly. A string such as `"yes "` is not silently changed to `"yes"`; nonnumeric and nonfinite numeric values remain diagnostic findings. Other arbitrary missing-value codes are not guessed.

Only the requested `excluded_ids` are removed from the analysis set. Excluding an ID duplicated in several rows excludes every row with that ID; the graph must explain this before accepting the answer. An absent exclusion ID generates a request warning. The tool never edits, imputes, deduplicates, rescales or automatically discards an outlier.

Common metadata include `task`, canonical `method`, `request_format`, `data_path`, `data_version`, `n_rows_in_file`, `columns_found`, `missing_required_columns`, `excluded_ids`, `request_warnings`, `python_version`, `scipy_version` and a transparent `tool_call` description.

| Status / exception | Meaning |
|---|---|
| `ok` | Requested task completed; inspect diagnostic findings before inference. |
| `unsupported_request` | Invalid request structure, roles, bounds or parameters; nothing computed. |
| `missing_required_columns` | One or more role/ID columns are absent. |
| `blocked` | `run_test` refused unresolved blocking record-level problems. |
| `out_of_scope` | `run_test` refused unmet method requirements. |
| `StatToolError` | File/CSV failure or unexpected numerical/output failure; graph error routing stops delivery. |

Outputs are strict JSON: NaN and Infinity cannot silently enter saved results. A specifically documented unavailable statistic may use null, such as t at perfect sample correlation.

## `summary`

Summary is descriptive input shared with Model A. It does not authorize the test.

- `n_rows_in_analysis_set` counts rows after explicit exclusions.
- `columns` includes each role column's name, role, type, missing count, numeric-parse count and number of distinct written values.
- Categorical columns include `levels_as_written`: exact label, quoted form and count.
- Numeric columns include finite-value quantiles, mean and sample SD. Quantiles are min, p05, p25, p50, p75, p95 and max.
- Welch adds `by_group_as_written`, preserving every observed written group label, with finite-outcome n/mean/SD/median/min/max.
- `stated_ranges` and `stated_levels` echo caller metadata.

Finite-value summaries intentionally omit invalid numbers from the descriptive calculation. This is not complete-case permission: `run_test` independently checks every included record and refuses blocking issues.

## `diagnostics`

Each `findings` entry contains `record_id`, `row_number`, `field`, `value_as_written`, `check`, `severity` and `detail`.

| Check | Severity / action |
|---|---|
| `missing_id`, `duplicate_id` | Blocking; resolve identity or explicitly exclude. |
| `missing_value`, `non_numeric_value`, `non_finite_value` | Blocking numeric-role problem. |
| `out_of_range` | Blocking violation of user-stated bounds. |
| `missing_label`, `invalid_label` | Blocking categorical-role problem. |
| `boxplot_flag` | Verify a plausible unusual value; never auto-exclude. |

With declared levels, categorical matches must be exact. Without them, observed labels differing only by whitespace/case are flagged for clarification. Normalized strings help explain the conflict but are never substituted into the source data. Boxplot flags use 1.5-IQR fences on usable rows, by group for Welch and separately on x/y for Pearson or regression.

The response includes `n_blocking` and `n_verify` (counts of findings), `n_usable_rows`, `method_checks_run`, `method_findings`, `distribution_checks_run`, `distribution_checks` and `distribution_checks_note`. More than one finding may refer to the same record.

Method checks are deferred until blocking record-level issues are resolved:

| Method | Computational requirements / stopping policy |
|---|---|
| Welch | Exactly the two requested observed groups; at least two observations per group; positive finite within-group variance. No third group is silently discarded. |
| Pearson | At least four pairs for the Fisher interval; positive finite variance in both variables. |
| Simple regression | At least three pairs; positive finite variance in both variables; finite fit and positive, nondegenerate residual variance/standard error. |
| Chi-square | At least two observed levels per variable; no expected count below one and at most twenty percent below five. |

These minimum sample sizes are computational policy, not sufficient evidence of valid assumptions, adequate power or reliable small-sample diagnostics. No automatic Mann-Whitney, Spearman-inference or Fisher-exact fallback changes the research question.

When data and method requirements pass, descriptive distribution checks are:

- Welch: Shapiro-Wilk per group.
- Pearson: Shapiro-Wilk for x and y separately. These do not establish linearity or joint normality.
- Regression: Shapiro-Wilk for residuals; a descriptive Spearman correlation between absolute residuals and fitted values. The separate `regression_diagnostics` object adds leverage, Cook's distance and an approximate Koenker Breusch-Pagan variance diagnostic.
- Chi-square: minimum expected count and share of expected counts below five.

Shapiro-Wilk runs only for 3 through 5000 nonconstant observations; otherwise its p-value is null. A large p-value does not establish normality and a small p-value does not mechanically select another method. Welch does not require equal variances, so an equal-variance pretest is not a gate.

### Regression diagnostic object

For an accepted regression fit, `diagnostics` and successful `run_test` return the same
`regression_diagnostics` object. When record-level or method requirements defer the fit,
the diagnostics response contains `regression_diagnostics: null`; a blocked or
out-of-scope test does not report fitted diagnostic values.

```text
regression_diagnostics = {
  n: integer,
  parameter_count: 2,
  thresholds: {cooks_distance: number, leverage: number},
  max_leverage: number,
  max_cooks_distance: number | null,
  high_leverage_ids: [record_id, ...],
  influential_ids: [record_id, ...],
  observations: [
    {record_id: string, row_number: integer,
     leverage: number, cooks_distance: number | null}, ...
  ],
  breusch_pagan: {
    lm_statistic: number | null, p_value: number | null, df: 1,
    method: string, note: string
  },
  warnings: [{code: string, message: string}, ...]
}
```

Rows retain original source `record_id` and one-based data `row_number` after the
current request's explicit exclusions; a missing ID column uses `row N`. No warning
changes the fit, estimator, slope p-value or confidence interval.

For the one-predictor OLS fit with intercept, the parameter count is `p = 2`,
`Sxx = sum((x - mean(x))^2)` and leverage is
`h_i = 1/n + (x_i - mean(x))^2 / Sxx`. The high-leverage screening threshold is
`2p/n = 4/n`. With `MSE = SSE/(n-p)` and the internally standardized residual
`r_i = residual_i / sqrt(MSE * (1-h_i))`, Cook's distance is
`D_i = (r_i^2/p) * h_i/(1-h_i)`. Potential influence is flagged at `D_i > 4/n`.
These are screening thresholds rather than rules for deleting observations.

Cook's distance is null when leverage is within `32 * machine_epsilon` of one,
outside its numerical domain, or its arithmetic is not finite. The implementation
does not replace a singular denominator with epsilon and claim a measured distance.
If any row's distance is unavailable, the overall `max_cooks_distance` is null;
defined influential distances can still be flagged. A null value does not establish
absence of influence.

The field named `breusch_pagan` contains the **Koenker studentized Breusch-Pagan**
variant: regress squared OLS residuals on an intercept and x, calculate
`LM = n * auxiliary_R_squared`, and use the approximate upper-tail chi-square
probability with one degree of freedom. The diagnostic is flagged at `p_value < 0.05`.
It is not the original normal-error Breusch-Pagan statistic or a robust covariance
estimator. Residual scaling before squaring preserves auxiliary R-squared and avoids
overflow/underflow from units. With no numerical variation in squared residuals, or
unrepresentable auxiliary arithmetic, the statistic and p-value are null with a warning.
The asymptotic test can exaggerate significance in small samples; a large p-value
does not establish constant variance. See the
[official statsmodels test description](https://www.statsmodels.org/stable/generated/statsmodels.stats.diagnostic.het_breuschpagan.html)
for the distinction between the Koenker and original variants.

Warning codes are `influential_observations`, `high_leverage`, `heteroscedasticity`,
`cooks_distance_unavailable` and `breusch_pagan_unavailable`. They are descriptive,
nonblocking warnings: they do not add record findings, `n_verify` or `n_blocking`.
Existing IQR verification and explicit human decisions still apply independently.
The graph copies these diagnostics into the protected statistics block, requires
limitation IDs for influence, leverage and unequal variance, and requires
`regression_diagnostics_unavailable` when any measure is unavailable. Model A must
include the required limitations; the program rejects their omission. Fixed report
formatting and the browser show diagnostic values, flagged IDs and warning messages,
rendering unavailable numeric values as `unavailable`.

## `run_test`

The tool rechecks blocking data problems and method requirements before inference. The graph additionally requires resolution of outstanding `verify` findings, study-design questions and file-version checks; calling `run_test` directly does not perform those human/LLM workflow steps.

All successful methods return `n_included`, `method_label`, `conf_level`, `alpha`, `decision`, `tool_warnings`, `p_value` and `tool_call`. Tests of a signed scalar parameter are two-sided. Chi-square is an independence test using the upper-tail chi-square probability, not a directional signed-effect test.

| Method | Additional result fields and conventions |
|---|---|
| Welch | `group_1`, `group_2` each contain label/n/mean/SD; `mean_difference`, `ci_lower`, `ci_upper`, `t_statistic`, `df`, `var_equal=false`. Difference and CI follow the explicit group order. |
| Pearson | `n`, `r`, `ci_lower`, `ci_upper`, `t_statistic`, `df`, `ci_method`, `perfect_correlation`; t is null at the perfect-correlation boundary with `t_statistic_note` and warning. |
| Chi-square | `n`, `chi_square`, `df`, `cramers_v`, `yates_correction=false`, `observed`, `expected`, `min_expected_count`; each table includes row/column labels and nested counts. No effect CI is returned. |
| Regression | `n`, `slope`, `slope_se`, `intercept`, `ci_lower`, `ci_upper` for the slope, `t_statistic`, `df`, `r_squared`, and the descriptive `regression_diagnostics` object above. |

Welch uses SciPy's unequal-variance t-test and its requested-level interval. Pearson uses SciPy's test and the Fisher-z normal interval. Chi-square uses `correction=False`; Cramer's V is `sqrt(chi_square / (n * (min(table_shape) - 1)))`. Regression uses centered NumPy OLS with an intercept and SciPy's t distribution, with df `n-2` and interval `slope +/- t_critical * slope_se`.

The graph builds a protected statistics block from saved results. Model A writes allowed placeholders; the program inserts the values and performs mechanical checks. Model B reviews the rendered text and original evidence. This checking does not rerun the statistical test. Follow-up changes of confidence level do rerun the tool; re-explanation alone reuses the validated result.

### Protected hypothesis and conclusion fields

In addition to estimates and intervals, the program supplies `null_value` (zero),
`decision_claim` (the computed reject/do-not-reject wording) and `direction_claim`
(the computed sign). The wording check runs after protected fields are rendered. A
method-matched `H0 (slope = {null_value})` is distinguished from the estimated slope;
an estimated-slope statement using the null value is still rejected. These are fixed
program-owned hypothesis/conclusion fields, not model-generated numerical results.

## Evaluation evidence

Root `benchmark_suite.py` runs the frozen 31 source CSV/JSON cases in
`examples/benchmark_v2/`, with provenance at teammate commit `b7eff1c` and separate
project-specific declarations in `examples/benchmark_v2_adapted/`. It records our
intentional pauses for missing/IQR issues, unsupported date filters and regression
minimum of three pairs instead of silently adopting source policies. Root
`interpretation_benchmark.py` contains 16 controlled challenges: four valid templates
and twelve authored mutations. It recomputes statistics and checks the program and
reviewer separately; live interpretation mode calls Model B, not Model A.

New results belong to separate run directories under `artifacts/benchmark_v2/` and
`artifacts/interpretation_checks/`, with offline/live mode and configuration recorded.
Source fixture declarations and source README scores are preserved as provenance,
not copied into our result claims. Offline mechanical checks, independent numeric
agreement and controlled detector coverage are different measures. None supplies
independent human semantic accuracy or changes model training weights. Consult
`docs/VERIFICATION.md` and each saved run for executed outcomes; this interface
specification does not promise current pass counts or live scores.
