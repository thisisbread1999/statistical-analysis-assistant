"""Project paths and the analysis settings fixed by the project design."""
from pathlib import Path

PACKAGE_DIR = Path(__file__).resolve().parent
PROJECT_DIR = PACKAGE_DIR.parent
DATA_DIR = PROJECT_DIR / "data"
OUTPUT_DIR = PROJECT_DIR / "outputs"          # tests may point this somewhere else

ALPHA = 0.05                        # significance level fixed by the analysis design
DEFAULT_CONF_LEVEL = 0.95           # a follow-up question may ask for another level (e.g. 0.99)
MAX_PLAN_REVISIONS = 1              # case study: at most one automatic method-plan revision
MAX_REPORT_REVISIONS = 1            # case study: Model A revises its explanation at most once
MAX_CLARIFICATION_ROUNDS = 2        # our choice; the case study does not fix a number
MAX_MODEL_CALLS_PER_REQUEST = 15    # hard cap on LLM calls for one request (cost and loop safety)
RUN_CONFIG = {"recursion_limit": 80}
