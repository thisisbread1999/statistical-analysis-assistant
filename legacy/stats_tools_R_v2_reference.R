# =============================================================================
# stats_tools.R  --  R statistical tools called by the LangGraph workflow (v2)
#
# The Python workflow calls this script through Rscript (not through RStudio):
#
#   Rscript stats_tools.R <task> <request.json> <result.json>
#
#   task = "summary"      shared descriptive summary (no verdicts) for BOTH
#                         diagnostic branches
#          "diagnostics"  rule-based checks: record level (IDs, missing /
#                         non-numeric / non-finite / out-of-range values,
#                         labels, boxplot flags), then method requirements,
#                         then descriptive distribution checks
#          "run_test"     the planned test, one of four methods:
#                           welch_t_test              t.test(var.equal = FALSE)
#                           pearson_correlation       cor.test(method = "pearson")
#                           chi_square_independence   chisq.test(table(x, y))
#                           simple_linear_regression  lm(y ~ x) + confint()
#          "welch_test"   v1 task name, kept as an alias of run_test with
#                         method = welch_t_test (the v1 notebook uses it)
#
# The interface is specified in docs/R_TOOLS_SPEC.md. request.json (written by
# Python) contains:
#   data_path      path of the CSV for the current data version
#   data_version   label of that version, echoed back so Python can check it
#   excluded_ids   record IDs excluded by a user-confirmed decision (may be empty)
#   id_column      record identifier column, or null (record IDs are then
#                  "row N" = N-th data row of the file)
#   method, roles  the method and the columns it uses (outcome/group or x/y)
#   group_labels   Welch only: [group_1, group_2]; difference = group_1 - group_2
#   valid_ranges   optional, stated by the user: {column: [min, max]}
#   valid_levels   optional, stated by the user: {column: [level, ...]}
#   conf_level     confidence level of intervals (default 0.95 if absent)
#   alpha          significance level, only used to report the decision
#                  (default 0.05 if absent)
#
# v1 requests: a request without "roles" (fields score_min, score_max,
# group_labels, alpha) is still accepted. It is read as a Welch request on the
# columns student_id / tutoring / score with valid_ranges = {score: [score_min,
# score_max]}, valid_levels = {tutoring: group_labels}, conf_level = 1 - alpha,
# and the result also carries the v1 field names (missing_score, ...,
# tutoring_label_counts, score_quantiles, group_findings).
#
# result.json (read back by Python) contains the structured results.
# Principles:
#   * This script never edits, drops or imputes data on its own. The only rows
#     left out of the analysis set are those in excluded_ids (each one backed
#     by a user confirmation and a correction-log entry on the Python side).
#     Problems are reported, never silently fixed.
#   * Every column is read as text, so "yes " (trailing space) or "abc" in a
#     numeric column stay visible as written.
#   * Exit status 0 whenever a result could be written. Expected problems go in
#     "status": "missing_required_columns", "unsupported_request" (bad or
#     incomplete request; see "problems"), "blocked" (run_test with unresolved
#     record-level problems) and "out_of_scope" (run_test when the data do not
#     meet the method's requirements). A non-zero exit is a genuine failure
#     (e.g. the data file does not exist); R's message then goes to stderr.
#   * JSON arrays stay arrays, also with 0 or 1 element.
# =============================================================================

suppressWarnings(suppressPackageStartupMessages(library(jsonlite)))

TASKS <- c("summary", "diagnostics", "run_test", "welch_test")

# Variable roles of each supported method and the type each role must have.
METHOD_ROLES <- list(
  welch_t_test             = c(outcome = "numeric", group = "categorical"),
  pearson_correlation      = c(x = "numeric", y = "numeric"),
  chi_square_independence  = c(x = "categorical", y = "categorical"),
  simple_linear_regression = c(x = "numeric", y = "numeric")   # x = predictor, y = outcome
)
MIN_N_BOXPLOT <- 4      # the boxplot rule is applied only to at least 4 values
SHAPIRO_N     <- c(3, 5000)

args <- commandArgs(trailingOnly = TRUE)
if (length(args) != 3) {
  stop("Usage: Rscript stats_tools.R <summary|diagnostics|run_test> <request.json> <result.json>")
}
task     <- args[1]
req      <- fromJSON(args[2], simplifyVector = TRUE)
out_path <- args[3]

# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------
as_array   <- function(x) I(as.character(x))     # text vector that stays a JSON array
is_blank   <- function(x) is.na(x) | trimws(x) == "" | x == "NA"
quoted     <- function(x) paste0("\"", x, "\"")
norm_label <- function(x) tolower(gsub("[[:space:]]+", "", x))   # ignore spaces and case
sort_text  <- function(x) sort(unique(x), method = "radix")      # locale-independent order
num_text   <- function(x) format(x, digits = 15)
r_name     <- function(x) if (identical(make.names(x), x)) x else paste0("`", x, "`")
is_text1   <- function(x) is.character(x) && length(x) == 1 && !is.na(x) && nzchar(x)
is_prob    <- function(x) is.numeric(x) && length(x) == 1 && is.finite(x) && x > 0 && x < 1
or_default <- function(x, default) if (is.null(x)) default else x
listing    <- function(x) if (length(x) == 0) "(none)" else paste(quoted(x), collapse = ", ")

group_stats <- function(values) {
  values <- values[is.finite(values)]
  list(n = length(values),
       mean = if (length(values) > 0) mean(values) else NA,
       sd = if (length(values) > 1) sd(values) else NA,
       median = if (length(values) > 0) median(values) else NA,
       min = if (length(values) > 0) min(values) else NA,
       max = if (length(values) > 0) max(values) else NA)
}

safe_shapiro <- function(v) {
  if (length(v) < SHAPIRO_N[1] || length(v) > SHAPIRO_N[2]) return(NA)
  tryCatch(shapiro.test(v)$p.value, error = function(e) NA)
}

# ---------------------------------------------------------------------------
# Read the request. A v1 request (no "roles") is translated into a v2 request.
# ---------------------------------------------------------------------------
request_format <- if (is.null(req$roles)) "v1" else "v2"
excluded_ids   <- as.character(unlist(req$excluded_ids))
group_labels   <- as.character(unlist(req$group_labels))
alpha          <- or_default(req$alpha, 0.05)
if (request_format == "v1") {
  method       <- "welch_t_test"
  roles        <- list(outcome = "score", group = "tutoring")
  id_column    <- "student_id"
  valid_ranges <- if (!is.null(req$score_min) && !is.null(req$score_max))
                    list(score = c(req$score_min, req$score_max)) else list()
  valid_levels <- list(tutoring = group_labels)
  conf_level   <- or_default(req$conf_level, if (is_prob(alpha)) 1 - alpha else 0.95)
} else {
  method       <- req$method
  roles        <- req$roles
  id_column    <- req$id_column
  valid_ranges <- or_default(req$valid_ranges, list())
  valid_levels <- or_default(req$valid_levels, list())
  conf_level   <- or_default(req$conf_level, 0.95)
}
if (task == "welch_test" && is.null(method)) method <- "welch_t_test"

# ---------------------------------------------------------------------------
# Check the request itself. Problems are reported as status
# "unsupported_request"; nothing is computed then.
# ---------------------------------------------------------------------------
problems <- character(0)
problem  <- function(...) problems <<- c(problems, sprintf(...))

if (!(task %in% TASKS)) problem("unknown task '%s'; use summary, diagnostics or run_test", task)
if (!is_text1(req$data_path)) problem("data_path must be the path of a CSV file")
method_ok <- is_text1(method) && method %in% names(METHOD_ROLES)
if (!method_ok) {
  problem("method must be one of: %s", paste(names(METHOD_ROLES), collapse = ", "))
} else if (task == "welch_test" && method != "welch_t_test") {
  problem("task welch_test runs only method welch_t_test (requested: %s); use run_test", method)
}
if (!is.null(id_column) && !is_text1(id_column)) problem("id_column must be a column name or null")
if (!is_prob(conf_level)) problem("conf_level must be a number between 0 and 1, e.g. 0.95")
if (!is_prob(alpha)) problem("alpha must be a number between 0 and 1, e.g. 0.05")

