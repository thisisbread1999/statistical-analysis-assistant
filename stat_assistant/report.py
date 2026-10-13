"""Placeholder rendering, the program check of Model A's draft, and report formatting (no LLM here)."""
import re

PLACEHOLDER = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)\}")
LIST_MARKER = re.compile(r"(^|[.!?]\s+)\(?\d{1,2}[.)]\s+", re.M)     # "1. " / "2) " at a sentence start
HYPOTHESIS_NAMES = re.compile(r"\b[HΗ][01]\b")                        # H0 / H1 are names, not numbers
LITERAL_NUMBER = re.compile(r"\d+(?:[.,]\d+)?")


def render(text: str, values: dict) -> str:
    """Replace {placeholder} with the protected value computed by the Python statistical tool; unknown names are left as written."""
    rendered = PLACEHOLDER.sub(lambda m: values.get(m.group(1), m.group(0)), text)
    return re.sub(r"\bp\s*=\s*<\s*", "p < ", rendered)


def check_report(stats_block: dict, draft: dict) -> dict:
    """Program check of Model A's draft against the stored statistical result (no LLM, no re-run of the test).
    1. only known placeholders, and every required one is used (the estimate, CI, test statistic, p ...);
    2. no number written by the model itself: all numbers must come from placeholders;
    3. decision wording matches the result ("reject" / "do not reject H0");
    4. the declared direction and decision match the result;
    5. the limitations are exactly the required ones (none missing, none added)."""
    problems = []
    text = draft["interpretation"]
    used = PLACEHOLDER.findall(text)
    limitation_text = " ".join(l["text"] for l in draft["limitations"])
    unknown = sorted({u for u in PLACEHOLDER.findall(text + " " + limitation_text)
                      if u not in stats_block["values"]})
    if unknown:
        problems.append({"check": "unknown_placeholder", "detail": f"not available: {unknown}; "
                         f"use only {sorted(stats_block['values'])}"})
    missing = [p for p in stats_block["required_placeholders"] if p not in used]
    if missing:
        problems.append({"check": "missing_content", "detail": f"the interpretation must state {missing}"})
    # Catch direct label/value swaps; broader prose meaning is still reviewed by Model B.
    field_patterns = {
        "p_value": r"\bp(?:[-_ ]value)?\s*(?:=|is|was|of)\s*\{(\w+)\}",
        "r": r"\br\s*(?:=|is|was|of)\s*\{(\w+)\}",
        "mean_difference": r"\bmean difference\s*(?:=|is|was|of)\s*\{(\w+)\}",
        "slope": r"\bslope\s*(?:=|is|was|of)\s*\{(\w+)\}",
        "r_squared": r"\bR[- ]squared\s*(?:=|is|was|of)\s*\{(\w+)\}",
        "t_statistic": r"\bt\(\{df\}\)\s*=\s*\{(\w+)\}",
    }
    for field, pattern in field_patterns.items():
        for match in re.finditer(pattern, text, re.I):
            actual = match.group(1)
            null_fields = {"simple_linear_regression": "slope", "pearson_correlation": "r", "welch_t_test": "mean_difference"}
            if (actual == "null_value" and field == null_fields.get(stats_block.get("method"))
                    and re.search(r"\bH0\s*(?:\(|:)\s*$", text[:match.start()], re.I)):
                continue  # A stated null value is not the sample estimate.
            if actual != field:
                problems.append({"check": "field_binding", "detail": f"{field} was labelled with {{{actual}}}; use {{{field}}}."})
    bare = HYPOTHESIS_NAMES.sub("", LIST_MARKER.sub(r"\1", PLACEHOLDER.sub("", text + " " + limitation_text)))
    literals = LITERAL_NUMBER.findall(bare)
    if literals:
        problems.append({"check": "literal_number", "detail": f"numbers must be placeholders, found {literals}"})
    decision_text = render(text, stats_block["values"])
    says_not_reject = re.search(r"\b(not|n't|fail(s|ed)? to)\s+reject", decision_text, re.I)
    says_reject = re.search(r"\breject", decision_text, re.I)
    if stats_block["decision"] == "reject_H0" and (not says_reject or says_not_reject):
        problems.append({"check": "decision_wording", "detail": "the statistical result rejects H0; the text must say that H0 is rejected"})
    if stats_block["decision"] == "do_not_reject_H0" and not says_not_reject:
        problems.append({"check": "decision_wording", "detail": "the statistical result does not reject H0; the text must say so"})
    if draft["direction_claim"] != stats_block["direction"]:
        problems.append({"check": "direction", "detail": f"claims {draft['direction_claim']}, the statistical result gives {stats_block['direction']}"})
    if draft["decision_claim"] != stats_block["decision"]:
        problems.append({"check": "decision", "detail": f"claims {draft['decision_claim']}, the statistical result gives {stats_block['decision']}"})
    written = {l["limitation_id"] for l in draft["limitations"]}
    if len(written) != len(draft["limitations"]):
        problems.append({"check": "duplicate_limitation", "detail": "Each limitation id must occur exactly once."})
    required = set(stats_block["required_limitations"])
    if required - written:
        problems.append({"check": "required_sections", "detail": f"missing limitation(s): {sorted(required - written)}"})
    if written - required:
        problems.append({"check": "required_sections",
                         "detail": f"limitation(s) not in required_limitations: {sorted(written - required)}; remove them"})
    return {"report_version": draft["version"], "passed": not problems, "problems": problems}


