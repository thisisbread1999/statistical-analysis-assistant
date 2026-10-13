> Historical reference: this unfinished R v2 contract is superseded by `PYTHON_TOOLS_SPEC.md`. Active v2 uses only Python.

# R tool interface (v2)

The Python workflow calls one R script for every statistical computation:

```
Rscript r/stats_tools.R <task> <request.json> <result.json>
```

* `task` is `summary`, `diagnostics` or `run_test`.
* Python writes `request.json`; R writes `result.json`. R never edits, drops or imputes data on its own. The only rows left out of the analysis set are those in `excluded_ids`, each backed by a user confirmation and a correction-log entry on the Python side.
* R exits with status 0 whenever it could write a result. Expected problems, such as a missing column or an unsupported request, go in `status` and are not errors. A non-zero exit means a genuine failure: the R error message goes to stderr.
* JSON arrays always stay arrays (length 0 or 1 included). Use `I()` / `as.list()` so that Python never receives a scalar where it expects a list.

## Request (all tasks)

```json
{
  "data_path": "C:/.../data/students_synthetic.csv",
  "data_version": "v1",
  "excluded_ids": ["S001"],
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

| field | meaning |
|---|---|
| `id_column` | Record identifier column, or `null`. Without one, record IDs are `"row 12"` (1-based data row number). |
| `method` | `welch_t_test`, `pearson_correlation`, `chi_square_independence` or `simple_linear_regression`. |
| `roles` | Welch: `outcome` (numeric) and `group` (categorical). Pearson: `x`, `y` (numeric). Regression: `x` = predictor, `y` = outcome (numeric). Chi-square: `x`, `y` (categorical). |
| `group_labels` | Welch only: `[group_1, group_2]`; Δ = mean(group_1) − mean(group_2). |
| `valid_ranges` | Optional, stated by the user: `{column: [min, max]}`. |
| `valid_levels` | Optional, stated by the user: `{column: [level, ...]}` for categorical columns. |
| `conf_level` | Confidence level for intervals (e.g. 0.95 or 0.99). |
| `alpha` | Significance level, used only to report the decision (`p < alpha`). |

Every result echoes `task`, `data_version`, `data_path`, `method`, `n_rows_in_file`, `columns_found`, `missing_required_columns` (the role columns, plus `id_column`, that are absent), `excluded_ids` and `r_version`, plus `status`.
If any required column is missing, `status = "missing_required_columns"` and nothing else is computed.

## Task `summary`: descriptive only, no verdicts

The shared input for the LLM diagnostic branch.

* `n_rows_in_analysis_set`
* `columns`: one object per column **used by the roles**: `name`, `role`, `n_blank`, `n_parseable_numeric`, `n_unique_as_written`.
  * For categorical roles, also `levels_as_written`: a list of `{label_as_written, quoted, n}`.
  * For numeric roles, also `quantiles` (`min, p05, p25, p50, p75, p95, max`, over finite values) and `mean` / `sd`.
* Welch only: `by_group_as_written`, giving per group label as written: `n, mean, sd, median, min, max` of finite outcome values.
* `stated_ranges`, `stated_levels`: echo of the request.

## Task `diagnostics`: rule-based checks

* `findings`: record-level, list of
  `{record_id, field, value_as_written, check, severity, detail}`.
  * `severity` is `"blocking"` (the test cannot run until resolved) or `"verify"` (plausible but unusual; ask the user).
  * `check` values:
    * `missing_id`, `duplicate_id` (only when `id_column` is given; the duplicate detail states the row count and that `exclude` removes all rows with that ID)
    * numeric role columns: `missing_value`, `non_numeric_value`, `non_finite_value`, `out_of_range` (only with `valid_ranges`)
    * categorical role columns: `missing_label`, `invalid_label`. With `valid_levels`, a label is invalid if it is not in the list; the detail says whether it matches after trimming/case. Without `valid_levels`, a label is invalid only if it differs from another observed label only by whitespace/case.
    * `boxplot_flag` (severity `verify`), computed on usable rows: Welch, outcome per group; Pearson and regression, `x` and `y` separately.
* `n_blocking`, `n_verify`, `n_usable_rows`
* `method_findings`: `{check, severity: "out_of_scope", detail}`, reported **only when `n_blocking == 0`**:
  * Welch: each of the two `group_labels` needs ≥ 2 usable rows and SD > 0; if, without `valid_levels`, the group column has a number of distinct usable labels other than 2 → `wrong_number_of_groups`.
  * Pearson: n ≥ 4 (needed for the CI), SD > 0 for `x` and `y`.
  * Regression: n ≥ 3, variance of `x` > 0.
  * Chi-square: each variable has ≥ 2 levels; Cochran rule violated (any expected count < 1, or more than 20 % of cells < 5) → `expected_counts_too_small` (the detail says that Fisher's exact test is not supported in this stage).
* `distribution_checks`, **only when `n_blocking == 0` and there are no `method_findings`**. Descriptive, never a method switch:
  * Welch: Shapiro-Wilk p per group.
  * Pearson: Shapiro-Wilk p for `x` and `y`.
  * Regression: Shapiro-Wilk p of the residuals, and `spread_check` = Spearman correlation between |residual| and fitted values (with p).
  * Chi-square: `min_expected_count`, `share_cells_expected_below_5`.
  * Shapiro-Wilk runs only for 3 ≤ n ≤ 5000; otherwise p is `null`.
* `distribution_checks_note`: text.

## Task `run_test`

Refuses (`status = "blocked"`, `reason`, `problem_ids`) if any record-level blocking problem remains in the analysis set.
Otherwise `status = "ok"` and, for every method: `method_label` (R's method string), `conf_level`, `alpha`, `n_included`, `r_call` (the R call as text, for transparency).

| method | additional fields |
|---|---|
| `welch_t_test` | `group_1`, `group_2` (`{label, n, mean, sd}`), `mean_difference` (group_1 − group_2), `ci_lower`, `ci_upper`, `t_statistic`, `df`, `p_value`, `var_equal: false` |
| `pearson_correlation` | `n`, `r`, `ci_lower`, `ci_upper`, `t_statistic`, `df`, `p_value` |
| `chi_square_independence` | `n`, `chi_square`, `df`, `p_value`, `cramers_v` (uncorrected: sqrt(chi2 / (n·(min(r,c)−1)))), `yates_correction` (TRUE for 2×2, R default), `observed` and `expected` as `{row_labels, col_labels, counts: [[...]]}`, `min_expected_count` |
| `simple_linear_regression` | `n`, `slope`, `slope_se`, `intercept`, `ci_lower`, `ci_upper` (slope), `t_statistic`, `df`, `p_value`, `r_squared` |

R calls: `t.test(x1, x2, alternative="two.sided", var.equal=FALSE, conf.level=conf_level)`; `cor.test(x, y, method="pearson", conf.level=conf_level)`; `chisq.test(table(x, y))`; `lm(y ~ x)` with `confint(fit, level=conf_level)`.
