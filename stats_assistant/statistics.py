"""Deterministic, read-only statistical tools using NumPy and SciPy.

``execute(task, request)`` is the public interface. CSV cells remain strings
until a role requires a numeric parse. No value is corrected, imputed or
silently excluded; only the explicit ``excluded_ids`` request is applied.
Diagnostic "usable" subsets are descriptive only: run_test rechecks every
record and every method requirement before performing inference.
"""
from __future__ import annotations

from collections import Counter
import csv
import json
import math
from pathlib import Path
import platform
import warnings

import numpy as np
import scipy
from scipy import stats


class StatToolError(RuntimeError):
    """An I/O, malformed CSV, or unexpected numerical/tool failure."""


METHOD_ROLES = {
    "welch_t_test": {"outcome": "numeric", "group": "categorical"},
    "pearson_correlation": {"x": "numeric", "y": "numeric"},
    "chi_square_independence": {"x": "categorical", "y": "categorical"},
    "simple_linear_regression": {"x": "numeric", "y": "numeric"},
}
METHOD_ALIASES = {
    "welch": "welch_t_test", "welch_ttest": "welch_t_test",
    "pearson": "pearson_correlation", "chi_square": "chi_square_independence",
    "linear_regression": "simple_linear_regression",
}


def _blank(value: str) -> bool:
    return not value.strip() or value == "NA"


def _normal_label(value: str) -> str:
    return "".join(value.split()).casefold()


def _text(value) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _finite_number(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _probability(value) -> bool:
    return _finite_number(value) and 0 < value < 1


def _parse(value: str) -> tuple[float, bool]:
    if _blank(value):
        return np.nan, False
    try:
        return float(value), True
    except ValueError:
        return np.nan, False


def _json_safe(value):
    """Convert NumPy scalars; never emit JSON NaN or Infinity."""
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, (tuple, list, np.ndarray)):
        return [_json_safe(item) for item in value]
    if isinstance(value, np.generic):
        return _json_safe(value.item())
    if isinstance(value, float) and not math.isfinite(value):
        raise StatToolError("A calculation produced a non-finite output; inference was not reported.")
    return value


def _description(values) -> dict:
    finite = np.asarray(values, dtype=float)
    finite = finite[np.isfinite(finite)]
    if not len(finite):
        return {"n": 0, "mean": None, "sd": None, "median": None, "min": None, "max": None}
    with np.errstate(all="ignore"):
        mean, sd = np.mean(finite), np.std(finite, ddof=1) if len(finite) > 1 else np.nan
    return {"n": len(finite), "mean": float(mean) if np.isfinite(mean) else None,
            "sd": float(sd) if np.isfinite(sd) else None,
            "median": float(np.median(finite)), "min": float(np.min(finite)), "max": float(np.max(finite))}


def _shapiro(values):
    if not 3 <= len(values) <= 5000 or np.ptp(values) == 0:
        return None
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        result = float(stats.shapiro(values).pvalue)
    return result if math.isfinite(result) else None