role_types <- if (method_ok) METHOD_ROLES[[method]] else character(0)
roles_ok   <- FALSE
if (method_ok) {
  if (!is.list(roles) || is.null(names(roles))) {
    problem("roles must be an object such as {\"%s\": \"<column>\", ...}", names(role_types)[1])
  } else {
    for (role in names(role_types)) {
      if (!is_text1(roles[[role]]))
        problem("roles.%s must name a %s column for %s", role, role_types[[role]], method)
    }
    roles_ok <- !any(vapply(names(role_types), function(r) !is_text1(roles[[r]]), logical(1)))
  }
}
role_cols <- if (roles_ok) vapply(names(role_types), function(r) roles[[r]], character(1)) else character(0)
if (roles_ok) {
  if (anyDuplicated(role_cols)) problem("each role must name a different column")
  if (is_text1(id_column) && id_column %in% role_cols) problem("id_column cannot also be a role column")
}
if (method_ok && method == "welch_t_test") {
  if (length(group_labels) != 2 || any(is_blank(group_labels)) ||
      anyDuplicated(norm_label(group_labels))) {
    problem("group_labels must be two different labels [group_1, group_2]")
  } else if (roles_ok && !is.null(valid_levels[[roles$group]]) &&
             !all(group_labels %in% valid_levels[[roles$group]])) {
    problem("group_labels %s are not all among valid_levels.%s", listing(group_labels), roles$group)
  }
}
if (!is.list(valid_ranges) || (length(valid_ranges) > 0 && is.null(names(valid_ranges)))) {
  problem("valid_ranges must be an object {column: [min, max]}")
  valid_ranges <- list()
} else {
  for (col in names(valid_ranges)) {
    r <- valid_ranges[[col]]
    if (!is.numeric(r) || length(r) != 2 || any(!is.finite(r)) || r[1] > r[2])
      problem("valid_ranges.%s must be [min, max] with min <= max", col)
  }
}
if (!is.list(valid_levels) || (length(valid_levels) > 0 && is.null(names(valid_levels)))) {
  problem("valid_levels must be an object {column: [level, ...]}")
  valid_levels <- list()
} else {
  for (col in names(valid_levels)) {
    lv <- valid_levels[[col]]
    if (!is.character(lv) || length(lv) == 0 || any(is_blank(lv)))
      problem("valid_levels.%s must be a non-empty list of labels", col)
  }
}

# ---------------------------------------------------------------------------
# Read the CSV with every column as text, so problems such as "yes " (trailing
# space) or "abc" in a numeric column stay visible instead of being silently
# converted. A missing file is a genuine failure (non-zero exit).
# ---------------------------------------------------------------------------
raw <- NULL
if (is_text1(req$data_path)) {
  if (!file.exists(req$data_path)) stop(sprintf("data file not found: %s", req$data_path), call. = FALSE)
  raw <- read.csv(req$data_path, colClasses = "character", na.strings = character(0),
                  strip.white = FALSE, check.names = FALSE)
  if (ncol(raw) > 0) names(raw)[1] <- sub("^﻿", "", names(raw)[1])   # UTF-8 byte-order mark
}

request_ok <- length(problems) == 0
required_columns <- unique(c(if (is_text1(id_column)) id_column, unname(role_cols)))
missing_columns  <- if (request_ok && !is.null(raw)) setdiff(required_columns, names(raw)) else character(0)

# Notes about parts of the request that could not be applied (not errors).
request_warnings <- character(0)
if (request_ok && !is.null(raw)) {
  for (col in names(valid_ranges)) {
    if (!(col %in% names(raw))) {
      request_warnings <- c(request_warnings, sprintf("valid_ranges names column '%s', which is not in the file; no range check was applied to it", col))
    } else if (col %in% role_cols && role_types[match(col, role_cols)] != "numeric") {
      request_warnings <- c(request_warnings, sprintf("valid_ranges.%s was not applied: '%s' is a categorical role here", col, col))
    }
  }
  for (col in names(valid_levels)) {
    if (!(col %in% names(raw))) {
      request_warnings <- c(request_warnings, sprintf("valid_levels names column '%s', which is not in the file; no label check was applied to it", col))
    } else if (col %in% role_cols && role_types[match(col, role_cols)] != "categorical") {
      request_warnings <- c(request_warnings, sprintf("valid_levels.%s was not applied: '%s' is a numeric role here", col, col))
    }
  }
}

base_info <- list(
  task = task,
  data_version = req$data_version,
  data_path = req$data_path,
  method = if (is_text1(method)) method else NULL,
  request_format = request_format,
  n_rows_in_file = if (!is.null(raw)) nrow(raw) else NULL,
  columns_found = as_array(if (!is.null(raw)) names(raw) else character(0)),
  missing_required_columns = as_array(missing_columns),
  excluded_ids = as_array(excluded_ids),
  request_warnings = as_array(request_warnings),
  r_version = R.version.string
)

write_result <- function(result) {
  write_json(c(base_info, result), out_path, auto_unbox = TRUE, digits = NA,
             na = "null", null = "null", pretty = TRUE)
  quit(save = "no", status = 0)
}

if (!request_ok) {
  write_result(list(status = "unsupported_request",
                    reason = "The request is incomplete or not supported; nothing was computed.",
                    problems = as_array(problems)))
}

# If a required column is absent, no task can run: report it and stop here.
if (length(missing_columns) > 0) write_result(list(status = "missing_required_columns"))

