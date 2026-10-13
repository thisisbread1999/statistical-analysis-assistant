# Verification record

Date: 2026-10-12. This record distinguishes executed checks from pending verification. Mock agents and scripted answers are test inputs, not evidence of real model accuracy or actual user decisions.

## Naming/layout refactor verification

The refactor aligns the package, entry points, example/artifact folders, dependency files
and assignment filenames with the teammate's
[`b7eff1c4a8035f196ac4bfc73ef3fe88956dadb5` layout](https://github.com/Junliang-Lyu/statistical-analysis-assistant/tree/b7eff1c4a8035f196ac4bfc73ef3fe88956dadb5).
See `docs/PROJECT_STRUCTURE.md` for the mapping. Imports and runtime paths were updated;
the statistical and human-confirmation policies remain the same.

The canonical `demo.ipynb` and
`assignments/2026-10-12/langgraph/LangGraph_Submission.ipynb` are newly generated with
explicit mock-mode provenance. The standalone version embeds our source and datasets.
Earlier live outputs remain in `artifacts/verification/`, separate from current mock
outputs. No new real-model evaluation was performed for this naming refactor.

| Current refactor check | Observed result |
|---|---|
| Full renamed-package pytest suite | **93 passed**: 31 in `test_four_methods.py`, 32 in `test_reports.py`, 30 in `test_mvp.py`; no failed or skipped tests. Model responses were mocked. |
| Root CLI mock demonstration | `python demo.py --mode mock` delivered a validated report for the supplied synthetic tutoring data. |
| Project-linked `demo.ipynb` fresh mock execution | All 14 code cells executed successfully in explicit mock mode. The messy-data case remained paused; no user answers were fabricated. |
| Standalone assignment from an empty working directory | All 15 code cells executed successfully in explicit mock mode. Both canonical notebooks have no saved error outputs: eight expected cases delivered, messy data paused for the user, and the injected model failure stopped. |
| Diagram consistency and artifact paths | `artifacts/graph.png` and `assignments/2026-10-12/langgraph/graph.png` are byte-identical. Mermaid source is exported directly from the executed compiled workflow. |
| Preserved v1 assets, source CSVs and historical JSONs | Eleven historical files retain their Git contents after normalizing text CRLF: the v1 notebook/PNG, R scripts, two v1 check files and all five source CSVs. The binary PNG is exact. Five `examples/` CSVs are byte-identical to the original physical CSV files. Three historical JSONs and the archived pre-layout notebook were moved/copied without rewriting. Dependency pins are unchanged. |

The machine-readable layout audit is preserved at
[`artifacts/verification/layout_alignment.json`](../artifacts/verification/layout_alignment.json).
An independent review found a cached-module issue in the standalone bootstrap. After its
repair, a targeted same-process check passed with the original package already loaded and
the standalone setup executed twice. The current standalone bootstrap includes this repair.
These checks concern portability and workflow mechanics.

Current generated request/result logs and notebook temporary files use ignored
`artifacts/runtime/`. Use `python -m pytest -q --basetemp=artifacts/pytest` for an ignored
project-local test temporary directory whose parent exists in a fresh checkout. The first
refactor pytest attempt had an absent nested basetemp parent; creating the runtime directory
resolved it before the complete successful run above. Existing ignored `outputs/` is
retained for v1 history. Mock/test passes and agreement with SciPy do not measure semantic accuracy. Cloud-provider calls,
hosted CI and independent human interpretation scoring remain unverified by this refactor.

## Historical checks before the naming/layout refactor

| Check | Observed result | Scope |
|---|---|---|
| Report and local-model identity regressions | `tests/test_reports.py`: 32 passed | Required result fields, invented numbers, direct field swaps, direction/decision, missing/duplicate limitations, p-value threshold rounding, local model aliases and weight digests. HTTP responses were mocked; no model inference. |
| Independent numeric comparison | Four supported methods matched selected direct SciPy references | Welch/Pearson at 99% confidence: maximum checked difference zero; centered OLS versus `linregress`: about `1.6e-15`; 2-by-2 chi-square/p/V: difference zero with `correction=False`. Synthetic temporary CSVs, no model calls. |
| Historical v1 compatibility | 18 of 18 checks passed | Current v1 notebook, R script, synthetic data and original test runner copied into an isolated directory. Rule-based mock agents; real R statistical calls. |
| Teammate reference identity | Same commit and matching core file hashes | Both reference checkouts at `b7eff1c4a8035f196ac4bfc73ef3fe88956dadb5`; statistical, agent, workflow and four-method test files matched. |

### Commands used

The report regression run used the project virtual environment:

```powershell
& "$env:USERPROFILE\.venvs\langgraph-viz\Scripts\python.exe" -B -m pytest -q tests/test_reports.py -p no:cacheprovider
```

For v1, R initially could not locate `jsonlite`. Its existing installation was found under the user's R library. The successful isolated check used only process-local settings:

```powershell
$env:R_LIBS_USER = "$env:USERPROFILE\AppData\Local\R\win-library\4.4"
$env:RSCRIPT_PATH = "C:\Program Files\R\R-4.4.1\bin\Rscript.exe"
```

R 4.4.1 loaded the installed `jsonlite` 2.0.0. The package's build-version warning did not prevent the 18 checks from passing. No package was installed and no persistent user environment setting was changed. The v1 source notebook, original CSVs and R script were not rewritten by this verification run.

The local isolated-run log is `C:/Users/62703/Documents/Codex/2026-09-20/https-chatgpt-com-share-6ab06193-d980/work/v1-compat-audit/v1-checks.log`. This local audit path is not required to run the submitted v2 project. V2 does not require R or this library setting.

## Historical Python v2 integration results

The table separates completed integration checks from unperformed cloud/hosted/human checks. An implementation or test file existing on disk does not itself establish a passing result.

| Pre-layout integration check | Status |
|---|---|
| Full v2 pytest suite | **93 passed** (31 statistics, 32 report/model-identity, 30 workflow), no failed or skipped tests; `python -X utf8 -m pytest -q --basetemp=outputs/pytest --tb=short`. |
| Archived pre-layout v2 notebook | Complete 14-code-cell real run plus selective real reruns of two repaired cases; provenance retained in `artifacts/verification/python_v2_pre_layout.ipynb`. A pre-layout mock run also passed expected routes. Messy data intentionally stays paused. |
| PNG exported from the same compiled graph used for execution | Generated by the notebook with `graph.get_graph().draw_mermaid_png()`; inspected at 1454 by 2213 pixels. All 17 nodes and handoffs are present. LangGraph coalesces coincident conditional edges; notebook text enumerates every condition. |
| Two real local models in the pre-layout v2 workflow | A: `ollama:qwen3:8b`; B: `ollama:gemma3:12b`. Four methods, two follow-ups and both injected report faults delivered after the runs described below. The simulated model failure stopped. |
| Cloud API providers | Not verified by these checks. |
| Hosted CI execution | Not verified by these checks; local tests are not a hosted CI result. |
| Independent human interpretation evaluation | Not performed by these automated checks. |

## What these results do and do not establish

Numeric reference checks establish agreement for their tested data and conventions. They do not validate causal claims, missingness assumptions, the population model or all numerical edge cases. Control-flow tests establish that prescribed branches and stopping boundaries behave as tested. They do not measure whether real Model A will select the right method or whether Model B will catch every misleading interpretation.

The program protects numeric placeholders and catches several direct field/label mismatches, but it is not a complete natural-language verifier. Model B receives original results and design evidence for semantic review. Two-model agreement is still fallible. A later human evaluation should retain both correct and incorrect reports, borderline data situations, missed errors and false alarms rather than reporting only successful examples.

No push, pull request, public deployment or teammate-repository modification was part of the checks above.

### Final preservation check

The original v1 notebook and PNG match the pre-change backup byte for byte. All four
historical CSV MD5 hashes match the pre-migration hashes. The unfinished R extension was
preserved in `legacy/stats_tools_R_v2_reference.R`; `r/stats_tools.R` was restored from the
frozen v1 tag. The original 18-check runner was then run again against the restored tool
and passed **18/18** (`outputs/v1_checks_final.log`).

The first integrated pytest attempt could not write the sandbox's default temporary
directory. Running with the project-local `--basetemp=outputs/pytest` resolved this environment
issue; the final successful result above is the complete suite. No packages were installed
or global environment settings changed during this migration.

## Real-model outcomes and repair history

The initial complete real run executed all fourteen code cells without a notebook exception.
Welch, chi-square, both follow-ups and both injected report faults delivered. Messy data
paused without fabricated answers. The injected model failure stopped as intended. Pearson
and regression first stopped because their hypotheses contained a literal zero while the
placeholder policy rejected all model-written digits. This was a prompt/checker conflict,
not a failure of their SciPy calculations.

Adding a protected null value resolved that conflict. A first targeted rerun exposed
additional formatting issues: decision/direction placeholders lacked protected renderings,
and a null-hypothesis slope was confused with an estimated slope by a label checker. These
were repaired and regression-tested without weakening rejection of estimated-value swaps.
The final targeted run delivered Pearson after one revision and regression on its first
draft. No retry limit was bypassed within a request; development reruns are logged separately.

| Case | Latest observed real outcome | Report revisions |
|---|---|---|
| welch | delivered | 1 |
| pearson | delivered | 1 |
| chi_square | delivered | 0 |
| regression | delivered | 0 |
| ci99 | delivered | 1 |
| re_explain | delivered | 1 |
| messy | paused_for_user | 0 |
| causal_fault | delivered | 1 |
| numeric_fault | delivered | 1 |
| model_failure | stopped | 0 |

Evidence: `artifacts/verification/initial_full_real.json`,
`artifacts/verification/first_targeted_real.json` and
`artifacts/verification/final_targeted_real.json`. These historical JSONs were moved byte
for byte. The archived `artifacts/verification/python_v2_pre_layout.ipynb` retains the latest
observed outputs for the two rerun cases and labels its aggregate summary. Other real
outputs come from the complete initial run. Its saved results are not one fresh execution.
The canonical `demo.ipynb` and standalone assignment notebook now contain fresh mock outputs.

Minor reviewer false alarms about correctly rounded numbers occurred. The prompt now
explicitly distinguishes protected displayed values from raw floating-point precision.
These development-observed examples are not a blinded/held-out accuracy evaluation and
must not be reported as a model success rate.

Additional fail-closed source/version and empty-review-verdict guards were validated in
pytest. The notebook runner now uses project-local temporary files and explicitly shuts
down its kernel; final mock and targeted real runs exited successfully.

## Local browser UI verification (2026-10-12)

The new `ui_server.py` and `ui/` adapt the teammate's browser layout to this project's
existing seventeen-node workflow. No statistical package, model prompt or notebook was
changed for this interface. The server binds to `127.0.0.1` and queues jobs in one worker;
mock/real mode is selected explicitly, with no fallback after a real-model failure.

`python -X utf8 -m pytest -q --basetemp=artifacts/pytest` passed **125 tests**: the previous
93 plus 32 browser-adapter/HTTP tests. New coverage includes all four methods, uploads and
metadata confirmation, missing-data interruption and explicit resume decisions, original
source preservation, changed-confidence/re-explanation routing, unsupported paired design,
model-start failure without mock substitution, and local HTTP request/JSON validation.

Manual browser checks exercised a mock Welch report, a 99% CI follow-up, missing decisions
being rejected before inference, and the messy-data pause/resume flow. The entered decisions
were labelled **UI TEST ONLY**, not human research verification. The resumed teaching case
delivered on data version v2 with 78 included records and a missingness limitation. An actual
file-chooser upload of the clean synthetic CSV also delivered after entering and confirming
its study metadata. Input edits now identify the displayed report as belonging to the
previous session, and completion updates the sidebar status after a resume.

One browser-initiated real Welch run delivered with Model A `ollama:qwen3:8b` and Model B
`ollama:gemma3:12b`. Five real calls completed, the program check and independent review
passed, and recorded workflow-node durations totalled approximately 46.6 seconds on this
machine. The protected estimate was 6.9175, p = 0.000824240443, with the 95% interval
[2.9688820792, 10.8661179208]. The UI rounded these values for presentation. This was a
single integration smoke run; it is not an accuracy score, human evaluation or latency
guarantee. Evidence is preserved in `artifacts/verification/ui_smoke.json`.

The local service was left running for user trials. Uploads and generated runtime files
remain ignored by Git. Neither a hosted deployment nor a teammate-repository modification
was part of this UI work. Existing assignment notebooks and midterm artifacts were retained.

### Optional decision notes (2026-10-12)

At the user's request, source/reason notes are now optional for verification, exclusion
and correction. A permitted action remains required for every current finding, and a
correction still needs a valid replacement. Omitted, blank or null notes are stored as an
empty string; the UI displays "No note provided" rather than generating a rationale.
The earlier mandatory-note behavior and live smoke evidence above are historical.

The complete suite passed **133 tests**, including note-free pause/resume paths, retained
nonempty notes and rejection of invalid corrections, missing actions and incomplete
answers. A sandboxed HTTP attempt had a local connection aborted; the complete rerun with
local transport access passed without failures. Both canonical notebooks were rebuilt
from the updated source and executed in explicit mock mode: 14 project code cells and
15 standalone code cells completed. The graph and frozen v1 artifacts were unchanged.

The browser was also used to select two exclusions, two corrections and three
verifications on the messy synthetic fixture, leaving all notes empty. Submission
delivered on v2 with 78 included records, the missingness limitation and seven empty
audit notes. This was a synthetic UI smoke test, not human verification of research
records or a real-model evaluation. Evidence is recorded in
`artifacts/verification/ui_optional_notes_smoke.json`. The local service was updated and
left running with the new rule.

### Evaluation port and OLS diagnostics (2026-10-12)

The teammate's frozen 31-case CSV/JSON inputs at `b7eff1c` are retained unchanged,
with a separately declared adapter for our confirmation, independence, minimum-size
and unsupported date-filter policies. Source hashes and Git attributes protect the
fixture bytes. All numerical results and scores are regenerated by this project.

The final software run passed **192 tests** with no failures or skips. Regression
references independently check hat matrices, leave-one-out influence and the auxiliary
least-squares calculation for the Koenker studentized Breusch–Pagan LM. Workflow tests
check that warning limitations reach drafting, review and delivery, and that unavailable
diagnostics are not represented as a pass. Both new browser examples were tested through
the asynchronous UI adapter. See `artifacts/verification/evaluation_regression_pytest.txt`.

Both canonical notebooks were rebuilt and executed in mock mode: all 14 project code
cells and 15 standalone code cells completed. The graph still has 17 nodes. No model
weights, dependency versions or frozen v1 artifacts were changed. Evaluated source
hashes and local model weight digests are in
`artifacts/verification/evaluation_regression_manifest.json`.

| Final evidence | Result and scope |
|---|---|
| `artifacts/benchmark_v2/20261012-offline-blinded/` | 31/31 workflow mechanics; 19/19 independently checked computed results and mock reports. Prespecified fixture plans mean this is not model method-selection accuracy. Original pauses are retained; continued answers are labelled TEST FIXTURE. |
| `artifacts/benchmark_v2/20261012-supplemental-offline/` | Five separate confidence-level, re-explanation, missing-exclusion and replacement-data followups passed. This denominator is separate from the source 31. |
| `artifacts/interpretation_checks/20261012-offline-blinded/` | Four valid templates accepted; combined program/Mock B detected eight of twelve authored mutations. Mechanics only. |
| `artifacts/interpretation_checks/20261012-live-blinded/` | Actual `gemma3:12b` reviewer plus program check accepted four of four valid templates and detected ten of twelve authored mutations. No reviewer errors or valid-template false alarms in this run. Model A was not called. |
| `artifacts/benchmark_v2/20261012-live-blinded/` | Actual `qwen3:8b` / `gemma3:12b` full-workflow results are recorded per case with the completed/requested count. Use that run's REPORT.md for the final aggregate. |

The live interpretation reviewer missed the Welch-as-correlation mutation and the
frequentist interval probability mutation. Those drafts, verdicts and detector misses
remain recorded. The score measures controlled detector coverage; it is not a human
semantic accuracy score or the natural error rate of Model A's generated reports.

Initial development runs are retained with `PROVENANCE.md` status notes. The first
workflow run hit Windows path-length failures; the runner now uses short, ignored audit
paths. An early reviewer run exposed authored challenge names through report versions,
and an early workflow run exposed fixture names through tool data paths. Later runs use
neutral report versions and runtime file paths. Labels, mutations and expected answers
remain outside model input. Guarded provider/tool errors cannot receive a mechanical
pass simply because an expected-stop case stopped. These harness fixes did not alter
production model prompts or the originally recorded results.

The browser delivered the heteroscedastic regression example in mock mode after nine
explicitly labelled synthetic verification answers, with all 60 records retained. It
displayed maximum Cook's distance about 0.56185, maximum leverage about 0.065027 and
Koenker LM about 10.938 (p about 0.00094201), plus influential-record and unequal-variance
warnings. Ordinary OLS inference was unchanged and its limitation was included in the
report. This is a UI smoke demonstration, not human verification of real observations.
See `artifacts/verification/ui_regression_diagnostics.jpg`.

Human ratings remain unperformed. Frozen report texts, hashes and blank CSV rating
columns are available, with instructions in `docs/HUMAN_EVALUATION_RUBRIC.md`.