def _validate(task: str, request: dict) -> tuple[dict, list[str]]:
    """Bad requests have a structured status and never start computation."""
    if not isinstance(request, dict):
        return {}, ["request must be a JSON object"]
    req = dict(request)
    problems = []
    req["request_format"] = "v2" if "roles" in req else "v1"
    if req["request_format"] == "v1":
        # Compatibility for the first notebook, which fixed the three columns.
        req.setdefault("method", "welch_t_test")
        req["roles"] = {"outcome": "score", "group": "tutoring"}
        req.setdefault("id_column", "student_id")
        req.setdefault("group_labels", ["yes", "no"])
        req.setdefault("valid_levels", {"tutoring": req["group_labels"]})
        if "score_min" in req and "score_max" in req:
            req.setdefault("valid_ranges", {"score": [req["score_min"], req["score_max"]]})
    req.setdefault("alpha", 0.05)
    req.setdefault("conf_level", 0.95)
    req.setdefault("excluded_ids", [])
    req.setdefault("id_column", None)
    req.setdefault("valid_ranges", {})
    req.setdefault("valid_levels", {})
    req.setdefault("group_labels", [])
    method = req.get("method")
    if isinstance(method, str):
        req["method"] = METHOD_ALIASES.get(method, method)
    if not isinstance(task, str) or task not in {"summary", "diagnostics", "run_test", "welch_test"}:
        problems.append("task must be summary, diagnostics or run_test")
    if not _text(req.get("data_path")):
        problems.append("data_path must name a CSV file")
    if req.get("data_version") is not None and not _text(req["data_version"]):
        problems.append("data_version must be a non-empty string or null")
    method = req.get("method")
    if not isinstance(method, str) or method not in METHOD_ROLES:
        problems.append("method must be one of: " + ", ".join(METHOD_ROLES))
    elif task == "welch_test" and method != "welch_t_test":
        problems.append("welch_test only accepts welch_t_test; use run_test")
    for name in ("alpha", "conf_level"):
        if not _probability(req[name]):
            problems.append(f"{name} must be a finite number strictly between 0 and 1")
    if req["id_column"] is not None and not _text(req["id_column"]):
        problems.append("id_column must be a non-empty column name or null")
    if not isinstance(req["excluded_ids"], list) or any(not _text(v) for v in req["excluded_ids"]):
        problems.append("excluded_ids must be an array of non-empty record ID strings")
    roles = req.get("roles")
    if not isinstance(roles, dict):
        problems.append("roles must be an object mapping role names to column names")
    elif isinstance(method, str) and method in METHOD_ROLES:
        for role, kind in METHOD_ROLES[method].items():
            if not _text(roles.get(role)):
                problems.append(f"roles.{role} must name a {kind} column")
        cols = [roles.get(role) for role in METHOD_ROLES[method]]
        if all(isinstance(col, str) for col in cols):
            if len(cols) != len(set(cols)):
                problems.append("each role must name a different column")
            if req["id_column"] in cols:
                problems.append("id_column cannot also be a role column")
    for field in ("valid_ranges", "valid_levels"):
        if not isinstance(req[field], dict):
            problems.append(f"{field} must be an object")
            continue
        for col, vals in req[field].items():
            if not _text(col):
                problems.append(f"{field} keys must be column names")
            if field == "valid_ranges":
                if not (isinstance(vals, list) and len(vals) == 2 and all(_finite_number(v) for v in vals)
                        and vals[0] <= vals[1]):
                    problems.append(f"valid_ranges.{col} must be [finite_min, finite_max] with min <= max")
            elif not (isinstance(vals, list) and vals and all(_text(v) and not _blank(v) for v in vals)
                      and len(vals) == len(set(vals))):
                problems.append(f"valid_levels.{col} must be a non-empty array of distinct labels")
    if method == "welch_t_test":
        labels = req["group_labels"]
        if not (isinstance(labels, list) and len(labels) == 2 and all(_text(v) and not _blank(v) for v in labels)
                and len({_normal_label(v) for v in labels}) == 2):
            problems.append("group_labels must contain two distinct labels in comparison order")
        elif isinstance(roles, dict) and _text(roles.get("group")) and isinstance(req["valid_levels"], dict):
            declared = req["valid_levels"].get(roles.get("group"))
            if isinstance(declared, list) and not all(v in declared for v in labels):
                problems.append("group_labels must belong to the declared valid_levels for the group")
    return req, problems