# ---------------------------------------------------------------------------
# Record IDs and the analysis set (= all rows except user-confirmed exclusions).
# Without an id_column, or where the ID is empty, a record is "row N".
# ---------------------------------------------------------------------------
row_label <- paste("row", seq_len(nrow(raw)))
record_id <- if (is_text1(id_column)) ifelse(is_blank(raw[[id_column]]), row_label, raw[[id_column]]) else row_label
in_set    <- !(record_id %in% excluded_ids)
d         <- raw[in_set, , drop = FALSE]
rid       <- record_id[in_set]
row_no    <- which(in_set)
not_found <- setdiff(excluded_ids, record_id)
if (length(not_found) > 0) {
  base_info$request_warnings <- as_array(c(request_warnings, sprintf(
    "excluded_ids not found in the file: %s", paste(not_found, collapse = ", "))))
}

col_of <- function(role) roles[[role]]
if (method == "welch_t_test") { outcome_col <- col_of("outcome"); group_col <- col_of("group") }

# v1 requests keep the v1 check names for the score column.
check_name <- function(check) {
  if (request_format == "v1" && check %in% c("missing_value", "non_numeric_value", "non_finite_value"))
    sub("_value$", "_score", check) else check
}

# ===========================================================================
# Record-level checks, shared by "diagnostics" and "run_test".
# Each finding: record_id, field, value_as_written, check, severity, detail.
#   severity "blocking" -> the test cannot run until the user resolves it
#   severity "verify"   -> plausible but unusual; the user should confirm it
# Returns the findings, the usable rows (rows that pass every blocking check)
# and the parsed role columns.
# ===========================================================================
record_checks <- function() {
  findings <- list()
  add <- function(rows, field, check, severity, detail) {
    idx <- which(rows)
    detail <- rep_len(detail, length(idx))
    for (k in seq_along(idx)) {
      i <- idx[k]
      findings[[length(findings) + 1]] <<- list(
        record_id = rid[i], field = field, value_as_written = d[[field]][i],
        check = check_name(check), severity = severity, detail = detail[k])
    }
  }

  usable <- rep(TRUE, nrow(d))
  if (is_text1(id_column)) {
    ids <- d[[id_column]]
    id_blank <- is_blank(ids)
    add(id_blank, id_column, "missing_id", "blocking",
        sprintf("%s is empty (data row %d)", id_column, row_no[id_blank]))
    dup <- !id_blank & (duplicated(ids) | duplicated(ids, fromLast = TRUE))
    dup_count <- vapply(ids[dup], function(id) sum(ids == id), integer(1))
    add(dup, id_column, "duplicate_id", "blocking",
        sprintf("%s %s appears in %d rows; 'exclude' removes all rows with this ID",
                id_column, quoted(ids[dup]), dup_count))
    usable <- !id_blank & !dup
  }

  num <- list(); lab <- list()
  for (role in names(role_types)) {
    col <- col_of(role)
    x <- d[[col]]
    blank <- is_blank(x)
    if (role_types[[role]] == "numeric") {
      v <- suppressWarnings(as.numeric(x))
      non_numeric <- !blank & is.na(v) & !is.nan(v)
      non_finite  <- !blank & (is.nan(v) | is.infinite(v))
      add(blank, col, "missing_value", "blocking", sprintf("%s is missing", col))
      add(non_numeric, col, "non_numeric_value", "blocking", sprintf("%s is not a number", col))
      add(non_finite, col, "non_finite_value", "blocking", sprintf("%s is not a finite number", col))
      out_of_range <- rep(FALSE, length(v))
      rng <- valid_ranges[[col]]
      if (!is.null(rng)) {
        out_of_range <- is.finite(v) & (v < rng[1] | v > rng[2])
        add(out_of_range, col, "out_of_range", "blocking",
            sprintf("%s is outside the stated range %s to %s", col, num_text(rng[1]), num_text(rng[2])))
      }
      num[[role]] <- v
      usable <- usable & is.finite(v) & !out_of_range
    } else {
      add(blank, col, "missing_label", "blocking", sprintf("%s label is empty", col))
      invalid <- rep(FALSE, length(x))
      detail  <- rep(NA_character_, length(x))
      levels_stated <- valid_levels[[col]]
      if (!is.null(levels_stated)) {
        # Stated levels: a label is invalid if it is not exactly one of them.
        invalid <- !blank & !(x %in% levels_stated)
        m <- match(norm_label(x), norm_label(levels_stated))
        detail <- ifelse(!is.na(m),
          sprintf("label matches the valid level %s only after removing spaces / changing case", quoted(levels_stated[m])),
          sprintf("label is not one of the valid levels %s", listing(levels_stated)))
      } else {
        # No stated levels: a label is invalid only if it differs from another
        # observed label only by spaces / case ("yes" vs "yes " vs "Yes").
        key <- norm_label(x)
        for (k in unique(key[!blank])) {
          members <- which(!blank & key == k)
          forms <- sort_text(x[members])
          if (length(forms) < 2) next
          counts <- vapply(forms, function(f) sum(x[members] == f), integer(1))
          preferred <- if (method == "welch_t_test" && role == "group") intersect(forms, group_labels) else character(0)
          top <- forms[counts == max(counts)]
          reference <- if (length(preferred) == 1) preferred else if (length(top) == 1) top else NA
          for (i in members) {
            if (is.na(reference)) {
              invalid[i] <- TRUE
              detail[i] <- sprintf("labels %s differ only by spaces / case; it is unclear which one is intended", listing(forms))
            } else if (x[i] != reference) {
              invalid[i] <- TRUE
              detail[i] <- sprintf("label differs from the observed label %s (%d rows) only by spaces / case",
                                   quoted(reference), counts[[reference]])
            }
          }
        }
      }
      add(invalid, col, "invalid_label", "blocking", detail[invalid])
      lab[[role]] <- x
      usable <- usable & !blank & !invalid
    }
  }

  # Boxplot rule on usable rows: flag for verification, never drop.
  if (method == "welch_t_test") {
    for (g in group_labels) {
      in_g <- usable & lab$group == g
      if (sum(in_g) >= MIN_N_BOXPLOT) {
        flag <- in_g & num$outcome %in% boxplot.stats(num$outcome[in_g])$out
        add(flag, outcome_col, "boxplot_flag", "verify",
            sprintf("%s is outside the 1.5*IQR boxplot whiskers of group %s = %s", outcome_col, group_col, quoted(g)))
      }
    }
  } else if (method %in% c("pearson_correlation", "simple_linear_regression")) {
    for (role in c("x", "y")) {
      if (sum(usable) >= MIN_N_BOXPLOT) {
        flag <- usable & num[[role]] %in% boxplot.stats(num[[role]][usable])$out
        add(flag, col_of(role), "boxplot_flag", "verify",
            sprintf("%s is outside the 1.5*IQR boxplot whiskers of all usable rows", col_of(role)))
      }
    }
  }

  severity <- vapply(findings, function(f) f$severity, character(1))
  list(findings = findings, usable = usable, num = num, lab = lab,
       n_blocking = sum(severity == "blocking"), n_verify = sum(severity == "verify"),
       blocking_ids = unique(vapply(findings[severity == "blocking"], function(f) f$record_id, character(1))))
}

