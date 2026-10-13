"""Report guard regressions and model identity checks; no live model calls."""
import copy
import math

import pytest

from stat_assistant import models
from stat_assistant.methods import format_p
from stat_assistant.report import check_report, render


@pytest.fixture
def report_pair():
    """A valid report with a non-significant, positive mean difference."""
    block = {
        "values": {"mean_difference": "1.20", "p_value": "0.7000", "ci_lower": "-5.00",
                   "ci_upper": "7.40", "t_statistic": "0.380", "df": "50.00"},
        "required_placeholders": ["mean_difference", "p_value", "ci_lower", "ci_upper", "t_statistic", "df"],
        "direction": "positive", "decision": "do_not_reject_H0",
        "required_limitations": {"nonrandom_design": "This analysis does not establish causation."},
    }
    draft = {
        "version": "draft1",
        "interpretation": "The mean difference is {mean_difference}, CI {ci_lower} to {ci_upper}; "
                          "t({df}) = {t_statistic}, p = {p_value}. We do not reject H0. "
                          "This does not establish equal population means.",
        "direction_claim": "positive", "decision_claim": "do_not_reject_H0",
        "limitations": [{"limitation_id": "nonrandom_design", "text": "This analysis does not establish causation."}],
    }
    return block, draft


def checks(block, draft):
    return {problem["check"] for problem in check_report(block, draft)["problems"]}


def test_valid_report_hypothesis_names_and_protected_rendering(report_pair):
    block, draft = report_pair
    assert check_report(block, draft)["passed"]
    output = render(draft["interpretation"], block["values"])
    assert "p = 0.7000" in output and "CI -5.00 to 7.40" in output
    assert "H0" in output and "{" not in output


def test_missing_interval_cannot_be_hidden_in_limitations(report_pair):
    block, draft = report_pair
    draft["interpretation"] = draft["interpretation"].replace("CI {ci_lower} to {ci_upper}; ", "")
    draft["limitations"][0]["text"] += " Interval: {ci_lower} to {ci_upper}."
    assert "missing_content" in checks(block, draft)


@pytest.mark.parametrize("section", ["interpretation", "limitations"])
def test_invented_literal_is_rejected_in_either_section(report_pair, section):
    block, draft = report_pair
    if section == "interpretation":
        draft[section] += " The p-value is 0.001."
    else:
        draft[section][0]["text"] += " There were 99 excluded records."
    assert "literal_number" in checks(block, draft)


@pytest.mark.parametrize("section", ["interpretation", "limitations"])
def test_unknown_placeholder_is_rejected_in_either_section(report_pair, section):
    block, draft = report_pair
    if section == "interpretation":
        draft[section] += " Effect: {invented_statistic}."
    else:
        draft[section][0]["text"] += " Uncertainty: {invented_statistic}."
    assert "unknown_placeholder" in checks(block, draft)


def test_swapped_p_and_mean_difference_are_rejected_even_when_fields_present(report_pair):
    block, draft = report_pair
    draft["interpretation"] = draft["interpretation"].replace("{mean_difference}", "TEMP")
    draft["interpretation"] = draft["interpretation"].replace("{p_value}", "{mean_difference}").replace("TEMP", "{p_value}")
    result = check_report(block, draft)
    assert not result["passed"]
    assert "field_binding" in {p["check"] for p in result["problems"]}
    assert "missing_content" not in {p["check"] for p in result["problems"]}


@pytest.mark.parametrize("label", ["r", "slope", "R-squared"])
def test_another_estimate_label_cannot_be_bound_to_p_value(report_pair, label):
    block, draft = report_pair
    draft["interpretation"] += f" {label} = {{p_value}}."
    assert "field_binding" in checks(block, draft)


def test_test_statistic_cannot_be_bound_to_p_value(report_pair):
    block, draft = report_pair
    draft["interpretation"] = draft["interpretation"].replace("= {t_statistic}", "= {p_value}")
    draft["interpretation"] += " Stored statistic: {t_statistic}."
    assert "field_binding" in checks(block, draft)


@pytest.mark.parametrize("key,value,expected", [
    ("direction_claim", "negative", "direction"),
    ("decision_claim", "reject_H0", "decision"),
])
def test_structured_claims_must_match_results(report_pair, key, value, expected):
    block, draft = report_pair
    draft[key] = value
    assert expected in checks(block, draft)


def test_significance_decision_must_also_match_written_conclusion(report_pair):
    block, draft = report_pair
    draft["interpretation"] = draft["interpretation"].replace("do not reject", "reject")
    assert "decision_wording" in checks(block, draft)