class _Analysis:
    def __init__(self, req: dict):
        self.req = req
        self.method = req["method"]
        self.roles = req["roles"]
        self.role_types = METHOD_ROLES[self.method]
        path = Path(req["data_path"])
        try:
            with path.open(newline="", encoding="utf-8-sig") as handle:
                reader = csv.reader(handle, strict=True)
                self.headers = next(reader, [])
                if not self.headers or any(not _text(col) for col in self.headers):
                    raise StatToolError("CSV must have a non-empty header with named columns")
                if len(set(self.headers)) != len(self.headers):
                    raise StatToolError("CSV has duplicate column names; resolve them before analysis")
                raw = []
                for number, values in enumerate(reader, start=1):
                    if len(values) != len(self.headers):
                        raise StatToolError(f"CSV data row {number} has {len(values)} cells; expected {len(self.headers)}")
                    raw.append(dict(zip(self.headers, values)))
        except (OSError, UnicodeError, csv.Error) as error:
            raise StatToolError(f"Cannot read CSV {path}: {error}") from error
        required = list(self.roles[role] for role in self.role_types)
        if req["id_column"]:
            required.append(req["id_column"])
        self.missing = [col for col in dict.fromkeys(required) if col not in self.headers]
        self.n_file = len(raw)
        self.request_warnings = []
        self.rows = []
        self.ids = []
        self.row_numbers = []
        if self.missing:
            return
        all_ids = []
        for number, row in enumerate(raw, start=1):
            written_id = row.get(req["id_column"], "")
            record_id = f"row {number}" if _blank(written_id) else written_id
            all_ids.append(record_id)
            if record_id not in req["excluded_ids"]:
                self.rows.append(row)
                self.ids.append(record_id)
                self.row_numbers.append(number)
        absent = sorted(set(req["excluded_ids"]) - set(all_ids))
        if absent:
            self.request_warnings.append("excluded_ids not found in file: " + ", ".join(absent))
        for field, kind in (("valid_ranges", "numeric"), ("valid_levels", "categorical")):
            for col in req[field]:
                if col not in self.headers:
                    self.request_warnings.append(f"{field}.{col} was not applied: column absent")
                elif col not in required:
                    self.request_warnings.append(f"{field}.{col} was not applied: column has no analysis role")
                elif not any(self.roles[role] == col and typ == kind for role, typ in self.role_types.items()):
                    self.request_warnings.append(f"{field}.{col} was not applied: incompatible role type")

    def values(self, role: str) -> list[str]:
        return [row[self.roles[role]] for row in self.rows]

    def summary(self):
        columns = []
        for role, kind in self.role_types.items():
            written = self.values(role)
            parsed = [_parse(value) for value in written]
            values = np.array([pair[0] for pair in parsed])
            item = {"name": self.roles[role], "role": role, "type": kind,
                    "n_blank": sum(_blank(v) for v in written),
                    "n_parseable_numeric": sum(pair[1] for pair in parsed),
                    "n_unique_as_written": len(set(written))}
            if kind == "categorical":
                counts = Counter(written)
                item["levels_as_written"] = [
                    {"label_as_written": label, "quoted": json.dumps(label), "n": count}
                    for label, count in sorted(counts.items())]
            else:
                finite = values[np.isfinite(values)]
                # Percentiles are descriptions of finite values only, not test exclusions.
                item["quantiles"] = dict(zip(("min", "p05", "p25", "p50", "p75", "p95", "max"),
                    np.quantile(finite, [0, .05, .25, .5, .75, .95, 1]))) if len(finite) else None
                desc = _description(values)
                item.update(mean=desc["mean"], sd=desc["sd"])
            columns.append(item)
        result = {"status": "ok", "n_rows_in_analysis_set": len(self.rows), "columns": columns,
                  "stated_ranges": self.req["valid_ranges"], "stated_levels": self.req["valid_levels"]}
        if self.method == "welch_t_test":
            labels = self.values("group")
            numbers = [_parse(value)[0] for value in self.values("outcome")]
            result["group_labels"] = self.req["group_labels"]
            result["by_group_as_written"] = [
                {"label_as_written": label, "quoted": json.dumps(label),
                 **_description([v for v, group in zip(numbers, labels) if group == label])}
                for label in sorted(set(labels))]
        return result

    def record_checks(self):
        self.findings = []
        self.usable = np.ones(len(self.rows), dtype=bool)
        self.numeric = {}
        self.labels = {}

        def add(index, field, check, severity, detail):
            self.findings.append({"record_id": self.ids[index], "row_number": self.row_numbers[index],
                "field": field, "value_as_written": self.rows[index][field], "check": check,
                "severity": severity, "detail": detail})
            if severity == "blocking":
                self.usable[index] = False

        id_col = self.req["id_column"]
        if id_col:
            counts = Counter(row[id_col] for row in self.rows)
            for i, row in enumerate(self.rows):
                value = row[id_col]
                if _blank(value):
                    add(i, id_col, "missing_id", "blocking", f"{id_col} is missing at data row {self.row_numbers[i]}")
                elif counts[value] > 1:
                    add(i, id_col, "duplicate_id", "blocking",
                        f"ID {value!r} appears in {counts[value]} rows; excluding this ID removes ALL those rows")
        for role, kind in self.role_types.items():
            col = self.roles[role]
            written = self.values(role)
            if kind == "numeric":
                vals = []
                for i, value in enumerate(written):
                    number, parseable = _parse(value)
                    vals.append(number)
                    if _blank(value):
                        add(i, col, "missing_value", "blocking", f"{col} is missing")
                    elif not parseable:
                        add(i, col, "non_numeric_value", "blocking", f"{col} is not a number")
                    elif not math.isfinite(number):
                        add(i, col, "non_finite_value", "blocking", f"{col} is not a finite number")
                    elif col in self.req["valid_ranges"]:
                        low, high = self.req["valid_ranges"][col]
                        if not low <= number <= high:
                            add(i, col, "out_of_range", "blocking", f"{col} is outside the stated range [{low}, {high}]")
                self.numeric[role] = np.asarray(vals, dtype=float)
            else:
                self.labels[role] = np.asarray(written, dtype=str)
                declared = self.req["valid_levels"].get(col)
                for i, value in enumerate(written):
                    if _blank(value):
                        add(i, col, "missing_label", "blocking", f"{col} label is missing")
                    elif declared is not None and value not in declared:
                        match = next((v for v in declared if _normal_label(v) == _normal_label(value)), None)
                        detail = f"Label matches {match!r} only after removing whitespace/changing case" if match is not None else f"Label is not among {declared!r}"
                        add(i, col, "invalid_label", "blocking", detail)
                if declared is None:
                    for key in sorted({_normal_label(v) for v in written if not _blank(v)}):
                        forms = Counter(v for v in written if not _blank(v) and _normal_label(v) == key)
                        if len(forms) < 2:
                            continue
                        preferred = [v for v in forms if role == "group" and v in self.req["group_labels"]]
                        top = [v for v, n in forms.items() if n == max(forms.values())]
                        reference = preferred[0] if len(preferred) == 1 else top[0] if len(top) == 1 else None
                        for i, value in enumerate(written):
                            if not _blank(value) and _normal_label(value) == key and value != reference:
                                add(i, col, "invalid_label", "blocking",
                                    f"Observed labels {sorted(forms)!r} differ only by whitespace/case; verify the intended label")
        # NumPy linear quartiles (R quantile type 7), explicitly a verify flag.
        def boxplot(role, mask, detail):
            values = self.numeric[role][mask]
            if len(values) < 4:
                return
            q1, q3 = np.quantile(values, [.25, .75])
            low, high = q1 - 1.5 * (q3-q1), q3 + 1.5 * (q3-q1)
            for i in np.flatnonzero(mask & ((self.numeric[role] < low) | (self.numeric[role] > high))):
                add(i, self.roles[role], "boxplot_flag", "verify", detail)
        if self.method == "welch_t_test":
            for label in self.req["group_labels"]:
                boxplot("outcome", self.usable & (self.labels["group"] == label),
                        f"Outside 1.5*IQR fences for group {label!r}; verify, do not automatically exclude")
        elif self.method in {"pearson_correlation", "simple_linear_regression"}:
            for role in ("x", "y"):
                boxplot(role, self.usable, "Outside 1.5*IQR fences among usable rows; verify, do not automatically exclude")
        self.n_blocking = sum(f["severity"] == "blocking" for f in self.findings)
        self.n_verify = sum(f["severity"] == "verify" for f in self.findings)

    def table(self):
        level_lists = []
        for role in ("x", "y"):
            observed = set(self.labels[role][self.usable])
            declared = self.req["valid_levels"].get(self.roles[role])
            level_lists.append([v for v in declared if v in observed] if declared else sorted(observed))
        rows, cols = level_lists
        counts = np.zeros((len(rows), len(cols)), dtype=int)
        for x, y in zip(self.labels["x"][self.usable], self.labels["y"][self.usable]):
            counts[rows.index(x), cols.index(y)] += 1
        return rows, cols, counts

    def regression(self):
        x, y = self.numeric["x"][self.usable], self.numeric["y"][self.usable]
        with np.errstate(all="ignore"):
            xc, yc = x - np.mean(x), y - np.mean(y)
            sxx, syy = np.dot(xc, xc), np.dot(yc, yc)
            slope = np.dot(xc, yc) / sxx
            residuals = yc - slope * xc
            sse = np.dot(residuals, residuals)
            se = np.sqrt(sse / (len(x) - 2) / sxx)
            intercept = np.mean(y) - slope * np.mean(x)
        return {"sxx": sxx, "syy": syy, "slope": slope, "intercept": intercept,
                "residuals": residuals, "sse": sse, "slope_se": se, "y": y}

    def method_checks(self):
        findings = []
        def add(check, detail):
            findings.append({"check": check, "severity": "out_of_scope", "detail": detail})
        n = int(np.sum(self.usable))
        if self.method == "welch_t_test":
            observed = set(self.labels["group"][self.usable])
            compared = set(self.req["group_labels"])
            if observed != compared:
                add("wrong_number_of_groups", f"Observed groups {sorted(observed)!r} do not match the two compared labels {self.req['group_labels']!r}; no other groups are silently discarded")
            for label in self.req["group_labels"]:
                values = self.numeric["outcome"][self.usable & (self.labels["group"] == label)]
                if len(values) < 2:
                    add("group_too_small", f"Group {label!r} needs at least 2 observations (found {len(values)})")
                else:
                    with np.errstate(all="ignore"):
                        variance = np.var(values, ddof=1)
                    if not np.isfinite(variance):
                        add("numeric_instability", f"Group {label!r} variance is not representable; rescale verified data explicitly")
                    elif variance <= 0:
                        add("no_variation", f"Group {label!r} has zero or numerically degenerate variance")
        elif self.method in {"pearson_correlation", "simple_linear_regression"}:
            minimum = 4 if self.method == "pearson_correlation" else 3
            if n < minimum:
                add("too_few_observations", f"{self.method} needs at least {minimum} observations (found {n})")
            for role in ("x", "y"):
                if n >= 2:
                    with np.errstate(all="ignore"):
                        variance = np.var(self.numeric[role][self.usable], ddof=1)
                    if not np.isfinite(variance):
                        add("numeric_instability", f"Variance of {self.roles[role]} is not representable")
                    elif variance <= 0:
                        add("no_variation", f"{self.roles[role]} is constant or has numerically degenerate variance")
            if self.method == "simple_linear_regression" and not findings:
                fit = self.regression()
                scalars = [fit[k] for k in ("slope", "intercept", "sse", "slope_se", "sxx", "syy")]
                if not all(np.isfinite(v) for v in scalars):
                    add("degenerate_standard_error", "Regression has non-finite arithmetic/standard error; no inferential result is reported")
                else:
                    tolerance = 100 * np.finfo(float).eps ** 2 * fit["syy"]
                    if fit["sse"] <= tolerance or fit["slope_se"] <= 0:
                        add("zero_residual_variance", "Residual variance is zero or numerically degenerate; a usual slope t-test and interval are not reported")
        else:
            rows, cols, counts = self.table()
            for role, levels in (("x", rows), ("y", cols)):
                if len(levels) < 2:
                    add("too_few_levels", f"{self.roles[role]} needs at least 2 observed levels (found {len(levels)})")
            if not findings:
                expected = stats.contingency.expected_freq(counts)
                if np.min(expected) < 1 or np.mean(expected < 5) > .2:
                    add("expected_counts_too_small", f"Cochran rule failed: min expected = {np.min(expected):.4g}, share below 5 = {np.mean(expected < 5):.1%}; require none below 1 and at most 20% below 5. Fisher's exact test is not supported in this stage.")
        return findings

    def distribution_checks(self):
        n = int(np.sum(self.usable))
        if self.method == "welch_t_test":
            return [{"check": "shapiro_wilk", "variable": self.roles["outcome"], "group": label,
                     "n": int(np.sum(mask)), "shapiro_wilk_p": _shapiro(self.numeric["outcome"][mask])}
                    for label in self.req["group_labels"]
                    for mask in [self.usable & (self.labels["group"] == label)]]
        if self.method == "pearson_correlation":
            return [{"check": "shapiro_wilk", "variable": self.roles[role], "role": role, "n": n,
                     "shapiro_wilk_p": _shapiro(self.numeric[role][self.usable])} for role in ("x", "y")]
        if self.method == "simple_linear_regression":
            fit = self.regression()
            fitted = fit["y"] - fit["residuals"]
            rho, pvalue = None, None
            if np.ptp(np.abs(fit["residuals"])) > 0 and np.ptp(fitted) > 0:
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore")
                    result = stats.spearmanr(np.abs(fit["residuals"]), fitted)
                rho = float(result.statistic) if np.isfinite(result.statistic) else None
                pvalue = float(result.pvalue) if np.isfinite(result.pvalue) else None
            return [{"check": "shapiro_wilk", "variable": "residuals", "n": n,
                     "shapiro_wilk_p": _shapiro(fit["residuals"])},
                    {"check": "spread_check", "variable": "|residual| vs fitted value", "method": "spearman",
                     "n": n, "spearman_rho": rho, "p_value": pvalue}]
        _, _, counts = self.table()
        expected = stats.contingency.expected_freq(counts)
        return [{"check": "expected_counts", "min_expected_count": float(np.min(expected)),
                 "share_cells_expected_below_5": float(np.mean(expected < 5)), "n_cells": expected.size}]

    def diagnostics(self):
        self.record_checks()
        mf = self.method_checks() if not self.n_blocking else []
        dist_run = self.n_blocking == 0 and not mf
        note = ("Descriptive diagnostics only; they never switch the method. A large Shapiro-Wilk p-value does not prove normality, and a small one alone does not rule out the planned test. Shapiro runs only for 3 <= n <= 5000."
                if dist_run else "Deferred: resolve blocking record-level problems and method requirements before distribution checks.")
        return {"status": "ok", "n_rows_in_analysis_set": len(self.rows), "n_usable_rows": int(np.sum(self.usable)),
                "findings": self.findings, "n_blocking": self.n_blocking, "n_verify": self.n_verify,
                "method_checks_run": not self.n_blocking, "method_findings": mf,
                "distribution_checks_run": dist_run, "distribution_checks": self.distribution_checks() if dist_run else [],
                "distribution_checks_note": note}

    def run_test(self):
        diagnostics = self.diagnostics()
        if self.n_blocking:
            return {"status": "blocked", "reason": "Unresolved record-level problems; test was not run.",
                    "n_blocking": self.n_blocking, "problem_ids": list(dict.fromkeys(f["record_id"] for f in self.findings if f["severity"] == "blocking"))}
        if diagnostics["method_findings"]:
            return {"status": "out_of_scope", "reason": "Method requirements are not met; test was not run.",
                    "method_findings": diagnostics["method_findings"]}
        n = len(self.rows)  # identical to usable size after all blocking checks pass
        conf, alpha = self.req["conf_level"], self.req["alpha"]
        result = {"status": "ok", "alternative": "two-sided", "conf_level": conf, "alpha": alpha,
                  "n_included": n, "tool_warnings": []}
        if self.method == "welch_t_test":
            g1, g2 = self.req["group_labels"]
            x1, x2 = [self.numeric["outcome"][self.labels["group"] == g] for g in (g1, g2)]
            test = stats.ttest_ind(x1, x2, equal_var=False, alternative="two-sided")
            interval = test.confidence_interval(confidence_level=conf)
            result.update(method_label="Welch independent-samples t-test", var_equal=False,
                group_1={"label": g1, "n": len(x1), "mean": np.mean(x1), "sd": np.std(x1, ddof=1)},
                group_2={"label": g2, "n": len(x2), "mean": np.mean(x2), "sd": np.std(x2, ddof=1)},
                mean_difference=np.mean(x1)-np.mean(x2), ci_lower=interval.low, ci_upper=interval.high,
                t_statistic=test.statistic, df=test.df, p_value=test.pvalue,
                tool_call=f"scipy.stats.ttest_ind(group_1={g1!r}, group_2={g2!r}, equal_var=False, alternative='two-sided'); confidence_interval(confidence_level={conf})")
        elif self.method == "pearson_correlation":
            x, y = self.numeric["x"], self.numeric["y"]
            test = stats.pearsonr(x, y, alternative="two-sided")
            r = float(test.statistic)
            xc, yc = x-np.mean(x), y-np.mean(y)
            normalized_difference = yc / np.linalg.norm(yc) - np.sign(r) * xc / np.linalg.norm(xc)
            perfect = abs(r) == 1 or np.linalg.norm(normalized_difference) <= 8 * np.finfo(float).eps * np.sqrt(n)
            if perfect:
                r = float(np.sign(r))
                low, high, tvalue, pvalue = r, r, None, 0.0
                result["t_statistic_note"] = "Perfect sample correlation: t diverges; null encodes its non-finite limit. The Fisher-z interval is the boundary limit [r, r], not proof of a deterministic population relation."
                result["perfect_correlation"] = True
                result["tool_warnings"].append("Perfect sample correlation is a boundary case; verify data provenance and do not interpret the zero-width limiting interval as population certainty.")
            else:
                z = np.arctanh(r)
                half = stats.norm.ppf((1+conf)/2) / np.sqrt(n-3)
                low, high = np.tanh([z-half, z+half])
                tvalue, pvalue = r*np.sqrt((n-2)/(1-r*r)), test.pvalue
                result["perfect_correlation"] = False
            result.update(method_label="Pearson product-moment correlation", n=n, r=r,
                ci_lower=low, ci_upper=high, t_statistic=tvalue, df=n-2, p_value=pvalue,
                ci_method="Fisher z normal approximation",
                tool_call=f"scipy.stats.pearsonr(x, y, alternative='two-sided'); Fisher-z interval(confidence_level={conf})")
        elif self.method == "chi_square_independence":
            rows, cols, counts = self.table()
            test = stats.chi2_contingency(counts, correction=False)
            result.update(method_label="Pearson chi-square test of independence (uncorrected)", n=n,
                chi_square=test.statistic, df=test.dof, p_value=test.pvalue,
                cramers_v=np.sqrt(test.statistic/(n*(min(counts.shape)-1))), yates_correction=False,
                observed={"row_labels": rows, "col_labels": cols, "counts": counts.tolist()},
                expected={"row_labels": rows, "col_labels": cols, "counts": test.expected_freq.tolist()},
                min_expected_count=np.min(test.expected_freq),
                tool_call="scipy.stats.chi2_contingency(observed, correction=False); Cramer's V uses the same uncorrected chi-square")
        else:
            fit = self.regression()
            degrees = n-2
            tvalue = fit["slope"]/fit["slope_se"]
            critical = stats.t.ppf((1+conf)/2, degrees)
            result.update(method_label="Ordinary least squares (one predictor, with intercept)", n=n,
                slope=fit["slope"], slope_se=fit["slope_se"], intercept=fit["intercept"],
                ci_lower=fit["slope"]-critical*fit["slope_se"], ci_upper=fit["slope"]+critical*fit["slope_se"],
                t_statistic=tvalue, df=degrees, p_value=2*stats.t.sf(abs(tvalue), degrees),
                r_squared=1-fit["sse"]/fit["syy"],
                tool_call=f"NumPy centered OLS with intercept; scipy.stats.t slope inference(confidence_level={conf})")
        result["decision"] = "reject_H0" if result["p_value"] < alpha else "do_not_reject_H0"
        return result