# Levels of a categorical column in the usable rows: stated order if levels
# were stated, otherwise sorted. Unobserved levels are not included.
observed_levels <- function(values, col) {
  stated <- valid_levels[[col]]
  if (!is.null(stated)) stated[stated %in% values] else sort_text(values)
}

expected_counts <- function(tab) outer(rowSums(tab), colSums(tab)) / sum(tab)

# ===========================================================================
# Method requirements, checked on the usable rows (only when no blocking
# record-level problem is open, so fixable label or value problems are always
# asked about first). Severity "out_of_scope": this method cannot be run on
# these data as they are.
# ===========================================================================
method_checks <- function(rc) {
  out <- list()
  add <- function(check, detail) out[[length(out) + 1]] <<- list(check = check, severity = "out_of_scope", detail = detail)
  u <- rc$usable
  n <- sum(u)
  if (method == "welch_t_test") {
    labels_used <- sort_text(rc$lab$group[u])
    other <- setdiff(labels_used, group_labels)
    if (is.null(valid_levels[[group_col]]) && length(labels_used) != 2) {
      add("wrong_number_of_groups", sprintf(
        "%s has %d distinct label(s) among the usable rows (%s); Welch's test compares exactly 2 groups",
        group_col, length(labels_used), listing(labels_used)))
    } else if (length(other) > 0) {
      add("wrong_number_of_groups", sprintf(
        "%s has usable rows with label(s) %s besides the compared groups %s; Welch's test compares exactly 2 groups and rows are never left out automatically",
        group_col, listing(other), listing(group_labels)))
    }
    for (g in group_labels) {
      v <- rc$num$outcome[u & rc$lab$group == g]
      if (length(v) < 2) {
        add("group_too_small", sprintf("group %s = %s has %d usable rows; at least 2 are needed",
                                       group_col, quoted(g), length(v)))
      } else if (sd(v) == 0) {
        add("no_variation", sprintf("group %s = %s has no variation in %s (SD = 0)", group_col, quoted(g), outcome_col))
      }
    }
  } else if (method %in% c("pearson_correlation", "simple_linear_regression")) {
    n_min <- if (method == "pearson_correlation") 4 else 3
    if (n < n_min) {
      add("too_few_observations", sprintf("%d usable rows; %s needs at least %d", n,
          if (method == "pearson_correlation") "Pearson's correlation with a confidence interval" else "a simple linear regression", n_min))
    }
    check_roles <- if (method == "pearson_correlation") c("x", "y") else "x"
    for (role in check_roles) {
      if (n >= 2 && sd(rc$num[[role]][u]) == 0)
        add("no_variation", sprintf("%s has no variation among the usable rows (SD = 0)", col_of(role)))
    }
  } else if (method == "chi_square_independence") {
    lv <- list()
    for (role in c("x", "y")) {
      lv[[role]] <- observed_levels(rc$lab[[role]][u], col_of(role))
      if (length(lv[[role]]) < 2)
        add("too_few_levels", sprintf("%s has %d level(s) among the usable rows (%s); at least 2 are needed",
                                      col_of(role), length(lv[[role]]), listing(lv[[role]])))
    }
    if (length(out) == 0) {
      e <- expected_counts(table(factor(rc$lab$x[u], lv$x), factor(rc$lab$y[u], lv$y)))
      if (min(e) < 1 || mean(e < 5) > 0.2) {
        add("expected_counts_too_small", sprintf(
          "Cochran's rule is not met: smallest expected count = %.2f and %.0f%% of cells have expected counts below 5 (rule: none below 1 and at most 20%% below 5). Fisher's exact test is not supported in this stage.",
          min(e), 100 * mean(e < 5)))
      }
    }
  }
  out
}

