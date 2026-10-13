# Midterm project status package

| File | Purpose |
|---|---|
| `Midterm_Presentation_Final.pptx` | Five editable English slides with a five-minute oral presentation in the speaker notes. |
| `Midterm_Writeup.docx` | Editable two-page English status report. |
| `Midterm_Writeup.pdf` | Two-page PDF exported from the final Word document. |

The slide and paragraph structure were adapted from the teammate's
[midterm package at `b7eff1c`](https://github.com/Junliang-Lyu/statistical-analysis-assistant/tree/b7eff1c4a8035f196ac4bfc73ef3fe88956dadb5/assignments/2026-10-12/midterm).
The updated content describes our implementation snapshot `4ebe82c`:
Qwen3:8b for planning, semantic diagnosis and drafting; Gemma3:12b for independent
evidence review; parallel LLM/Python diagnostics; user-confirmed data changes; four
statistical methods; bounded revisions and memory within the running graph process.

## Presentation order

1. Problem and implemented scope — 45 seconds.
2. Two models, parallel diagnostics and the human decision point — 70 seconds.
3. Tutoring versus no tutoring: hypotheses, Welch calculation and interpretation — 80 seconds.
4. Follow-up reuse, a changed confidence interval and evaluation evidence — 55 seconds.
5. Future work: human evaluation, broader methods and real-world datasets — 50 seconds.

The synthetic walkthrough uses eighty simulated students, forty per group, from
[`examples/tutoring_scores_clean_synthetic.csv`](../../../examples/tutoring_scores_clean_synthetic.csv).
The estimated tutoring-minus-no-tutoring difference is 6.9175 points, with a 95% interval
of [2.9689, 10.8661] and p = 0.000824. Supplied teaching metadata describe independent
records and nonrandom assignment; the demonstration does not establish a causal effect.

## Evidence and unresolved work

The updated materials distinguish 192 software tests, the 31-case live workflow
evaluation (27/31 mechanical checks and 19/19 assessed numerical references), and the
separate controlled interpretation evaluation (four valid templates accepted and ten
of twelve authored mutations detected). These are different denominators and do not
establish independent human semantic accuracy. Historical development failures and
repairs remain explicitly identified as earlier observations.

Independent human interpretation scoring remains pending. The planned evaluation retains
ordinary, ambiguous and failing cases, missed errors and reviewer false alarms.
Detailed evidence is in [`docs/VERIFICATION.md`](../../../docs/VERIFICATION.md) and the
historical JSON records under [`artifacts/verification/`](../../../artifacts/verification).

## Future work

- **Human evaluation:** use the prepared CSV and rubric to independently score method
  choice, numerical fidelity and interpretation. Data correction/exclusion confirmation
  already exists; selective analyst review of unresolved issues is a possible addition.
- **Broader statistical methods:** add paired comparisons and multiple regression when
  the question and design call for them, with appropriate assumptions and diagnostics.
- **Real-world datasets:** test curated public datasets, including suitable Kaggle
  datasets, after checking provenance, variable definitions and research design. Compare
  with analyst reference analyses while retaining reproducible synthetic benchmarks.

Human scores and real-world dataset results have not yet been collected. The revised
Word/PDF retain two pages and uniform body typography; the PPTX retains five editable
slides and five-minute speaker notes. Runtime code and model weights are unchanged.