def execute(task: str, request: dict) -> dict:
    """Run summary, diagnostics, or run_test; return a strict-JSON-safe dict.

    Unsupported requests and unsuitable data are structured results. File I/O,
    malformed CSV and unexpected non-finite computations raise StatToolError.
    """
    req, problems = _validate(task, request)
    original = request if isinstance(request, dict) else {}
    base = {"task": task if isinstance(task, str) else None,
            "data_version": original.get("data_version") if _text(original.get("data_version")) else None,
            "data_path": original.get("data_path") if _text(original.get("data_path")) else None,
            "method": req.get("method") if _text(req.get("method")) else None, "request_format": req.get("request_format"),
            "n_rows_in_file": None, "columns_found": [], "missing_required_columns": [],
            "excluded_ids": req.get("excluded_ids", []), "request_warnings": [],
            "python_version": platform.python_version(), "scipy_version": scipy.__version__,
            "tool_call": f"stats_assistant.statistics.execute({task!r}, request)"}
    if problems:
        # Do not echo invalid NaN / Infinity values from a malformed request.
        safe_base = {key: value for key, value in base.items() if key != "excluded_ids"}
        safe_base["excluded_ids"] = []
        return {**safe_base, "status": "unsupported_request", "problems": problems,
                "reason": "The request is incomplete or unsupported; nothing was computed."}
    analysis = _Analysis(req)
    base.update(n_rows_in_file=analysis.n_file, columns_found=analysis.headers,
                missing_required_columns=analysis.missing, request_warnings=analysis.request_warnings)
    if analysis.missing:
        return {**base, "status": "missing_required_columns"}
    try:
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            result = analysis.summary() if task == "summary" else analysis.diagnostics() if task == "diagnostics" else analysis.run_test()
        if caught:
            result.setdefault("tool_warnings", []).extend(str(item.message) for item in caught)
        final = _json_safe({**base, **result})
        json.dumps(final, allow_nan=False)
        return final
    except (ValueError, FloatingPointError, OverflowError) as error:
        raise StatToolError(f"Statistical computation failed: {error}") from error
