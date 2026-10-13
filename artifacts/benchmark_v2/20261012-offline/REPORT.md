# Adapted frozen four-method benchmark

MOCK: prespecified fixture plans and rule-based reports; mechanics only, NOT LLM accuracy

Source snapshot: `b7eff1c4a8035f196ac4bfc73ef3fe88956dadb5`. Completed 31/31 selected cases.
Mechanical method/safety/numeric checks: 17/31.
Independent numerical checks: 5/5 assessed computed cases.
Reports delivered after program checks and Model B: 5/5 computed cases.

Code acceptance and Model B review are not independent human semantic accuracy. Human labels remain blank.
Primary pauses are retained. Optional secondary answers are explicitly TEST FIXTURE synthetic recipes, not user decisions.
No training, mock fallback, cherry picking, or copying of teammate scores is performed.

| Category | Case | Primary status | Final status | Failed mechanical checks | Report accepted |
|---|---|---|---|---|---|
| normal | welch_clean | paused | delivered | none | True |
| normal | pearson_clean | delivered | delivered | none | True |
| normal | chi_square_2x2 | delivered | delivered | none | True |
| normal | regression_clean | stopped | stopped | primary_safety_behavior | False |
| boundary | welch_unequal_variance | stopped | stopped | primary_safety_behavior | False |
| boundary | welch_missing | paused | delivered | none | True |
| boundary | pearson_missing | stopped | stopped | primary_safety_behavior | False |
| boundary | chi_square_missing | stopped | stopped | primary_safety_behavior | False |
| boundary | regression_missing | stopped | stopped | primary_safety_behavior | False |
| boundary | chi_square_2x3 | delivered | delivered | none | True |
| boundary | pearson_nonlinear | stopped | stopped | primary_safety_behavior | False |
| boundary | regression_influential | stopped | stopped | primary_safety_behavior | False |
| boundary | regression_heteroscedastic | stopped | stopped | primary_safety_behavior | False |
| boundary | regression_negative_slope | stopped | stopped | primary_safety_behavior | False |
| clarification | unknown_design | stopped | stopped | none | False |
| clarification | ambiguous_outcome | stopped | stopped | none | False |
| clarification | ambiguous_last_year | stopped | stopped | primary_safety_behavior | False |
| clarification | regression_direction | stopped | stopped | none | False |
| stop | paired_design | stopped | stopped | none | False |
| stop | chi_square_sparse | stopped | stopped | none | False |
| stop | chi_square_one_category | stopped | stopped | none | False |
| stop | chi_square_numeric_codes | stopped | stopped | none | False |
| stop | pearson_constant | stopped | stopped | none | False |
| stop | pearson_too_few | stopped | stopped | none | False |
| stop | regression_constant | stopped | stopped | none | False |
| stop | regression_too_few | stopped | stopped | primary_safety_behavior | False |
| stop | regression_perfect | stopped | stopped | none | False |
| stop | welch_extreme_small_group | stopped | stopped | primary_safety_behavior | False |
| stop | unsupported_multivariable | stopped | stopped | none | False |
| followup | correlation_2025 | stopped | stopped | primary_safety_behavior | False |
| followup | regression_2025 | stopped | stopped | primary_safety_behavior | False |