# ===========================================================================
# Distribution checks: descriptive information for the analyst, never a
# switch that changes the method. Run only after record-level problems are
# resolved and the method's requirements are met.
# ===========================================================================
distribution_checks <- function(rc) {
  u <- rc$usable
  if (method == "welch_t_test") {
    lapply(group_labels, function(g) {
      v <- rc$num$outcome[u & rc$lab$group == g]
      list(check = "shapiro_wilk", variable = outcome_col, group = g, n = length(v), shapiro_wilk_p = safe_shapiro(v))
    })
  } else if (method == "pearson_correlation") {
    lapply(c("x", "y"), function(role) {
      v <- rc$num[[role]][u]
      list(check = "shapiro_wilk", variable = col_of(role), role = role, n = length(v), shapiro_wilk_p = safe_shapiro(v))
    })
  } else if (method == "simple_linear_regression") {
    fit <- lm(y ~ x, data = data.frame(x = rc$num$x[u], y = rc$num$y[u]))
    res <- unname(residuals(fit))
    spread <- tryCatch(suppressWarnings(cor.test(abs(res), unname(fitted(fit)), method = "spearman", exact = FALSE)),
                       error = function(e) NULL)
    list(list(check = "shapiro_wilk", variable = "residuals", n = length(res), shapiro_wilk_p = safe_shapiro(res)),
         list(check = "spread_check", variable = "|residual| vs fitted value", method = "spearman",
              n = length(res),
              spearman_rho = if (is.null(spread)) NA else unname(spread$estimate),
              p_value = if (is.null(spread)) NA else spread$p.value))
  } else {
    lx <- observed_levels(rc$lab$x[u], col_of("x"))
    ly <- observed_levels(rc$lab$y[u], col_of("y"))
    e <- expected_counts(table(factor(rc$lab$x[u], lx), factor(rc$lab$y[u], ly)))
    list(list(check = "expected_counts", min_expected_count = min(e),
              share_cells_expected_below_5 = mean(e < 5), n_cells = length(e)))
  }
}

