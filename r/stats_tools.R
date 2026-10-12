# =============================================================================
# stats_tools.R  --  R statistical tools called by the LangGraph workflow
#
# The Python notebook calls this script through Rscript (not through RStudio):
#
#   Rscript stats_tools.R <task> <request.json> <result.json>
#
#   task = "summary"      shared descriptive summary for BOTH diagnostic branches
#          "diagnostics"  rule-based data checks (missingness, types, ranges,
#                         labels, duplicate IDs, group sizes, variation, flags)
#          "welch_test"   two-sided Welch independent-samples t-test
#
# request.json (written by Python) contains:
#   data_path     path of the CSV for the current data version
#   data_version  label of that version, echoed back so Python can check it
#   excluded_ids  record IDs excluded by a user-confirmed decision (may be empty)
#   score_min, score_max, group_labels, alpha
#
# result.json (read back by Python) contains the structured results.
# This script never edits, drops or imputes data on its own. Only the
# excluded_ids passed in (each one backed by a user confirmation and a log
# entry on the Python side) are left out of the analysis set.
# =============================================================================

suppressWarnings(suppressPackageStartupMessages(library(jsonlite)))

args <- commandArgs(trailingOnly = TRUE)
if (length(args) != 3) {
  stop("Usage: Rscript stats_tools.R <summary|diagnostics|welch_test> <request.json> <result.json>")
}
task     <- args[1]
req      <- fromJSON(args[2], simplifyVector = TRUE)
out_path <- args[3]

REQUIRED_COLUMNS <- c("student_id", "tutoring", "score")
score_min    <- as.numeric(req$score_min)
score_max    <- as.numeric(req$score_max)
group_labels <- as.character(unlist(req$group_labels))   # e.g. c("yes", "no")
excluded_ids <- as.character(unlist(req$excluded_ids))
alpha        <- as.numeric(req$alpha)

# Keep vectors as JSON arrays even when they have length 0 or 1.
as_array <- function(x) I(as.character(x))

# ---------------------------------------------------------------------------
# Read the CSV with every column as text, so problems such as "yes " (trailing
# space) or "abc" in a numeric column stay visible instead of being silently
# converted.
# ---------------------------------------------------------------------------
raw <- read.csv(req$data_path, colClasses = "character", na.strings = character(0),
                strip.white = FALSE, check.names = FALSE)

missing_columns <- setdiff(REQUIRED_COLUMNS, names(raw))
is_blank <- function(x) is.na(x) | x == "" | x == "NA"

base_info <- list(
  task = task,
  data_version = req$data_version,
  data_path = req$data_path,
  n_rows_in_file = nrow(raw),
  columns_found = as_array(names(raw)),
  missing_required_columns = as_array(missing_columns),
  excluded_ids = as_array(excluded_ids),
  r_version = R.version.string
)

write_result <- function(result) {
  write_json(c(base_info, result), out_path, auto_unbox = TRUE, digits = NA,
             na = "null", null = "null", pretty = TRUE)
}

# If a required column is absent, no task can run: report it and stop here.
if (length(missing_columns) > 0) {
  write_result(list(status = "missing_required_columns"))
  quit(save = "no", status = 0)
}

# Analysis set = all rows except the user-confirmed exclusions.
d <- raw[!(raw$student_id %in% excluded_ids), REQUIRED_COLUMNS]
score_text <- d$score
score_num  <- suppressWarnings(as.numeric(score_text))

group_stats <- function(values) {
  values <- values[is.finite(values)]
  list(n = length(values),
       mean = if (length(values) > 0) mean(values) else NA,
       sd = if (length(values) > 1) sd(values) else NA,
       median = if (length(values) > 0) median(values) else NA,
       min = if (length(values) > 0) min(values) else NA,
       max = if (length(values) > 0) max(values) else NA)
}