def format_stats_block(sb: dict) -> str:
    """The protected statistics as text (all numbers formatted by the program from the statistical result)."""
    v = sb["values"]
    p_clause = "p " + v["p_value"] if v["p_value"].startswith("<") else "p = " + v["p_value"]
    lines = [f"Method: {sb['method_label']}  (data version {sb['data_version']}; Python: {sb['tool_call']})",
             f"{sb['hypotheses']}; α = {v['alpha']}", ""]
    if sb["method"] == "welch_t_test":
        lines += ["| Group | n | Mean | SD |", "|---|---|---|---|",
                  f"| {v['group_1']} | {v['n_group_1']} | {v['mean_group_1']} | {v['sd_group_1']} |",
                  f"| {v['group_2']} | {v['n_group_2']} | {v['mean_group_2']} | {v['sd_group_2']} |", "",
                  f"Mean difference = {v['mean_difference']} ({v['confidence_level']} CI {v['ci_lower']} to "
                  f"{v['ci_upper']}); t({v['df']}) = {v['t_statistic']}; {p_clause}"]
    elif sb["method"] == "pearson_correlation":
        lines += [f"n = {v['n']}; r = {v['r']} ({v['confidence_level']} CI {v['ci_lower']} to {v['ci_upper']}); "
                  f"t({v['df']}) = {v['t_statistic']}; {p_clause}"]
    elif sb["method"] == "chi_square_independence":
        table = sb.get("observed") or {}
        if table:
            lines += ["| | " + " | ".join(table["col_labels"]) + " |", "|---" * (len(table["col_labels"]) + 1) + "|"]
            lines += [f"| {row} | " + " | ".join(str(c) for c in counts) + " |"
                      for row, counts in zip(table["row_labels"], table["counts"])]
            lines += [""]
        lines += [f"n = {v['n']}; chi-square({v['df']}) = {v['chi_square']}; {p_clause}; "
                  f"Cramer's V = {v['cramers_v']}" + (" (Yates continuity correction, 2x2)" if sb.get("yates") else " (no Yates continuity correction)")]
    else:
        lines += [f"n = {v['n']}; slope = {v['slope']} ({v['confidence_level']} CI {v['ci_lower']} to {v['ci_upper']}); "
                  f"intercept = {v['intercept']}; t({v['df']}) = {v['t_statistic']}; {p_clause}; "
                  f"R-squared = {v['r_squared']}"]
    lines += [f"Decision at α = {v['alpha']}: {sb['decision']}"]
    if sb.get("distribution_checks"):
        lines += [f"Distribution checks (descriptive only, never used to choose the method): {sb['distribution_checks']}"]
    if sb.get("tool_warnings"):
        lines += ["Statistical tool warnings: " + "; ".join(map(str, sb["tool_warnings"]))]
    if sb.get("t_statistic_note"):
        lines += ["Statistic note: " + sb["t_statistic_note"]]
    return "\n".join(lines)
