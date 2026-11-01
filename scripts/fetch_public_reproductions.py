"""Fetch official R data snapshots and build explicitly labelled teaching derivatives.

No R code is executed. Existing snapshots are immutable: use --destination for a
new version if upstream bytes change. R source notices and licence travel with it.
"""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import re
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DESTINATION = ROOT / "examples" / "public_reproductions"
FIXTURE_VERSION = "public-reproductions-v2"
BASE_URL = "https://svn.r-project.org/R/trunk/"
SOURCES = {
    "sleep.R": "src/library/datasets/data/sleep.R",
    "UCBAdmissions.R": "src/library/datasets/data/UCBAdmissions.R",
    "anscombe.R": "src/library/datasets/data/anscombe.R",
    "LICENSE-R-GPL-2.txt": "COPYING",
    "COPYRIGHTS-R.txt": "doc/COPYRIGHTS",
    "DESCRIPTION-R-datasets.in": "src/library/datasets/DESCRIPTION.in",
}


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def write_immutable(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_bytes() != data:
            raise ValueError(f"Refusing to replace an existing snapshot: {path}. Use a new --destination.")
        return
    path.write_bytes(data)


def json_bytes(value) -> bytes:
    return (json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8")


def csv_bytes(columns, rows) -> bytes:
    stream = io.StringIO(newline="")
    writer = csv.writer(stream, lineterminator="\n")
    writer.writerow(columns)
    writer.writerows(rows)
    return stream.getvalue().encode("utf-8")


def parse_sleep(source: str) -> list[list]:
    match = re.search(r"extra\s*=\s*c\((.*?)\)\s*,\s*group", source, re.S)
    if not match:
        raise ValueError("The official sleep.R structure changed; review before deriving data.")
    values = [float(v.strip()) for v in match.group(1).split(",")]
    if len(values) != 20 or "rep.int(1:10,2)" not in re.sub(r"\s", "", source):
        raise ValueError("Expected twenty sleep observations on ten repeated patient IDs.")
    return [[str(i + 1), values[i], values[i + 10]] for i in range(10)]


def parse_berkeley(source: str) -> list[list]:
    match = re.search(r"array\(c\((.*?)\)\s*,\s*dim", source, re.S)
    if not match:
        raise ValueError("The official UCBAdmissions.R structure changed; review before deriving data.")
    values = [int(v.strip()) for v in match.group(1).split(",")]
    if len(values) != 24 or sum(values) != 4526:
        raise ValueError("Expected the twenty-four cells of the six-department table (n = 4526).")
    # R fills the first array dimension fastest: admission, sex, department.
    return [[dept, sex, admission, values[4 * k + 2 * j + i]]
            for k, dept in enumerate("ABCDEF")
            for j, sex in enumerate(("Male", "Female"))
            for i, admission in enumerate(("Admitted", "Rejected"))]


def parse_anscombe(source: str) -> list[list]:
    """Read the eight published vectors without evaluating R code."""
    vectors = {name: [float(v.strip()) for v in body.split(",")]
               for name, body in re.findall(r"([xy][1-4])\s*=\s*c\((.*?)\)", source, re.S)}
    columns = [f"{axis}{i}" for axis in ("x", "y") for i in range(1, 5)]
    if set(vectors) != set(columns) or any(len(vectors[c]) != 11 for c in columns):
        raise ValueError("Expected eight eleven-value Anscombe vectors; review changed source.")
    return [[f"illustrative_{row + 1:02d}", *[vectors[c][row] for c in columns]] for row in range(11)]


def definitions() -> list[dict]:
    return [
        {
            "id": "student_sleep", "title": "Student's sleep data: preserve the patient pairs",
            "data_file": "student_sleep.csv", "design_file": "student_sleep.design.json",
            "source_file": "sources/sleep.R", "source_name": "R datasets::sleep",
            "source_url": BASE_URL + SOURCES["sleep.R"],
            "documentation_url": "https://stat.ethz.ch/R-manual/R-devel/library/datasets/html/sleep.html",
            "paper_doi": "https://doi.org/10.2307/2331554",
            "paper_url": "https://ocw.mit.edu/courses/esd-86-models-data-and-inference-for-socio-technical-systems-spring-2007/1dabbcb2c2fa46e67fb3655a35ec11fc_gosset_1908.pdf",
            "citation": "Student (1908). The probable error of a mean. Biometrika 6(1), 1–25; data from Cushny and Peebles (1905).",
            "question": "Use a two-sided paired t-test to compare the mean within-patient difference drug_2 minus drug_1, in additional hours of sleep.",
            "method": "paired_t_test", "roles": {"x": "drug_1", "y": "drug_2"},
            "unit": "One wide row per historical patient, matched using the original R ID.",
            "derivation": "Reshape the two ten-value drug vectors by their repeated patient IDs; retain every value. Drug labels are the R labels, with no reconstructed treatment order.",
            "claim_supported": "Modern two-sided reanalysis of the paired historical values; reproduce the published mean difference of 1.58 hours.",
            "claim_not_supported": "A modern randomized clinical trial, current treatment guidance, or an exact reproduction of Student's historical probability wording.",
            "reference": {"n": 10, "n_pairs": 10, "mean_difference": 1.58, "t_statistic": 4.062127683382037,
                          "df": 9, "p_value": 0.00283289019738427,
                          "ci_lower": 0.7001142367012769, "ci_upper": 2.459885763298723},
        },
        {
            "id": "berkeley_admissions", "title": "Berkeley admissions: what pooling conceals",
            "data_file": "berkeley_frequency_expanded.csv", "count_file": "berkeley_counts.csv",
            "design_file": "berkeley_admissions.design.json", "source_file": "sources/UCBAdmissions.R",
            "source_name": "R datasets::UCBAdmissions", "source_url": BASE_URL + SOURCES["UCBAdmissions.R"],
            "documentation_url": "https://stat.ethz.ch/R-manual/R-devel/library/datasets/html/UCBAdmissions.html",
            "paper_doi": "https://doi.org/10.1126/science.187.4175.398",
            "paper_url": "https://pubmed.ncbi.nlm.nih.gov/17835295/",
            "citation": "Bickel PJ, Hammel EA, O'Connell JW (1975). Sex bias in graduate admissions: data from Berkeley. Science 187(4175), 398–404.",
            "question": "Use Pearson chi-square independence without continuity correction to test the pooled association between sex and admission across these six departments. Department-specific rates are descriptive context.",
            "method": "chi_square_independence", "roles": {"x": "sex", "y": "admission"},
            "unit": "Source: twenty-four aggregate frequency cells for six departments, not original individual records.",
            "derivation": "Preserve all source cells in berkeley_counts.csv. Deterministically repeat each cell by its frequency for the current categorical tool; derived_record_id is a generated label, not an applicant identifier.",
            "claim_supported": "Reproduce the six-department pooled association and the department-specific descriptive admission-rate pattern.",
            "claim_not_supported": "The original paper's whole-university adjusted significance, a causal account of discrimination, or a universal within-department reversal.",
            "reference": {"n": 4526, "chi_square": 92.20528041152764, "df": 1,
                          "p_value": 7.813600388994667e-22, "cramers_v": 0.14273176020608103},
        },
        {
            "id": "anscombe_quartet", "title": "Anscombe's quartet: similar summaries, different plots",
            "data_file": "anscombe_quartet.csv", "design_file": "anscombe_quartet.design.json",
            "source_file": "sources/anscombe.R", "source_name": "R datasets::anscombe",
            "source_url": BASE_URL + SOURCES["anscombe.R"],
            "documentation_url": "https://stat.ethz.ch/R-manual/R-devel/library/datasets/html/anscombe.html",
            "paper_doi": "https://doi.org/10.1080/00031305.1973.10478966",
            "paper_url": "https://personal.us.es/vararey/anscombe1973.pdf",
            "citation": "Anscombe FJ (1973). Graphs in Statistical Analysis. The American Statistician 27(1), 17–21. R documentation credits Tufte (1990), pp. 13–14, as its data source.",
            "question": "Fit one simple linear regression with x1 as predictor and y1 as outcome, including an intercept. Report the slope and its two-sided 95% confidence interval. This run analyses only the first constructed dataset.",
            "method": "simple_linear_regression", "roles": {"x": "x1", "y": "y1"},
            "data_kind": "published_pedagogically_constructed_data",
            "unit": "One indexed pair per constructed dataset, aligned by published row position. These are illustrative constructed values, not real observed subjects.",
            "derivation": "Preserve all four x/y vectors in an eleven-row wide CSV; add only an illustrative row label. The graph analyses x1 and y1 once; the four-panel comparison is deterministic descriptive visualization, not a four-test agent batch.",
            "claim_supported": "Reproduce the first dataset's ordinary least-squares summary and show the quartet's nearly identical summaries despite very different plotted patterns.",
            "claim_not_supported": "Empirical population evidence, a causal relationship, identical unrounded statistics across all four sets, or automatic workflow analysis of all four regressions.",
            "reference": {"n": 11, "slope": 0.5000909090909091, "intercept": 3.0000909090909103,
                          "r_squared": 0.6665424595087749, "t_statistic": 4.241455288892832, "df": 9,
                          "p_value": 0.002169628873078799, "ci_lower": 0.23337013638518744,
                          "ci_upper": 0.7668116817966308},
        },
    ]


def design_documents() -> dict:
    return {
        "student_sleep": {
            "id_column": "patient_id", "randomized": None, "independent_pairs": True,
            "assignment": "Historical drug comparisons. The R data documentation does not establish random assignment or treatment order.",
            "independence": "One matched pair per patient. Different patients are treated as independent units for this teaching reanalysis.",
            "pairing": "Each patient_id matches drug_1 and drug_2 in the R source. The contrast is drug_2 minus drug_1, not a claim about chronological before/after order.",
            "independence_provenance": "Working analysis assumption between patients; the dataset identifies ten distinct patients. This is not a claim of verified random sampling.",
            "variables": {"drug_1": {"type": "numeric", "meaning": "Additional hours of sleep versus control under R drug group 1"},
                          "drug_2": {"type": "numeric", "meaning": "Additional hours of sleep versus control under R drug group 2"}},
            "typical_outcome": "drug_2",
        },
        "berkeley_admissions": {
            "id_column": "derived_record_id", "randomized": False, "independent": True,
            "assignment": "Historical observational admissions counts; sex and department were not randomized.",
            "independence": "Treat counted applications as independent observational units for the pooled contingency-table model; the source is a grouped table.",
            "record_provenance": "The CSV is a deterministic frequency expansion, not original individual-level records. Generated IDs only satisfy the current categorical-tool interface.",
            "variables": {"sex": {"type": "categorical", "levels": ["Male", "Female"], "meaning": "Historical source classification"},
                          "admission": {"type": "categorical", "levels": ["Admitted", "Rejected"]},
                          "department": {"type": "categorical", "levels": list("ABCDEF")}},
            "limitations": ["Only the six largest departments are represented; the whole university had 12763 applications.",
                            "Pooling discards department information and cannot establish discrimination.",
                            "Counts do not verify independence or reveal applicant qualifications."],
        },
        "anscombe_quartet": {
            "id_column": "illustrative_row_id", "randomized": None, "independent": True,
            "assignment": "Published pedagogically constructed values from Anscombe's quartet, not empirical observations or a randomized study.",
            "independence": "For this illustrative regression, treat the listed x1-y1 pairs as independent model units. The values were constructed to teach graphical checking, not sampled from a population.",
            "record_provenance": "The four datasets share published row positions, not subject identities; the generated illustrative_row_id is only an index.",
            "variables": {f"{axis}{i}": {"type": "numeric", "meaning": f"Constructed dataset {i}: {'predictor' if axis == 'x' else 'outcome'}"}
                          for axis in ("x", "y") for i in range(1, 5)},
            "typical_outcome": "y1", "data_kind": "published_pedagogically_constructed_data",
            "limitations": ["This is published illustrative constructed data, not empirical population evidence.",
                            "Only x1-y1 is the approved workflow target; the quartet comparison is descriptive.",
                            "Similar numerical summaries do not establish adequate linear model fit."],
        },
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--destination", type=Path, default=DEFAULT_DESTINATION)
    args = parser.parse_args(argv)
    destination = args.destination.resolve()
    old_path = destination / "manifest.json"
    old = json.loads(old_path.read_text(encoding="utf-8")) if old_path.exists() else {}
    now = datetime.now(timezone.utc).isoformat()
    same_version = old.get("fixture_version") == FIXTURE_VERSION
    access_date = old.get("accessed_utc") if same_version else now
    previous_manifest = old.get("previous_manifest") if same_version else None
    if old and not same_version:
        previous_name = old["fixture_version"]
        previous_bytes = old_path.read_bytes()
        snapshot = destination / "manifests" / (previous_name + ".json")
        write_immutable(snapshot, previous_bytes)
        previous_manifest = {"file": "manifests/" + snapshot.name, "fixture_version": previous_name,
                             "sha256": sha256(previous_bytes), "note": "Exact prior canonical manifest retained for historical run hashes."}
    provenance = []
    for filename, remote_path in SOURCES.items():
        path = destination / "sources" / filename
        previous = next((s for s in old.get("sources", []) if s["file"] == "sources/" + filename), None)
        if path.exists() and previous:
            content = path.read_bytes()
            if sha256(content) != previous["sha256"]:
                raise ValueError(f"Cached source hash mismatch: {path}")
        else:
            request = Request(BASE_URL + remote_path, headers={"User-Agent": "PublicStatisticalReproduction/1.0"})
            with urlopen(request, timeout=40) as response:
                content = response.read()
        write_immutable(path, content)
        provenance.append({"file": "sources/" + filename, "url": BASE_URL + remote_path,
                           "sha256": sha256(content), "bytes": len(content), "accessed_utc": previous["accessed_utc"] if previous else access_date,
                           "source_version": "R SVN trunk; exact downloaded bytes identified by SHA-256"})
    sleep = parse_sleep((destination / "sources" / "sleep.R").read_text(encoding="utf-8"))
    counts = parse_berkeley((destination / "sources" / "UCBAdmissions.R").read_text(encoding="utf-8"))
    anscombe = parse_anscombe((destination / "sources" / "anscombe.R").read_text(encoding="utf-8"))
    write_immutable(destination / "student_sleep.csv", csv_bytes(("patient_id", "drug_1", "drug_2"), sleep))
    write_immutable(destination / "berkeley_counts.csv", csv_bytes(("department", "sex", "admission", "count"), counts))
    expanded = []
    for dept, sex, admission, count in counts:
        for within_cell in range(1, count + 1):
            expanded.append([f"derived_{dept}_{sex}_{admission}_{within_cell:04d}", dept, sex, admission])
    write_immutable(destination / "berkeley_frequency_expanded.csv", csv_bytes(
        ("derived_record_id", "department", "sex", "admission"), expanded))
    write_immutable(destination / "anscombe_quartet.csv", csv_bytes(
        ("illustrative_row_id", "x1", "x2", "x3", "x4", "y1", "y2", "y3", "y4"), anscombe))
    cases = definitions()
    for case in cases:
        case["fixture_version"] = FIXTURE_VERSION
        design_file = case["design_file"]
        write_immutable(destination / design_file, json_bytes(design_documents()[case["id"]]))
        case["data_sha256"] = sha256((destination / case["data_file"]).read_bytes())
        case["source_sha256"] = sha256((destination / case["source_file"]).read_bytes())
        case["reference_method"] = "Independent modern SciPy calculation from the preserved values; not an LLM output or original-paper p-value. Two-sided tests; 95% CI; Pearson chi-square correction=False; OLS with intercept."
        case["tolerance"] = {"rtol": 1e-8, "atol": 1e-12, "p_value_atol": 1e-30}
    manifest = {"schema_version": 1, "fixture_version": FIXTURE_VERSION, "accessed_utc": access_date,
                "license": {"dataset_package": "R datasets: License: Part of R", "r_distribution": "GPL-2 | GPL-3",
                            "url": "https://www.r-project.org/Licenses/", "included_notice": "sources/COPYRIGHTS-R.txt",
                            "included_license": "sources/LICENSE-R-GPL-2.txt", "note": "No standalone CC0 license is asserted for these R snapshots. Source notices are preserved; article rights are separate."},
                "sources": provenance, "cases": cases}
    if previous_manifest:
        manifest["previous_manifest"] = previous_manifest
    if old and not same_version:
        # Version migration only: the prior exact bytes were preserved above.
        if sha256(old_path.read_bytes()) != previous_manifest["sha256"]:
            raise ValueError("The previous manifest changed during version migration.")
        old_path.write_bytes(json_bytes(manifest))
    else:
        write_immutable(old_path, json_bytes(manifest))
    print(json.dumps({"destination": str(destination), "cases": [c["id"] for c in cases], "status": "ready"}))


if __name__ == "__main__":
    main()