# ===========================================================================
# Task 1: shared summary (descriptive only, no pass/fail verdicts).
# Both diagnostic branches receive this same summary for the same data version.
# ===========================================================================
if (task == "summary") {
  label_counts <- table(d$tutoring, useNA = "no")
  finite_scores <- score_num[is.finite(score_num)]
  per_label <- lapply(names(label_counts), function(lab) {
    c(list(label_as_written = lab), group_stats(score_num[d$tutoring == lab]))
  })
  write_result(list(
    status = "ok",
    n_rows_in_analysis_set = nrow(d),
    # Labels are reported exactly as written, so "yes" and "yes " stay distinct.
    tutoring_label_counts = lapply(names(label_counts), function(lab)
      list(label_as_written = lab, quoted = paste0("\"", lab, "\""), n = as.integer(label_counts[[lab]]))),
    score_blank_count = sum(is_blank(score_text)),
    score_parseable_count = sum(!is.na(score_num)),
    score_quantiles = if (length(finite_scores) > 0)
      as.list(setNames(quantile(finite_scores, c(0, .05, .25, .5, .75, .95, 1), names = FALSE),
                       c("min", "p05", "p25", "p50", "p75", "p95", "max"))) else NULL,
    score_by_label_as_written = per_label,
    stated_score_range = list(min = score_min, max = score_max)
  ))
  quit(save = "no", status = 0)
}

# ===========================================================================
# Task 2: rule-based diagnostics.
# Each finding has: record_id, field, value_as_written, check, severity.
#   severity "blocking"     -> the test cannot run until the user resolves it
#   severity "verify"       -> plausible but unusual; the user should confirm it
#   severity "out_of_scope" -> the requested analysis cannot be done with this data
# ===========================================================================
if (task == "diagnostics") {
  findings <- list()
  add_finding <- function(ids, field, values, check, severity, detail) {
    for (i in seq_along(ids)) {
      findings[[length(findings) + 1]] <<- list(
        record_id = ids[i], field = field, value_as_written = values[i],
        check = check, severity = severity,
        detail = if (length(detail) > 1) detail[i] else detail)
    }
  }

  id_blank <- is_blank(d$student_id)
  add_finding(rep("(row without ID)", sum(id_blank)), "student_id", d$student_id[id_blank],
              "missing_id", "blocking", "student_id is empty")

  dup <- !id_blank & (duplicated(d$student_id) | duplicated(d$student_id, fromLast = TRUE))
  dup_count <- vapply(d$student_id[dup], function(id) sum(d$student_id == id), integer(1))
  add_finding(d$student_id[dup], "student_id", d$student_id[dup], "duplicate_id", "blocking",
              sprintf("student_id appears in %d rows; 'exclude' removes all rows with this ID", dup_count))

  lab_blank <- is_blank(d$tutoring)
  add_finding(d$student_id[lab_blank], "tutoring", d$tutoring[lab_blank],
              "missing_label", "blocking", "tutoring label is empty")

  lab_bad <- !lab_blank & !(d$tutoring %in% group_labels)
  hint <- ifelse(tolower(trimws(d$tutoring[lab_bad])) %in% group_labels,
                 "label matches a valid label only after trimming spaces / changing case",
                 "label is not one of the valid labels")
  add_finding(d$student_id[lab_bad], "tutoring", d$tutoring[lab_bad],
              "invalid_label", "blocking", hint)

  sc_blank <- is_blank(score_text)
  add_finding(d$student_id[sc_blank], "score", score_text[sc_blank],
              "missing_score", "blocking", "score is missing")

  sc_nonnum <- !sc_blank & is.na(score_num)
  add_finding(d$student_id[sc_nonnum], "score", score_text[sc_nonnum],
              "non_numeric_score", "blocking", "score is not a number")

  sc_nonfinite <- !sc_blank & !is.na(score_num) & !is.finite(score_num)
  add_finding(d$student_id[sc_nonfinite], "score", score_text[sc_nonfinite],
              "non_finite_score", "blocking", "score is infinite")

  sc_range <- is.finite(score_num) & (score_num < score_min | score_num > score_max)
  add_finding(d$student_id[sc_range], "score", score_text[sc_range], "out_of_range", "blocking",
              sprintf("score is outside the stated %g-%g range", score_min, score_max))

  # Rows that pass every record-level check form the usable analysis rows.
  usable <- !id_blank & !dup & (d$tutoring %in% group_labels) &
            is.finite(score_num) & !sc_range

  # Boxplot rule, per group, on usable rows: flag for verification, never drop.
  for (g in group_labels) {
    in_g <- usable & d$tutoring == g
    if (sum(in_g) >= 4) {
      out_vals <- boxplot.stats(score_num[in_g])$out
      flag <- in_g & score_num %in% out_vals
      add_finding(d$student_id[flag], "score", score_text[flag], "boxplot_flag", "verify",
                  sprintf("outside the 1.5*IQR boxplot whiskers of group '%s'", g))
    }
  }

  n_blocking <- sum(vapply(findings, function(f) f$severity == "blocking", logical(1)))

  # Group sizes and variation (needed for a two-group comparison of means).
  # These group-level verdicts are issued only once no record-level problem is
  # open: e.g. if every label is written "Yes", the user must first be asked
  # about the labels instead of the run stopping with "group 'yes' is empty".
  group_info <- lapply(group_labels, function(g) c(list(group = g), group_stats(score_num[usable & d$tutoring == g])))
  names(group_info) <- group_labels
  group_findings <- list()
  for (g in group_labels) {
    gi <- group_info[[g]]
    if (n_blocking > 0) next
    if (gi$n < 2) {
      group_findings[[length(group_findings) + 1]] <- list(
        group = g, check = "group_too_small", severity = "out_of_scope",
        detail = sprintf("group '%s' has %d usable scores; at least 2 are needed", g, gi$n))
    } else if (is.na(gi$sd) || gi$sd == 0) {
      group_findings[[length(group_findings) + 1]] <- list(
        group = g, check = "no_variation", severity = "out_of_scope",
        detail = sprintf("group '%s' has no variation in scores", g))
    }
  }

  # Formal distribution checks run only after invalid values are resolved
  # (case-study Step 2). They are information for the analyst, not a switch
  # that picks the method.
  distribution_checks <- NULL
  if (n_blocking == 0 && length(group_findings) == 0) {
    distribution_checks <- lapply(group_labels, function(g) {
      x <- score_num[usable & d$tutoring == g]
      p <- if (length(x) >= 3 && length(x) <= 5000) shapiro.test(x)$p.value else NA
      list(group = g, n = length(x), shapiro_wilk_p = p,
           note = "A large p-value does not prove normality; a small one does not by itself rule out Welch's test.")
    })
  }

  write_result(list(
    status = "ok",
    n_rows_in_analysis_set = nrow(d),
    n_usable_rows = sum(usable),
    findings = findings,
    group_info = unname(group_info),
    group_findings = group_findings,
    n_blocking = n_blocking,
    n_verify = sum(vapply(findings, function(f) f$severity == "verify", logical(1))),
    distribution_checks = distribution_checks,
    distribution_checks_note = if (is.null(distribution_checks))
      "Deferred: formal distribution checks run after invalid values are corrected." else
      "Shapiro-Wilk results are descriptive diagnostics only."
  ))
  quit(save = "no", status = 0)
}

