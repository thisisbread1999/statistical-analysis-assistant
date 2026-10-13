"""Structured outputs exchanged between the agents and the program (Pydantic models).

Plain str fields with "" for "not used" are deliberate: they work the same way with OpenAI, Anthropic and
local Ollama models' JSON-schema output, which do not all handle optional / null fields reliably.
"""
from typing import Literal

from pydantic import BaseModel, Field

MethodName = Literal["welch_t_test", "pearson_correlation", "chi_square_independence",
                     "simple_linear_regression", "no_supported_method"]


class AnalysisPlan(BaseModel):
    method: MethodName = Field(description="One of supported_methods, or no_supported_method")
    outcome: str = Field(description="Welch only: numeric outcome column; otherwise ''")
    group: str = Field(description="Welch only: two-level group column; otherwise ''")
    group_1_label: str = Field(description="Welch only: label of group 1 (Δ = group 1 minus group 2); otherwise ''")
    group_2_label: str = Field(description="Welch only: label of group 2; otherwise ''")
    x: str = Field(description="Correlation/chi-square: first variable; regression: predictor; Welch: ''")
    y: str = Field(description="Correlation/chi-square: second variable; regression: outcome; Welch: ''")
    target_parameter: str
    null_hypothesis: str
    alternative_hypothesis: str
    method_rationale: str
    design_notes: list[str] = Field(description="Design facts that limit interpretation")


class DiagnosticIssue(BaseModel):
    topic: Literal["variable_meaning", "study_design", "goal_alignment", "distribution", "other"]
    severity: Literal["note", "limitation", "out_of_scope"] = Field(
        description="out_of_scope ONLY if the planned test cannot validly answer the question "
                    "(e.g. paired or clustered data, wrong variable types); non-random groups are a limitation")
    issue: str
    evidence: str
    suggested_action: str


class LLMDiagnosticReport(BaseModel):
    variable_meanings: str
    design_assessment: str
    goal_alignment: str
    distribution_notes: str
    issues: list[DiagnosticIssue]


class ClarificationQuestion(BaseModel):
    request_id: str
    question: str


class MergeAssessment(BaseModel):
    rationale: str = Field(description="Why the analysis proceeds, pauses for clarification, or stops")
    limitations: list[str] = Field(description="Limitations to carry into the report")
    questions: list[ClarificationQuestion] = Field(description="One question per open request_id (empty if none)")


class LimitationText(BaseModel):
    limitation_id: str = Field(description="One of the required_limitations ids")
    text: str = Field(description="Plain words; no digits")


class ReportDraft(BaseModel):
    interpretation: str = Field(description="One paragraph. Numbers ONLY as {placeholder} names; no digits")
    limitations: list[LimitationText]
    direction_claim: Literal["positive", "negative", "zero", "not_applicable"] = Field(
        description="Sign of the estimate (group 1 minus group 2, r, or slope); not_applicable for chi-square")
    decision_claim: Literal["reject_H0", "do_not_reject_H0"]


class ReviewIssue(BaseModel):
    severity: Literal["critical", "minor"]
    category: Literal["causal_claim", "numeric_mismatch", "contradiction", "missing_result",
                      "missing_limitation", "unsupported_claim", "overstatement", "other"]
    offending_sentence: str
    evidence: str
    suggested_correction: str


class ReviewVerdict(BaseModel):
    passed: bool = Field(description="True only if there is no critical issue")
    issues: list[ReviewIssue]
    summary: str


class FollowupDecision(BaseModel):
    kind: Literal["change_confidence_level", "re_explain", "new_question", "unsupported"] = Field(
        description="change_confidence_level: same analysis, another CI level; re_explain: explain the existing "
                    "result again (e.g. simpler words, answer a question about it); new_question: a different "
                    "analysis; unsupported: cannot be answered by the supported methods")
    confidence_level: float = Field(description="For change_confidence_level, e.g. 0.99; otherwise 0")
    focus: str = Field(description="What the user wants explained or changed, in one sentence")
    rationale: str
