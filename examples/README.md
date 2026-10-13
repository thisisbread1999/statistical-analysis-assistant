# Synthetic examples

This folder follows the teammate's `examples/` convention. All five CSVs are this
project's own synthetic teaching data, copied byte for byte from the preserved `data/`
files during the layout refactor. No real student records are included. Original filenames
remain descriptive so datasets can be identified across the v1 and Python notebooks.

| File | Current use | Provenance |
|---|---|---|
| `students_synthetic.csv` | Four-method Python examples: Welch, Pearson, chi-square and simple regression. | Python generator, single fixed seed `20261012`; 120 simulated students. |
| `tutoring_scores_clean_synthetic.csv` | Supplied default CLI tutoring example and clean two-group analysis. | Original v1 R generator; 40 students per group. |
| `tutoring_scores_no_difference_synthetic.csv` | Two-group example with equal simulated population means. | Original v1 R generator; 40 students per group. |
| `tutoring_scores_unequal_variance_synthetic.csv` | Two-group example illustrating the Welch calculation. | Original v1 R generator; 30 and 50 students with different simulated variances. |
| `tutoring_scores_messy_synthetic.csv` | Explicit user clarification, correction and verification example. | Original v1 R generator with labelled missing scores, invalid label, impossible value and unusual observation. |

The four tutoring CSVs contain `student_id`, `tutoring` and `score`. The Python dataset
adds `study_hours` and `passed`. Its score recipe is `45 + 1.7 * hours + 5 * tutoring +
uniform noise`, with hours uniform from 2 to 18 and noise from -12 to 12. A rounded score
of at least 70 defines `passed=yes`. These simulation equations establish no claim about
real tutoring or causation.

```powershell
python demo.py --mode mock
python scripts/make_synthetic_data.py
```

The Python generator targets `examples/students_synthetic.csv`, uses its one fixed seed
and does not screen samples, remove observations or inspect p-values. The older R
generator screened consecutive seeds to avoid boxplot flags in clean examples; it did
not screen p-values. Details and the planted messy-data issues are recorded in
[data/README.md](../data/README.md).

Mock agents are rule-based demonstrations and do not evaluate arbitrary natural-language
questions. For a deliberate real-model run, configure two distinct models and use
`demo.py --mode real --csv <path> --question "<question>" --design-json <confirmed-design.json>`.
The design argument must name a JSON file containing confirmed design and variable meanings;
independence is not inferred from a CSV. Use `--interactive` when you intend to answer
clarification requests. Neither unusual observations nor missing values are automatically
deleted. Source CSVs are preserved and confirmed changes are logged in ignored
`artifacts/runtime/`.
