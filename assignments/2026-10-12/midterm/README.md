# Midterm project status package

| File | Purpose |
|---|---|
| `Midterm_Presentation_Final.pptx` | Five editable English slides with a five-minute oral presentation in the speaker notes. |
| `Midterm_Writeup.docx` | Editable two-page English status report. |
| `Midterm_Writeup.pdf` | Two-page PDF exported from the final Word document. |

The slide and paragraph structure were adapted from the teammate's
[midterm package at `b7eff1c`](https://github.com/Junliang-Lyu/statistical-analysis-assistant/tree/b7eff1c4a8035f196ac4bfc73ef3fe88956dadb5/assignments/2026-10-12/midterm).
The content describes our implementation snapshot `9a8fa007c5165b75c2f3fc99a1f3d8fc51683fba`:
Qwen3:8b for planning, semantic diagnosis and drafting; Gemma3:12b for independent
evidence review; parallel LLM/Python diagnostics; user-confirmed data changes; four
statistical methods; bounded revisions and memory within the running graph process.

## Presentation order

1. Problem and implemented scope — 45 seconds.
2. Two models, parallel diagnostics and the human decision point — 70 seconds.
3. Tutoring versus no tutoring: hypotheses, Welch calculation and interpretation — 80 seconds.
4. Follow-up reuse, a changed confidence interval and evaluation evidence — 55 seconds.
5. An observed report-checking failure, repairs and remaining work — 50 seconds.

The synthetic walkthrough uses eighty simulated students, forty per group, from
[`examples/tutoring_scores_clean_synthetic.csv`](../../../examples/tutoring_scores_clean_synthetic.csv).
The estimated tutoring-minus-no-tutoring difference is 6.9175 points, with a 95% interval
of [2.9689, 10.8661] and p = 0.000824. Supplied teaching metadata describe independent
records and nonrandom assignment; the demonstration does not establish a causal effect.

## Evidence and unresolved work

The materials distinguish ninety-three mock-agent tests, current mock notebook executions
and historical real two-model development runs. The real-run records include an initial
run and targeted reruns, rather than one fresh final execution. The failure walkthrough
describes correct Pearson/regression calculations whose reports were withheld by a
placeholder-policy conflict, followed by the documented repair.

Independent human interpretation scoring remains pending. The planned evaluation retains
ordinary, ambiguous and failing cases, missed errors and reviewer false alarms.
Detailed evidence is in [`docs/VERIFICATION.md`](../../../docs/VERIFICATION.md) and the
historical JSON records under [`artifacts/verification/`](../../../artifacts/verification).
