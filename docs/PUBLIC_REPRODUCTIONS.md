# Reproducing three public teaching examples

Sleep and Berkeley use sourced historical observations. Anscombe's quartet uses
published pedagogically constructed values, not empirical observations. These
cases complement the synthetic workflow tests and let classmates inspect every input. They reproduce selected
patterns and modern numerical analyses; they do not reproduce every result of
the original papers. A correct statistical calculation and a delivered agent
workflow are recorded separately.

| Case | Classroom question | Modern numerical target |
|---|---|---|
| Student's sleep data | What changes when the same patients are correctly matched? | Drug two minus drug one: mean difference 1.58 hours, paired t(9) = 4.06212768, two-sided p = 0.0028328902; 95% CI 0.70011424 to 2.45988576 |
| Berkeley admissions | Can pooled rates conceal the department pattern? | Six departments, n = 4,526: uncorrected Pearson chi-square(1) = 92.20528041, p = 7.813600389e-22 |
| Anscombe's quartet | Why inspect the plot when regression summaries look alike? | First constructed set only: n = 11, slope = 0.50009091, intercept = 3.00009091, R² = 0.66654246, p = 0.0021696289; 95% slope CI 0.23337014 to 0.76681168 |

## Inputs, provenance, and rights

`examples/public_reproductions/manifest.json` records source URLs, access time,
SHA-256 hashes, the precise contrast, expected results, and numerical tolerances.
The source snapshots are in `sources/`; the derivation script reads their values
without executing R. Existing snapshots cannot be silently replaced.

