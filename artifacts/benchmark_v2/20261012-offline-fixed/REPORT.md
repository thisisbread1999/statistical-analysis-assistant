# Adapted frozen four-method benchmark

MOCK: prespecified fixture plans and rule-based reports; mechanics only, NOT LLM accuracy

Source snapshot: `b7eff1c4a8035f196ac4bfc73ef3fe88956dadb5`. Completed 31/31 selected cases.
Mechanical method/safety/numeric checks: 31/31.
Independent numerical checks: 19/19 assessed computed cases.
Reports delivered after program checks and Model B: 19/19 computed cases.

Code acceptance and Model B review are not independent human semantic accuracy. Human labels remain blank.
Primary pauses are retained. Optional secondary answers are explicitly TEST FIXTURE synthetic recipes, not user decisions.
No training, mock fallback, cherry picking, or copying of teammate scores is performed.

| Category | Case | Primary status | Final status | Failed mechanical checks | Report accepted |
|---|---|---|---|---|---|
| normal | welch_clean | paused | delivered | none | True |
| normal | pearson_clean | delivered | delivered | none | True |
| normal | chi_square_2x2 | delivered | delivered | none | True |
| normal | regression_clean | delivered | delivered | none | True |
| boundary | welch_unequal_variance | paused | delivered | none | True |
| boundary | welch_missing | paused | delivered | none | True |
| boundary | pearson_missing | paused | delivered | none | True |
| boundary | chi_square_missing | paused | delivered | none | True |
| boundary | regression_missing | paused | delivered | none | True |
| boundary | chi_square_2x3 | delivered | delivered | none | True |
| boundary | pearson_nonlinear | delivered | delivered | none | True |
| boundary | regression_influential | paused | delivered | none | True |
| boundary | regression_heteroscedastic | paused | delivered | none | True |
| boundary | regression_negative_slope | delivered | delivered | none | True |
| clarification | unknown_design | stopped | stopped | none | False |
| clarification | ambiguous_outcome | stopped | stopped | none | False |
| clarification | ambiguous_last_year | delivered | stopped | none | True |
| clarification | regression_direction | stopped | stopped | none | False |
| stop | paired_design | stopped | stopped | none | False |
| stop | chi_square_sparse | stopped | stopped | none | False |
| stop | chi_square_one_category | stopped | stopped | none | False |
| stop | chi_square_numeric_codes | stopped | stopped | none | False |
| stop | pearson_constant | stopped | stopped | none | False |
| stop | pearson_too_few | stopped | stopped | none | False |
| stop | regression_constant | stopped | stopped | none | False |
| stop | regression_too_few | delivered | delivered | none | True |
| stop | regression_perfect | stopped | stopped | none | False |
| stop | welch_extreme_small_group | paused | delivered | none | True |
| stop | unsupported_multivariable | stopped | stopped | none | False |
| followup | correlation_2025 | delivered | stopped | none | True |
| followup | regression_2025 | delivered | stopped | none | True |
