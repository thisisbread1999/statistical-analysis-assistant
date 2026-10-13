"""The statistical methods supported in this stage, and how their statistical results become protected report fields.

Each method has:
* roles: which variables it needs and their type,
* placeholders: the names Model A may write as {name}; the program fills in the values computed by the Python statistical tool,
* required: placeholders the interpretation must contain,
* the hypotheses, the direction field and the method-specific limitation.
"""
from dataclasses import dataclass, field

from .settings import ALPHA


@dataclass(frozen=True)
class MethodSpec:
    label: str                      # wording used in prompts and reports
    answers: str                    # the kind of question the method answers
    roles: dict                     # role -> "numeric" | "categorical"
    placeholders: tuple             # numbers Model A may cite as {name}
    required: tuple                 # placeholders the interpretation must contain
    direction_field: str | None     # sign gives the direction claim; None = no direction (chi-square)
    sentence_plan: tuple            # order of sentences for Model A's interpretation
    limitation: dict = field(default_factory=dict)   # method-specific required limitation {id: text}


METHODS = {
    "welch_t_test": MethodSpec(
        label="two-sided Welch independent-samples t-test",
        answers="difference between the means of a numeric outcome in two independent groups",
        roles={"outcome": "numeric", "group": "categorical"},
        placeholders=("group_1", "group_2", "n_group_1", "n_group_2", "mean_group_1", "mean_group_2",
                      "sd_group_1", "sd_group_2", "mean_difference", "ci_lower", "ci_upper",
                      "t_statistic", "df", "p_value", "n_included", "alpha", "confidence_level"),
        required=("t_statistic", "df", "p_value", "mean_difference", "ci_lower", "ci_upper"),
        direction_field="mean_difference",
        sentence_plan=("how many records were analysed in each group",
                       "Welch's test result: t({df}) = {t_statistic}, p = {p_value}",
                       "the decision at {alpha}: we reject H0 / we do not reject H0 (for 'do not reject', add "
                       "that this is not evidence that the two means are equal)",
                       "the estimated mean difference ({group_1} minus {group_2}) with its {confidence_level} CI, "
                       "and which group's sample mean was higher",
                       "that this is an association only when groups were not randomized"),
    ),
    "pearson_correlation": MethodSpec(
        label="Pearson correlation test (two-sided)",
        answers="linear association between two numeric variables",
        roles={"x": "numeric", "y": "numeric"},
        placeholders=("n", "r", "ci_lower", "ci_upper", "t_statistic", "df", "p_value", "alpha", "confidence_level"),
        required=("r", "ci_lower", "ci_upper", "p_value", "n"),
        direction_field="r",
        sentence_plan=("how many records were analysed",
                       "Pearson's r = {r} with its {confidence_level} CI and p = {p_value}",
                       "the decision at {alpha}: we reject H0 (rho = {null_value}) / we do not reject H0",
                       "the direction and strength of the linear association in plain words",
                       "that correlation does not establish causation"),
        limitation={"linear_association_only": "Pearson's r measures only linear association; a weak r does not "
                                               "rule out a non-linear relationship."},
    ),
    "chi_square_independence": MethodSpec(
        label="chi-square test of independence",
        answers="association between two categorical variables",
        roles={"x": "categorical", "y": "categorical"},
        placeholders=("n", "chi_square", "df", "p_value", "cramers_v", "alpha", "confidence_level"),
        required=("chi_square", "df", "p_value", "cramers_v", "n"),
        direction_field=None,
        sentence_plan=("how many records were analysed",
                       "the test result: chi-square({df}) = {chi_square}, p = {p_value}",
                       "the decision at {alpha}: we reject H0 (independence) / we do not reject H0",
                       "the strength of association as Cramer's V = {cramers_v} in plain words",
                       "that association does not establish causation"),
        limitation={"no_effect_interval": "No confidence interval was computed for Cramer's V in this stage."},
    ),
    "simple_linear_regression": MethodSpec(
        label="simple linear regression (one predictor, with intercept)",
        answers="linear change in a numeric outcome per unit of one numeric predictor",
        roles={"x": "numeric", "y": "numeric"},
        placeholders=("n", "slope", "intercept", "ci_lower", "ci_upper", "t_statistic", "df", "p_value",
                      "r_squared", "alpha", "confidence_level"),
        required=("slope", "ci_lower", "ci_upper", "p_value", "r_squared", "n"),
        direction_field="slope",
        sentence_plan=("how many records were analysed",
                       "the estimated slope = {slope} (change in y per one unit of x) with its "
                       "{confidence_level} CI, t({df}) = {t_statistic}, p = {p_value}",
                       "the decision at {alpha}: we reject H0 (slope = {null_value}) / we do not reject H0",
                       "R-squared = {r_squared} as the share of variation in y explained by x",
                       "that the slope describes an association, not the effect of changing x"),
        limitation={"no_extrapolation": "The slope describes the linear association within the observed range of "
                                        "the predictor and should not be extrapolated beyond it."},
    ),
}