# ===========================================================================
# Task 1: shared summary (descriptive only, no pass/fail verdicts).
# Both diagnostic branches receive this same summary for the same data version.
# ===========================================================================
if (task == "summary") {
  levels_as_written <- function(x) lapply(sort_text(x), function(lab)
    list(label_as_written = lab, quoted = quoted(lab), n = sum(x == lab)))
  quantiles_of <- function(v) {
    v <- v[is.finite(v)]
    if (length(v) == 0) return(NULL)
    as.list(setNames(quantile(v, c(0, .05, .25, .5, .75, .95, 1), names = FALSE),
                     c("min", "p05", "p25", "p50", "p75", "p95", "max")))
  }
  columns <- lapply(names(role_types), function(role) {
    col <- col_of(role)
    x <- d[[col]]
    blank <- is_blank(x)
    v <- suppressWarnings(as.numeric(x))
    info <- list(name = col, role = role, type = role_types[[role]],
                 n_blank = sum(blank),
                 n_parseable_numeric = sum(!blank & (!is.na(v) | is.nan(v))),
                 n_unique_as_written = length(unique(x)))
    if (role_types[[role]] == "categorical") {
      # Labels are reported exactly as written, so "yes" and "yes " stay distinct.
      info$levels_as_written <- levels_as_written(x)
    } else {
      finite <- v[is.finite(v)]
      info$quantiles <- quantiles_of(v)
      info$mean <- if (length(finite) > 0) mean(finite) else NA
      info$sd <- if (length(finite) > 1) sd(finite) else NA
    }
    info
  })
  result <- list(
    status = "ok",
    n_rows_in_analysis_set = nrow(d),
    columns = columns,
    stated_ranges = setNames(lapply(valid_ranges, function(r) I(as.numeric(r))), names(valid_ranges)),
    stated_levels = setNames(lapply(valid_levels, function(l) I(as.character(l))), names(valid_levels))
  )
  if (method == "welch_t_test") {
    y <- suppressWarnings(as.numeric(d[[outcome_col]]))
    result$group_labels <- as_array(group_labels)
    result$by_group_as_written <- lapply(sort_text(d[[group_col]]), function(lab)
      c(list(label_as_written = lab, quoted = quoted(lab)), group_stats(y[d[[group_col]] == lab])))
  }
  if (request_format == "v1") {        # v1 field names, used by the v1 notebook
    result$tutoring_label_counts <- columns[[2]]$levels_as_written
    result$score_quantiles <- columns[[1]]$quantiles
    result$score_by_label_as_written <- result$by_group_as_written
    result$score_blank_count <- columns[[1]]$n_blank
    result$score_parseable_count <- columns[[1]]$n_parseable_numeric
    result$stated_score_range <- if (!is.null(valid_ranges$score))
      list(min = valid_ranges$score[1], max = valid_ranges$score[2]) else NULL
  }
  write_result(result)
}

# ===========================================================================
# Task 2: rule-based diagnostics.
#   findings             record-level (blocking / verify)
#   method_findings      only when n_blocking == 0 (severity "out_of_scope")
#   distribution_checks  only when n_blocking == 0 and no method_findings
# ===========================================================================
if (task == "diagnostics") {
  rc <- record_checks()
  method_run <- rc$n_blocking == 0
  mf <- if (method_run) method_checks(rc) else list()
  dist_run <- method_run && length(mf) == 0
  result <- list(
    status = "ok",
    n_rows_in_analysis_set = nrow(d),
    n_usable_rows = sum(rc$usable),
    findings = rc$findings,
    n_blocking = rc$n_blocking,
    n_verify = rc$n_verify,
    method_checks_run = method_run,
    method_findings = mf,
    distribution_checks_run = dist_run,
    distribution_checks = if (dist_run) distribution_checks(rc) else list(),
    distribution_checks_note = if (!method_run) {
      "Deferred: method and distribution checks run after the blocking record-level problems are resolved."
    } else if (!dist_run) {
      "Deferred: distribution checks run only when the method's requirements are met."
    } else {
      "Descriptive diagnostics only; they never switch the method. A large Shapiro-Wilk p-value does not prove normality, and a small one does not by itself rule out the planned test. Shapiro-Wilk runs only for 3 <= n <= 5000 (otherwise p is null)."
    }
  )
  if (request_format == "v1") result$group_findings <- mf     # v1 field name
  write_result(result)
}

