"""Small, inspectable lexical retriever over curated statistical method cards.

This is document retrieval, not a summary of a CSV and not vector search. Cards
are project-authored notes with primary-source links; they cannot change policy.
"""
from __future__ import annotations

import re


METHOD_CARDS = (
    {"id": "independent-means", "title": "Comparing two independent means",
     "method": "welch_t_test", "keywords": "mean compare difference group independent score 平均 差异 两组",
     "text": "Use a numeric outcome and two independent groups. Welch allows unequal variances. "
             "The estimand is a difference in population means, not a causal effect without an appropriate design. "
             "A normality test alone does not select or replace the method.",
     "source": "https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.ttest_ind.html"},
    {"id": "paired-means", "title": "Comparing two measurements on the same subjects",
     "method": "paired_t_test", "keywords": "paired same before after drug sleep repeated 配对 同一 前后 睡眠",
     "text": "Each row must contain both measurements on one subject; different pairs must be independent. "
             "Compare the mean within-pair difference y minus x. The relevant distribution is the differences. "
             "Do not treat the two measurements as independent groups or silently remove incomplete pairs.",
     "source": "https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.ttest_rel.html"},
    {"id": "linear-association", "title": "Pearson linear association",
     "method": "pearson_correlation", "keywords": "correlation association pearson linear numeric 相关 关联",
     "text": "Use two numeric variables to estimate linear association. Correlation does not establish causation; "
             "a weak coefficient does not rule out a nonlinear relationship. Do not use it as a substitute for a requested mean difference.",
     "source": "https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.pearsonr.html"},
    {"id": "categorical-association", "title": "Association in a contingency table",
     "method": "chi_square_independence", "keywords": "categorical sex admission department survival table 录取 性别 分类",
     "text": "Use two categorical variables and inspect expected counts before chi-square inference. "
             "This project requires no expected count below one and at most a fifth below five. "
             "Pooled associations can differ from patterns within strata; do not imply causal discrimination from a pooled table.",
     "source": "https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.chi2_contingency.html"},
    {"id": "sparse-two-by-two", "title": "Exact inference for a two by two table",
     "method": "fisher_exact", "keywords": "fisher exact sparse small table categorical 精确 稀疏 小样本",
     "text": "Fisher's two-sided exact test supports a two by two categorical table with small expected counts. "
             "State row and column order for the sample odds ratio. Zero cells can produce an infinite or undefined ratio. "
             "An odds ratio is not a ratio of probabilities. Switching from chi-square requires a new explicit plan, not a silent fallback.",
     "source": "https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.fisher_exact.html"},
    {"id": "simple-regression", "title": "Simple ordinary least squares",
     "method": "simple_linear_regression", "keywords": "regression slope predict outcome predictor ols 回归 预测 斜率",
     "text": "Explicitly identify one numeric predictor x and outcome y. A fitted slope describes a linear association. "
             "The current ordinary OLS inference is not automatically made robust after a heteroscedasticity warning. "
             "Do not replace an adjusted or multivariable question with several unadjusted regressions.",
     "source": "https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.linregress.html"},
)


def retrieve_method_cards(question: str, limit: int = 3) -> list[dict]:
    """Rank a real local text corpus, returning excerpts and source provenance."""
    query = question.casefold()
    words = set(re.findall(r"[a-z_]+", query))
    scored = []
    for index, card in enumerate(METHOD_CARDS):
        terms = card["keywords"].casefold().split()
        score = sum(1 for term in terms if term in words or (not term.isascii() and term in query))
        scored.append((score, -index, card))
    return [{**card, "retrieval_score": score, "retriever": "local_lexical_method_cards_v1"}
            for score, _, card in sorted(scored, key=lambda item: item[:2], reverse=True) if score > 0][:limit]