# ===========================================================================
# Task 3: two-sided Welch independent-samples t-test.
# Refuses to run if any record-level problem remains in the analysis set.
# ===========================================================================
if (task == "welch_test") {
  bad <- is_blank(d$student_id) | duplicated(d$student_id) | !(d$tutoring %in% group_labels) |
         !is.finite(score_num) | score_num < score_min | score_num > score_max
  if (any(bad)) {
    write_result(list(status = "blocked",
                      reason = "Unresolved record-level problems remain; the test was not run.",
                      problem_ids = as_array(d$student_id[bad])))
    quit(save = "no", status = 0)
  }
  g1 <- group_labels[1]; g2 <- group_labels[2]   # g1 = "yes" (tutoring), g2 = "no"
  x1 <- score_num[d$tutoring == g1]
  x2 <- score_num[d$tutoring == g2]
  tt <- t.test(x1, x2, alternative = "two.sided", var.equal = FALSE, conf.level = 1 - alpha)
  write_result(list(
    status = "ok",
    method = tt$method,
    alternative = tt$alternative,
    var_equal = FALSE,
    conf_level = 1 - alpha,
    alpha = alpha,
    group_1 = c(list(label = g1), group_stats(x1)),
    group_2 = c(list(label = g2), group_stats(x2)),
    mean_difference = unname(mean(x1) - mean(x2)),   # Delta-hat = mean(g1) - mean(g2)
    ci_lower = tt$conf.int[1],
    ci_upper = tt$conf.int[2],
    t_statistic = unname(tt$statistic),
    df = unname(tt$parameter),
    p_value = tt$p.value,
    n_included = length(x1) + length(x2),
    r_call = sprintf("t.test(score[tutoring == '%s'], score[tutoring == '%s'], alternative = 'two.sided', var.equal = FALSE, conf.level = %g)",
                     g1, g2, 1 - alpha)
  ))
  quit(save = "no", status = 0)
}

stop(sprintf("Unknown task '%s'", task))
