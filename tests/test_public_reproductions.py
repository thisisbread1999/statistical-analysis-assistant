"""Fixture integrity and published-data numerical references, without model calls."""
from collections import Counter
import json

import pytest

from reproduce_public import (FIXTURES, compare, department_rates, load_manifest,
                              numerical_reference, quartet_descriptive_summaries, read_csv, tool_request, verify_fixtures, file_hash)
from scripts.fetch_public_reproductions import parse_anscombe
from stat_assistant.tools import execute


def test_preserved_public_sources_and_frequency_expansion_are_consistent():
    manifest = verify_fixtures()
    assert manifest["fixture_version"] == "public-reproductions-v2"
    assert {c["id"] for c in manifest["cases"]} == {"student_sleep", "berkeley_admissions", "anscombe_quartet"}
    assert manifest["license"]["r_distribution"] == "GPL-2 | GPL-3"
    for source in manifest["sources"]:
        assert source["url"].startswith("https://svn.r-project.org/R/trunk/")
        assert source["accessed_utc"]
        assert len(source["sha256"]) == 64
    rows = read_csv(FIXTURES / "berkeley_frequency_expanded.csv")
    assert len(rows) == 4526
    assert all(r["derived_record_id"].startswith("derived_") for r in rows)
    assert Counter(r["sex"] for r in rows) == {"Male": 2691, "Female": 1835}


def test_sleep_matches_source_patient_ids_without_invented_randomization():
    rows = read_csv(FIXTURES / "student_sleep.csv")
    assert len(rows) == 10
    assert [r["patient_id"] for r in rows] == [str(i) for i in range(1, 11)]
    assert [float(r["drug_1"]) for r in rows] == [.7, -1.6, -.2, -1.2, -.1, 3.4, 3.7, .8, 0, 2]
    assert [float(r["drug_2"]) for r in rows] == [1.9, .8, 1.1, .1, -.1, 4.4, 5.5, 1.6, 4.6, 3.4]
    design = json.loads((FIXTURES / "student_sleep.design.json").read_text())
    assert design["randomized"] is None
    assert design["independent_pairs"] is True


@pytest.mark.parametrize("case", load_manifest()["cases"], ids=lambda c: c["id"])
def test_independent_reference_and_statistical_tool_match_known_targets(case):
    independent = numerical_reference(case)
    assert compare(case["reference"], independent, case["tolerance"])["status"] == "passed"
    result = execute("run_test", tool_request(case))
    assert result["status"] == "ok", result
    assert compare(case["reference"], result, case["tolerance"])["status"] == "passed"
    if case["id"] == "student_sleep":
        assert result["mean_difference"] == pytest.approx(1.58)
        assert result["t_statistic"] > 0  # drug_2 minus drug_1 is the prescribed contrast.
    elif case["id"] == "berkeley_admissions":
        assert result["yates_correction"] is False
    else:
        assert result["slope"] == pytest.approx(0.5000909090909091)


def test_berkeley_department_rates_do_not_claim_universal_reversal():
    rows = {(r["department"], r["sex"]): r for r in department_rates()}
    assert rows["A", "Male"]["admitted"] == 512
    assert rows["A", "Female"]["admission_rate"] == pytest.approx(89 / 108)
    assert rows["C", "Female"]["admission_rate"] < rows["C", "Male"]["admission_rate"]
    assert rows["E", "Female"]["admission_rate"] < rows["E", "Male"]["admission_rate"]
    assert sum(rows[d, "Female"]["admission_rate"] > rows[d, "Male"]["admission_rate"] for d in "ABCDEF") == 4


def test_anscombe_retains_all_four_constructed_sets_but_targets_one_regression():
    case = next(c for c in load_manifest()["cases"] if c["id"] == "anscombe_quartet")
    expected = parse_anscombe((FIXTURES / case["source_file"]).read_text(encoding="utf-8"))
    actual = read_csv(FIXTURES / case["data_file"])
    assert len(actual) == 11
    for source_row, csv_row in zip(expected, actual):
        assert source_row[0] == csv_row["illustrative_row_id"]
        assert source_row[1:] == [float(csv_row[f"{axis}{i}"]) for axis in ("x", "y") for i in range(1, 5)]
    assert case["roles"] == {"x": "x1", "y": "y1"}
    design = json.loads((FIXTURES / case["design_file"]).read_text(encoding="utf-8"))
    assert design["data_kind"] == "published_pedagogically_constructed_data"
    summaries = quartet_descriptive_summaries()
    assert len(summaries) == 4
    slopes = [s["slope"] for s in summaries]
    assert max(slopes) - min(slopes) < .001
    assert len(set(slopes)) > 1  # Nearly identical at common rounding, not identical in exact arithmetic.


def test_previous_manifest_bytes_still_verify_historical_run_hashes():
    previous = load_manifest()["previous_manifest"]
    assert previous["fixture_version"] == "public-reproductions-v1"
    assert file_hash(FIXTURES / previous["file"]) == previous["sha256"]
    old_run = json.loads((FIXTURES / "evidence/mock_20261101_v2/summary.json").read_text(encoding="utf-8"))
    assert old_run["source_manifest_sha256"] == previous["sha256"]