NO_METHOD = "no_supported_method"


def format_p(p: float) -> str:
    """4 decimals, but never let rounding print a value on the wrong side of alpha (e.g. 0.04996)."""
    if p < 0.0001:
        return "< 0.0001"
    for digits in (4, 6, 8, 12, 16):
        text = f"{p:.{digits}f}"
        if p == ALPHA or (float(text) < ALPHA) == (p < ALPHA) and float(text) != ALPHA:
            return text
    return repr(p)


def hypotheses(method: str, roles: dict, group_labels: list | None) -> str:
    if method == "welch_t_test":
        g1, g2 = group_labels
        return (f"H0: Δ = 0 versus H1: Δ ≠ 0, where Δ = μ({roles['group']} = {g1}) − "
                f"μ({roles['group']} = {g2}) for the mean of {roles['outcome']}")
    if method == "pearson_correlation":
        return f"H0: ρ = 0 versus H1: ρ ≠ 0 (population Pearson correlation of {roles['x']} and {roles['y']})"
    if method == "chi_square_independence":
        return f"H0: {roles['x']} and {roles['y']} are independent versus H1: they are associated"
    return f"H0: β1 = 0 versus H1: β1 ≠ 0 (slope of {roles['y']} on {roles['x']})"


def protected_values(method: str, r: dict, conf_level: float) -> dict:
    """Format the stored statistical result into the protected placeholder values (fixed rounding, as text)."""
    values = {"p_value": format_p(r["p_value"]), "alpha": f"{ALPHA:g}", "null_value": "0",
              "confidence_level": f"{100 * conf_level:g}%",
              "decision_claim": "reject" if r["p_value"] < ALPHA else "do not reject",
              "direction_claim": direction_of(method, r)}
    if method == "welch_t_test":
        g1, g2 = r["group_1"], r["group_2"]
        values |= {"group_1": g1["label"], "group_2": g2["label"],
                   "n_group_1": str(g1["n"]), "n_group_2": str(g2["n"]),
                   "mean_group_1": f"{g1['mean']:.2f}", "mean_group_2": f"{g2['mean']:.2f}",
                   "sd_group_1": f"{g1['sd']:.2f}", "sd_group_2": f"{g2['sd']:.2f}",
                   "mean_difference": f"{r['mean_difference']:.2f}",
                   "ci_lower": f"{r['ci_lower']:.2f}", "ci_upper": f"{r['ci_upper']:.2f}",
                   "t_statistic": f"{r['t_statistic']:.3f}", "df": f"{r['df']:.2f}",
                   "n_included": str(r["n_included"])}
    elif method == "pearson_correlation":
        values |= {"n": str(r["n"]), "r": f"{r['r']:.3f}", "ci_lower": f"{r['ci_lower']:.3f}",
                   "ci_upper": f"{r['ci_upper']:.3f}", "t_statistic": ("undefined at exact correlation" if r["t_statistic"] is None else f"{r['t_statistic']:.3f}"),
                   "df": f"{r['df']:g}"}
    elif method == "chi_square_independence":
        values |= {"n": str(r["n"]), "chi_square": f"{r['chi_square']:.3f}", "df": f"{r['df']:g}",
                   "cramers_v": f"{r['cramers_v']:.3f}"}
    else:
        values |= {"n": str(r["n"]), "slope": f"{r['slope']:.3f}", "intercept": f"{r['intercept']:.3f}",
                   "ci_lower": f"{r['ci_lower']:.3f}", "ci_upper": f"{r['ci_upper']:.3f}",
                   "t_statistic": f"{r['t_statistic']:.3f}", "df": f"{r['df']:g}",
                   "r_squared": f"{r['r_squared']:.3f}"}
    return values


def direction_of(method: str, r: dict) -> str:
    """'positive' / 'negative' / 'zero' from the sign of the method's direction field, or 'not_applicable'."""
    key = METHODS[method].direction_field
    if key is None:
        return "not_applicable"
    value = r[key]
    return "positive" if value > 0 else "negative" if value < 0 else "zero"
