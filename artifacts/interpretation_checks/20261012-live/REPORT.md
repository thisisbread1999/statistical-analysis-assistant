# Interpretation challenge evaluation

Four valid controlled templates and twelve authored mutations; Python statistics are real. Model A is not called.

Mode: live. Reviewer: ollama:gemma3:12b.

All labels are authored test expectations. These counts are detector coverage on controlled drafts, not human semantic ratings or an error rate for real Model A outputs.

| Detector | Valid accepted | Valid false alarms | Valid unassessed | Planted caught | Planted missed | Planted unassessed |
|---|---:|---:|---:|---:|---:|---:|
| program | 4/4 | 0 | 0 | 4/12 | 8 | 0 |
| reviewer_b | 3/4 | 1 | 0 | 10/12 | 2 | 0 |
| combined | 3/4 | 1 | 0 | 10/12 | 2 | 0 |

Combined acceptance requires both detectors to accept. A detector error produces an unassessed result and receives no detection credit.

| Challenge | Expected valid | Program accepts | Reviewer B accepts | Combined accepts | Note |
|---|---|---|---|---|---|
| chi_square_2x2_valid | True | True | True | True | Correct controlled template using this project's tool placeholders and required limitations. |
| pearson_clean_valid | True | True | False | False | Correct controlled template using this project's tool placeholders and required limitations. |
| regression_clean_valid | True | True | True | True | Correct controlled template using this project's tool placeholders and required limitations. |
| welch_clean_valid | True | True | True | True | Correct controlled template using this project's tool placeholders and required limitations. |
| chi_square_2x2_causal | False | True | False | False | Append an unqualified causal assertion to an observational analysis. |
| chi_square_2x2_wrong_number | False | False | False | False | Replace the protected p-value placeholder with an unsupported numerical literal. |
| nonlinear_no_relationship | False | True | False | False | Claim no relationship from a near-zero Pearson correlation despite the U-shaped source data. |
| pearson_clean_causal | False | True | False | False | Append an unqualified causal assertion to an observational analysis. |
| pearson_clean_wrong_number | False | False | False | False | Replace the protected p-value placeholder with an unsupported numerical literal. |
| pearson_percent_misinterpretation | False | True | False | False | Describe a correlation coefficient as an eighty-percent increase using words. |
| regression_clean_causal | False | True | False | False | Append an unqualified causal assertion to an observational analysis. |
| regression_clean_wrong_number | False | False | False | False | Replace the protected p-value placeholder with an unsupported numerical literal. |
| regression_interval_probability | False | True | True | True | Assign a frequentist probability to the fixed true slope inside this observed interval. |
| welch_clean_causal | False | True | False | False | Append an unqualified causal assertion to an observational analysis. |
| welch_clean_wrong_number | False | False | False | False | Replace the protected p-value placeholder with an unsupported numerical literal. |
| welch_wrong_method | False | True | True | True | Misdescribe the Welch analysis as Pearson correlation. |

Per-case JSON retains the original Python results, protected statistics, original template, mutation, rendered reviewer evidence, checks and verdicts. Non-blocking verification flags are retained; no human verification is claimed.

Challenge categories were adapted from teammate commit b7eff1c. This project recomputed all results; source scores were not imported.
