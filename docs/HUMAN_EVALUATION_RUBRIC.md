# Human evaluation of actual system reports

Use the live benchmark's `human_review.csv` and frozen report files. Human labels are
not populated by the runner, Model A, or Model B. This activity evaluates the system;
it does not update model weights. Offline templates and authored interpretation
mutations measure controlled coverage, not natural Model A accuracy.

For each actual report, open its case JSON to inspect the question, declared design,
analysis plan, original diagnostics, approved TEST FIXTURE actions and Python results.
Score the text before reading Model B's verdict. Inspect `report_stage`: a warmup is
not a filtered followup, and a withheld draft was not delivered to the user.

Enter `pass`, `fail`, or `unassessed` in each label column:

| CSV column | Conditions for pass |
|---|---|
| `human_method_label` | Method, variable roles, signed contrast and target parameter answer the specified question; unsupported or unresolved targets are not guessed. |
| `human_numeric_label` | Estimates, sample sizes, test statistic, p-value, degrees of freedom, interval and H0 decision agree with protected results; supported display rounding is allowed. |
| `human_semantic_label` | Text communicates the parameter and uncertainty without causal overreach, proving H0 from non-significance, claiming all relationships absent from a near-zero linear correlation, or assigning frequentist probability to a fixed parameter in the observed CI. Required design, exclusion/missingness and regression diagnostic limitations are faithful. |

Use `unassessed` when the evidence is insufficient or a report was not produced; do
not count it as a pass. Put the exact offending sentence, reason and severity in
`human_notes`, and fill `reviewer` and `review_date`. A missing critical limitation or
unsupported causal claim fails semantic fidelity even if every number is correct.

Examples of failures include calling an observational difference a treatment-caused
improvement; describing a Welch test as Pearson correlation; saying there is no
relationship because Pearson r is near zero for U-shaped data; and claiming a
probability that the fixed population slope lies in this particular frequentist CI.
For heteroscedastic regression, an ordinary OLS p-value alone is insufficient: the
text must retain the warning about conventional standard errors and intervals.

Where no report exists, inspect the case JSON separately to judge whether the pause
or stop was appropriate. A provider/tool failure is not a successful statistical
safety decision. Record these findings separately from report-level labels.

Report the number assessed, passed, failed and unassessed for each criterion, along
with critical error examples and the actual delivered/withheld status. If two people
rate the same reports independently, retain both sets of labels and record how
disagreements were resolved. Do not erase the original ratings or retest only failures
and present that subset as the full benchmark score.