- [Official R sleep source](https://svn.r-project.org/R/trunk/src/library/datasets/data/sleep.R)
  and [dataset documentation](https://stat.ethz.ch/R-manual/R-devel/library/datasets/html/sleep.html).
- [Official R Berkeley source](https://svn.r-project.org/R/trunk/src/library/datasets/data/UCBAdmissions.R)
  and [dataset documentation](https://stat.ethz.ch/R-manual/R-devel/library/datasets/html/UCBAdmissions.html).
- [Official R Anscombe source](https://svn.r-project.org/R/trunk/src/library/datasets/data/anscombe.R)
  and [dataset documentation](https://stat.ethz.ch/R-manual/R-devel/library/datasets/html/anscombe.html).

The current collection is `public-reproductions-v2`. It adds Anscombe while
retaining every earlier data file and run. The exact v1 manifest is preserved at
`manifests/public-reproductions-v1.json`, so historical v1 run hashes remain
verifiable. New runs capture their manifest bytes and hash at startup.

R's datasets package says its license is “Part of R.” R is distributed under
`GPL-2 | GPL-3`; the downloaded GPL version two license, copyright notices, and
package description are included beside the snapshots. A separate CC0 license
is not asserted. Article rights are separate from the R distribution's license.
See the [R Foundation's license statement](https://www.r-project.org/Licenses/).

To fetch and derive these snapshots again, run:

```powershell
python scripts/fetch_public_reproductions.py
```

Existing files are checked and reused. If upstream source bytes change, preserve
a new version using `--destination PATH`; review the new data before accepting
different results. No original records are corrected, excluded, or imputed.

## Student's sleep data

`student_sleep.csv` has one row for each of ten patients and two columns of
additional sleep relative to control. The R data's twenty long-format rows were
matched using their repeated patient IDs. The analysis asks specifically for
**drug_2 minus drug_1**. These labels do not establish treatment order.

The original article's Illustration I reports a mean difference of 1.58 hours.
The modern two-sided test and confidence interval above are fresh calculations,
not a transcription of Student's historical probability terminology. The same
values analysed as independent groups give Welch p approximately 0.07939,
illustrating how the study structure matters. This is not an alternative valid
analysis of the matched observations. [Student (1908), original article, MIT-hosted copy](https://ocw.mit.edu/courses/esd-86-models-data-and-inference-for-socio-technical-systems-spring-2007/1dabbcb2c2fa46e67fb3655a35ec11fc_gosset_1908.pdf).

The metadata explicitly identifies the patient pairs and treats different
patients as independent units for this teaching reanalysis. That is a modelling
assumption, not verified random sampling. Randomization is `null`: the dataset
documentation does not establish random assignment or the treatment sequence.
Pairing alone does not support a causal treatment claim or current medical advice.

The workflow can pause to verify an unusual value. The reproduction script leaves
such a pause unresolved. The independent reference calculation and read-only
statistical-tool result can still be inspected separately; neither pretends that
a human verified a flagged record.

## Berkeley admissions

`berkeley_counts.csv` preserves all **twenty-four frequency cells** in the official R snapshot:
admission by historical sex category by department. It represents only the six
largest departments in 1973. The whole-university paper included 12,763
applications and reached an adjusted result that is not recoverable from this
subset alone. [Bickel, Hammel and O'Connell (1975), article abstract](https://pubmed.ncbi.nlm.nih.gov/17835295/).

`berkeley_frequency_expanded.csv` deterministically repeats each frequency cell
to make a 4,526-row input for the current categorical-tool interface. Its
`derived_record_id` is a generated label. These rows are **not original
individual-level application records**; they contain no information beyond the
count table. Regrouping them must recover every source frequency exactly.

The pooled rates are 1,198/2,691 for men and 557/1,835 for women. The descriptive
department display shows higher female admission rates in four departments and
lower rates in two. It therefore does not claim that every department reverses
the aggregate pattern. The chi-square target uses `correction=False`; applying
Yates correction produces a different statistic. Tests treat counted
applications as independent observational units, which grouped counts cannot
independently verify. Neither the association nor its p-value establishes
discrimination or adjusts for applicant qualifications.

A common-odds-ratio Mantel–Haenszel result is intentionally not the headline
analysis: R's own example flags substantial heterogeneity between these
departments. [Official R Mantel–Haenszel documentation](https://stat.ethz.ch/R-manual/R-devel/library/stats/html/mantelhaen.test.html).

## Anscombe's quartet

`anscombe_quartet.csv` retains all four x/y datasets as eleven wide rows, with an
explicitly illustrative row index. These are **published pedagogically
constructed values**, unlike the historical observations in Sleep and Berkeley.
The row index is not a subject identifier. The R documentation credits Tufte
(1990), pages 13–14, as its source and cites Anscombe's 1973 article.
[Official R dataset documentation](https://stat.ethz.ch/R-manual/R-devel/library/datasets/html/anscombe.html).

The four-panel plot draws each dataset with its own fitted line and the same
axis limits. Slopes are approximately one half and R² approximately two thirds,
yet the scatter, curved pattern, unusual y value, and distant x value differ
markedly. The displayed coefficients retain enough digits to show that the
unrounded summaries are **nearly identical**, rather than exactly equal.
This reproduces the graphical teaching point of
[Anscombe (1973), Graphs in Statistical Analysis](https://doi.org/10.1080/00031305.1973.10478966);
an [original article copy](https://personal.us.es/vararey/anscombe1973.pdf) is also available.

The workflow target is one explicit regression: **y1 on x1, with an intercept**.
It requires the same plan approval as the other cases. Comparing all four plots
and descriptive fits is deterministic visualization, not an automatic batch of
four agent analyses. The first dataset's ordinary least-squares slope, interval,
and p-value are reproducible model calculations on constructed numbers. They do
not establish an empirical population relationship or validate the other three
linear models. No data point is removed or altered to make a line fit.

## Running and reading the evidence

```powershell
# Offline agents; stops at the explicit analysis-plan confirmation.
python reproduce_public.py --mode mock --output artifacts/public_reproductions/my_review

# Explicit benchmark setup: approve only the exact predefined method and roles.
# It never supplies data verification, exclusions, or corrections.
python reproduce_public.py --mode mock --noninteractive-benchmark --output artifacts/public_reproductions/my_benchmark

# When separately authorized and configured, run the two real models.
python reproduce_public.py --mode real --noninteractive-benchmark --output artifacts/public_reproductions/my_real_run

python -m pytest tests/test_public_reproductions.py -q
```

`--output` names a new directory and refuses to replace existing evidence. With
no output argument a timestamp and random suffix create a fresh directory. Use
`--case student_sleep`, `--case berkeley_admissions`, or `--case anscombe_quartet`
to select one case. `--case all` runs the three predefined targets separately;
it does not run all four Anscombe regressions.

Each case JSON contains source version and hashes, expected and calculated
numbers, tolerances and comparison status, numerical-tool status, workflow
mode/status, trace, reviewer checks, and pending interrupts. The top-level
`summary.json` keeps these outcomes separate. An explicit benchmark plan approval
is logged under `benchmark_predefined_plan` with `human_approval: false`; it is
not a human approval record. A proposed plan with different method or variable
roles is left paused. Data verification and scope selection are never answered
automatically.

Mock runs execute the real graph and real numerical tools with deterministic
agent stand-ins. They cannot substantiate real-model planning or review quality.
A paused graph has not delivered a report, even when its separate numerical
reference matches. These fixtures add traceable examples, not evidence of
general scientific validity or complete original-paper reproduction.

Three standalone SVG classroom plots are generated in each output directory:
`student_sleep.svg` joins the patient pairs; `berkeley_admissions.svg` compares
pooled and department-specific rates; `anscombe_quartet.svg` shows all four
constructed datasets and separate fit lines. They are drawn directly from the data and
need no extra plotting package. PNG versions are also generated when matplotlib
is already available in the active Python environment; the script installs nothing.

## Saved offline evidence

The current successful run is
[`mock_20261101_v2/summary.json`](../examples/public_reproductions/evidence/mock_20261101_v2/summary.json).
Both cases delivered through the actual graph, matched their independent
numerical references, and passed program checks and the mock review. There were
no data verification answers, exclusions, corrections, or imputations. Plan
approval alone used the explicit `benchmark_predefined_plan` setup policy.
This is offline workflow evidence, with no claim about real-model quality.

The earlier `mock_20261101_v1` run remains preserved: its proposed sleep contrast
was reversed, so the benchmark refused to approve that plan and left it paused.
The subsequent parser correction is reflected in the new v2 run. The separate
`mock_plan_confirmation_20261101_v1` run records the default behavior without the
benchmark flag: Berkeley remains paused at plan confirmation.

After the fixture collection advanced to `public-reproductions-v2`, the
one-target Anscombe mock run also delivered and matched its numerical references:
[`mock_anscombe_20261101_v1/summary.json`](../examples/public_reproductions/evidence/mock_anscombe_20261101_v1/summary.json).
Its output includes the four descriptive summaries separately from the one
workflow result. There were no automatic data decisions and no real-model calls.

Ready-to-use classroom figures are available as
[Student sleep PNG](../examples/public_reproductions/classroom_plots/student_sleep.png)
and [Berkeley admissions PNG](../examples/public_reproductions/classroom_plots/berkeley_admissions.png),
plus [Anscombe quartet PNG](../examples/public_reproductions/classroom_plots/anscombe_quartet.png),
alongside standalone SVG versions.

## Real-model verification, 2026-11-01

The [final three-case run](../examples/public_reproductions/evidence/real_20261101_final/summary.json) used Qwen3 8B and Gemma3 12B. All three predefined targets delivered, matched independent numerical references, and passed the program and final reviewer gates. Berkeley and Anscombe required one report revision. No records were modified or excluded. The sleep review retained a minor false-positive numeric-mismatch comment, so successful delivery is not proof that every reviewer statement was correct. Plan approval was supplied by the explicit predefined benchmark policy, not a human. The 262 software tests are separate from this small live demonstration.

[Recorded native tool calls](../examples/public_reproductions/evidence/real_20261101_final/native_tools/index.json) preserve actual provider call IDs and byte-exact recorded inputs/results. Earlier failed and paused attempts remain available beside the final evidence. Independent human scoring has not been performed.
