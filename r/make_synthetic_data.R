# =============================================================================
# make_synthetic_data.R  --  creates the SYNTHETIC example datasets
#
# Run once from the project folder:   Rscript r/make_synthetic_data.R
#
# These are simulated students, not real people. The numbers are random draws;
# they were NOT tuned to reproduce the numbers printed in the case-study PDF,
# and no file was chosen for its test result (p-value). All statistical results
# in the notebook are computed by R from these files.
#
# Output files (in data/):
#   tutoring_scores_messy_synthetic.csv     80 students with deliberately planted
#                                           data problems (case-study scenario)
#   tutoring_scores_clean_synthetic.csv     80 students, simulated with a true mean
#                                           difference of 5 points
#   tutoring_scores_no_difference_synthetic.csv
#                                           80 students, simulated with EQUAL true means
#   tutoring_scores_unequal_variance_synthetic.csv
#                                           30 vs 50 students with very different
#                                           spreads (SD 5 vs 13)
# The last three have no planted problems and no boxplot flags (see the seed
# note below), so they follow the normal path without user clarification.
# =============================================================================

out_dir <- file.path("data")
dir.create(out_dir, showWarnings = FALSE)

simulate_students <- function(seed, n_yes = 40, n_no = 40, mean_yes = 76, sd_yes = 10,
                              mean_no = 71, sd_no = 8) {
  set.seed(seed)
  ids <- sprintf("S%03d", 1:(n_yes + n_no))
  tutoring <- rep(c("yes", "no"), times = c(n_yes, n_no))   # first n_yes rows are "yes"
  score <- c(rnorm(n_yes, mean = mean_yes, sd = sd_yes), rnorm(n_no, mean = mean_no, sd = sd_no))
  score <- round(pmin(pmax(score, 0), 100), 1)               # keep inside the 0-100 scale
  data.frame(student_id = ids, tutoring = tutoring, score = score,
             stringsAsFactors = FALSE)
}

# ---- Messy file: plant the problem types described in the case study --------
messy <- simulate_students(seed = 20261008)
messy$score[messy$student_id == "S001"] <- NA          # missing score (tutoring group)
messy$score[messy$student_id == "S041"] <- NA          # missing score (no-tutoring group)
messy$score[messy$student_id == "S006"] <- 850         # entry error: true value 85
messy$tutoring[messy$student_id == "S015"] <- "yes "   # label with a trailing space
messy$score[messy$student_id == "S065"] <- 95.8        # genuine but unusually high score

# ---- Files for the normal path: nothing planted -----------------------------
# These files exercise the normal (no-clarification) path. Even well-behaved
# random data often has a value outside the boxplot whiskers, which the
# workflow would (correctly) send to the user for verification. So for each
# file we draw samples with consecutive seeds until neither group has a
# boxplot flag, and print the seed that was used. Only this screening is
# applied; the scores themselves are not edited, and the test result is never
# looked at when choosing a seed.
has_boxplot_flag <- function(df) {
  any(vapply(split(df$score, df$tutoring), function(x) length(boxplot.stats(x)$out) > 0, logical(1)))
}
draw_without_flags <- function(label, first_seed, ...) {
  seed <- first_seed
  df <- simulate_students(seed, ...)
  while (has_boxplot_flag(df)) {
    seed <- seed + 1
    df <- simulate_students(seed, ...)
  }
  cat(label, "file uses seed", seed, "\n")
  df
}
clean <- draw_without_flags("Clean", 20261009)
no_difference <- draw_without_flags("No-difference", 20261101, mean_yes = 72, sd_yes = 9, mean_no = 72, sd_no = 9)
unequal <- draw_without_flags("Unequal-variance", 20261201, n_yes = 30, n_no = 50,
                              mean_yes = 78, sd_yes = 5, mean_no = 72, sd_no = 13)

# na = "" writes missing scores as empty cells; text columns are quoted so the
# trailing space in "yes " is preserved.
write.csv(messy, file.path(out_dir, "tutoring_scores_messy_synthetic.csv"), row.names = FALSE, na = "")
write.csv(clean, file.path(out_dir, "tutoring_scores_clean_synthetic.csv"), row.names = FALSE, na = "")
write.csv(no_difference, file.path(out_dir, "tutoring_scores_no_difference_synthetic.csv"), row.names = FALSE, na = "")
write.csv(unequal, file.path(out_dir, "tutoring_scores_unequal_variance_synthetic.csv"), row.names = FALSE, na = "")
cat("Wrote synthetic datasets to", normalizePath(out_dir), "\n")