# ===========================================================================
# Task 3: run_test (and its v1 alias welch_test).
# Refuses to run if any record-level blocking problem remains in the analysis
# set, or if the data do not meet the method's requirements.
# ===========================================================================
if (task %in% c("run_test", "welch_test")) {
  rc <- record_checks()
  if (rc$n_blocking > 0) {
    write_result(list(status = "blocked",
                      reason = "Unresolved record-level problems remain in the analysis set; the test was not run.",
                      n_blocking = rc$n_blocking,
                      problem_ids = as_array(rc$blocking_ids)))
  }
  mf <- method_checks(rc)
  if (length(mf) > 0) {
    write_result(list(status = "out_of_scope",
                      reason = "The data do not meet the requirements of the method; the test was not run.",
                      method_findings = mf))
  }

  # Warnings raised by R while computing are reported, not hidden.
  r_warnings <- character(0)
  quietly <- function(expr) withCallingHandlers(expr, warning = function(w) {
    r_warnings <<- c(r_warnings, conditionMessage(w)); invokeRestart("muffleWarning") })
  cl_text <- num_text(conf_level)
  u <- rc$usable
  decision <- function(p) if (is.na(p)) NA else if (p < alpha) "reject_H0" else "do_not_reject_H0"

  if (method == "welch_t_test") {
    g1 <- group_labels[1]; g2 <- group_labels[2]      # difference = mean(group_1) - mean(group_2)
    x1 <- rc$num$outcome[u & rc$lab$group == g1]
    x2 <- rc$num$outcome[u & rc$lab$group == g2]
    tt <- quietly(t.test(x1, x2, alternative = "two.sided", var.equal = FALSE, conf.level = conf_level))
    result <- list(
      method_label = tt$method, alternative = tt$alternative, var_equal = FALSE,
      group_1 = list(label = g1, n = length(x1), mean = mean(x1), sd = sd(x1)),
      group_2 = list(label = g2, n = length(x2), mean = mean(x2), sd = sd(x2)),
      mean_difference = mean(x1) - mean(x2),
      ci_lower = tt$conf.int[1], ci_upper = tt$conf.int[2],
      t_statistic = unname(tt$statistic), df = unname(tt$parameter), p_value = tt$p.value,
      n_included = length(x1) + length(x2),
      r_call = sprintf("t.test(%s[%s == '%s'], %s[%s == '%s'], alternative = 'two.sided', var.equal = FALSE, conf.level = %s)",
                       r_name(outcome_col), r_name(group_col), g1, r_name(outcome_col), r_name(group_col), g2, cl_text))
  } else if (method == "pearson_correlation") {
    x <- rc$num$x[u]; y <- rc$num$y[u]
    ct <- quietly(cor.test(x, y, method = "pearson", alternative = "two.sided", conf.level = conf_level))
    result <- list(
      method_label = ct$method, alternative = ct$alternative,
      n = length(x), r = unname(ct$estimate),
      ci_lower = ct$conf.int[1], ci_upper = ct$conf.int[2],
      t_statistic = unname(ct$statistic), df = unname(ct$parameter), p_value = ct$p.value,
      n_included = length(x),
      r_call = sprintf("cor.test(%s, %s, method = 'pearson', alternative = 'two.sided', conf.level = %s)",
                       r_name(col_of("x")), r_name(col_of("y")), cl_text))
  } else if (method == "chi_square_independence") {
    lx <- observed_levels(rc$lab$x[u], col_of("x"))
    ly <- observed_levels(rc$lab$y[u], col_of("y"))
    tab <- table(factor(rc$lab$x[u], lx), factor(rc$lab$y[u], ly))   # rows = x, columns = y
    ct <- quietly(chisq.test(tab))                                   # R default: Yates correction for 2x2
    chi2_uncorrected <- unname(quietly(chisq.test(tab, correct = FALSE))$statistic)
    n <- sum(tab)
    as_rows <- function(m) lapply(seq_len(nrow(m)), function(i) I(unname(as.vector(m[i, ]))))
    result <- list(
      method_label = ct$method,
      n = n, chi_square = unname(ct$statistic), df = unname(ct$parameter), p_value = ct$p.value,
      cramers_v = sqrt(chi2_uncorrected / (n * (min(dim(tab)) - 1))),
      yates_correction = all(dim(tab) == 2),
      observed = list(row_labels = as_array(lx), col_labels = as_array(ly), counts = as_rows(unclass(tab))),
      expected = list(row_labels = as_array(lx), col_labels = as_array(ly), counts = as_rows(ct$expected)),
      min_expected_count = min(ct$expected),
      n_included = n,
      r_call = sprintf("chisq.test(table(%s, %s)); Cramer's V uses chisq.test(table(%s, %s), correct = FALSE)$statistic",
                       r_name(col_of("x")), r_name(col_of("y")), r_name(col_of("x")), r_name(col_of("y"))))
  } else {
    x <- rc$num$x[u]; y <- rc$num$y[u]
    fit <- lm(y ~ x)
    s <- quietly(summary(fit))
    co <- s$coefficients
    ci <- confint(fit, level = conf_level)
    result <- list(
      method_label = "Simple linear regression (lm, one predictor with intercept)",
      n = length(x), slope = co["x", "Estimate"], slope_se = co["x", "Std. Error"],
      intercept = co["(Intercept)", "Estimate"],
      ci_lower = ci["x", 1], ci_upper = ci["x", 2],
      t_statistic = co["x", "t value"], df = fit$df.residual, p_value = co["x", "Pr(>|t|)"],
      r_squared = s$r.squared,
      n_included = length(x),
      r_call = sprintf("fit <- lm(%s ~ %s); summary(fit); confint(fit, level = %s)",
                       r_name(col_of("y")), r_name(col_of("x")), cl_text))
  }
  write_result(c(list(status = "ok"), result,
                 list(conf_level = conf_level, alpha = alpha, decision = decision(result$p_value),
                      r_warnings = as_array(r_warnings))))
}
