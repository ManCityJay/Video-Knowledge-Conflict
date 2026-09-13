"""Runtime constants and project paths."""

from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent.parent
PROJECT_ROOT = SCRIPT_DIR.parent
DEFAULT_SOURCE_CASE_DIR = PROJECT_ROOT / "dataset" / "source_cases"
DEFAULT_CASE_DIR = PROJECT_ROOT / "dataset" / "cases"
RESULTS_DIR = PROJECT_ROOT / "results"

AUTHOR_JUDGE_MODEL = "openai/gpt-5.6-luna-pro"
GEMINI_QA_MODEL = "google/gemini-3.1-pro-preview"
QWEN_QA_MODEL = "qwen3.8-max"
KIMI_QA_MODEL = "kimi-k3"
QA_MODELS = (GEMINI_QA_MODEL, QWEN_QA_MODEL, KIMI_QA_MODEL)
DEFAULT_QA_MODEL = GEMINI_QA_MODEL
QA_MODEL_SLUGS = {
    GEMINI_QA_MODEL: "gemini",
    QWEN_QA_MODEL: "qwen",
    KIMI_QA_MODEL: "kimi",
}
CLI_THINKING_EFFORTS = ("none", "default")

SEEDANCE_MODEL = "doubao-seedance-2-5-260628"
ARK_BASE_URL = "https://ark.cn-beijing.volces.com/api/v3"
DEFAULT_CASE_WORKERS = 4
DEFAULT_REQUEST_WORKERS = 12
DEFAULT_REQUEST_RPM = 20.0
DEFAULT_SEEDANCE_TOTAL_WORKERS = 12

CASE_SCHEMA_VERSION = "4.0"
QUESTION_LIMIT = 3
CONFLICT_VIDEO_LIMIT = 5
TOTAL_VIDEO_LIMIT = CONFLICT_VIDEO_LIMIT + 1
VIDEO_ROLES = {"conflict", "control"}
VIDEO_STATUSES = {"pending", "submitted", "ready", "failed"}
REVIEW_STATUSES = {"pending", "verified", "rejected"}
VERDICTS = {"context_grounded", "knowledge_trapped", "ambiguous_or_unjudgeable"}
LEGACY_VERDICTS = {"video_grounded"}
ACCEPTED_VERDICTS = VERDICTS | LEGACY_VERDICTS
INPUT_MODES = ("video", "description")
VIDEO_EXTENSIONS = {".mp4", ".mov", ".m4v", ".webm"}