@pytest.mark.parametrize("change,expected", [
    ("missing", "required_sections"), ("extra", "required_sections"),
    ("duplicate", "duplicate_limitation"),
])
def test_required_limitations_must_appear_exactly_once(report_pair, change, expected):
    block, draft = report_pair
    if change == "missing":
        draft["limitations"] = []
    elif change == "extra":
        draft["limitations"].append({"limitation_id": "invented", "text": "Unverified condition."})
    else:
        draft["limitations"].append(copy.deepcopy(draft["limitations"][0]))
    assert expected in checks(block, draft)


@pytest.mark.parametrize("p", [0.04996, 0.04999999, 0.05000001, 0.05004,
                              math.nextafter(0.05, 0.0), math.nextafter(0.05, 1.0)])
def test_p_value_rounding_preserves_side_of_significance_threshold(p):
    displayed = float(format_p(p))
    assert (displayed < 0.05) == (p < 0.05)
    assert (displayed > 0.05) == (p > 0.05)


def test_p_value_exact_threshold_and_small_values_are_unambiguous():
    assert float(format_p(0.05)) == 0.05
    assert format_p(0.014) == "0.0140"
    assert format_p(0.000001) == "< 0.0001"


def test_ollama_latest_alias_cannot_create_two_nominal_models(monkeypatch):
    def unexpected_call(*args, **kwargs):
        pytest.fail("Identity guard must reject aliases before a network/model call.")
    monkeypatch.setattr(models, "check_ollama_models", unexpected_call)
    monkeypatch.setattr(models, "make_chat_model", unexpected_call)
    with pytest.raises(ValueError, match="different underlying models"):
        models.create_agents({"mode": "real", "model_a": "ollama:gemma3", "model_b": "ollama:gemma3:latest"})


class FakeTags:
    def __init__(self, entries):
        self.entries = entries

    def raise_for_status(self):
        return None

    def json(self):
        return {"models": self.entries}


def test_ollama_weight_aliases_are_rejected_using_tags_digest(monkeypatch):
    import requests
    monkeypatch.setattr(requests, "get", lambda *a, **kw: FakeTags([
        {"name": "original:latest", "digest": "same-weights"},
        {"name": "reviewer:latest", "digest": "same-weights"},
    ]))
    with pytest.raises(ValueError, match="same Ollama weights"):
        models.check_ollama_models(["ollama:original", "ollama:reviewer"])


def test_distinct_ollama_models_use_configured_endpoint_without_inference(monkeypatch):
    import requests
    calls = []
    def fake_get(url, **kwargs):
        calls.append(url)
        return FakeTags([{"name": "qwen3:8b", "digest": "weights-a"},
                         {"name": "gemma3:12b", "digest": "weights-b"}])
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://127.0.0.1:9876/")
    monkeypatch.setattr(requests, "get", fake_get)
    models.check_ollama_models(["ollama:qwen3:8b", "ollama:gemma3:12b"])
    assert calls == ["http://127.0.0.1:9876/api/tags"]


def test_missing_local_model_is_not_treated_as_ready(monkeypatch):
    import requests
    monkeypatch.setattr(requests, "get", lambda *a, **kw: FakeTags([
        {"name": "qwen3:8b", "digest": "weights-a"},
    ]))
    with pytest.raises(RuntimeError, match="Download the local model"):
        models.check_ollama_models(["ollama:qwen3:8b", "ollama:gemma3:12b"])


def test_small_p_renders_as_inequality_without_equals():
    assert render("p = {p_value}", {"p_value": "< 0.0001"}) == "p < 0.0001"
    assert render("p = {p_value}", {"p_value": "0.2000"}) == "p = 0.2000"


def test_report_sentence_plans_obey_the_placeholder_number_contract():
    import re
    from stat_assistant.methods import METHODS
    from stat_assistant.report import PLACEHOLDER, HYPOTHESIS_NAMES
    for spec in METHODS.values():
        instructions = HYPOTHESIS_NAMES.sub("", PLACEHOLDER.sub("", " ".join(spec.sentence_plan)))
        assert re.search(r"\d", instructions) is None


def test_null_hypothesis_slope_is_distinct_from_sample_estimate(report_pair):
    block, draft = copy.deepcopy(report_pair)
    block["method"] = "simple_linear_regression"
    block["values"].update(null_value="0", slope="1.20")
    draft["interpretation"] += " H0 (slope = {null_value})."
    assert check_report(block, draft)["passed"]
    draft["interpretation"] += " The estimated slope is {null_value}."
    assert any(p["check"] == "field_binding" for p in check_report(block, draft)["problems"])

def test_protected_decision_words_are_checked_after_rendering(report_pair):
    block, draft = copy.deepcopy(report_pair)
    block["values"]["decision_claim"] = "do not reject"
    draft["interpretation"] = draft["interpretation"].replace("do not reject", "{decision_claim}")
    assert check_report(block, draft)["passed"]
    block["values"]["decision_claim"] = "reject"
    assert any(p["check"] == "decision_wording" for p in check_report(block, draft)["problems"])
