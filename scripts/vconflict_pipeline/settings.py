"""Runtime constants and project paths."""

from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent.parent
PROJECT_ROOT = SCRIPT_DIR.parent
DEFAULT_SOURCE_CASE_DIR = PROJECT_ROOT / "dataset" / "source_cases"
DEFAULT_CASE_DIR = PROJECT_ROOT / "dataset" / "cases"
DEFAULT_SUMMARY_OUTPUT = PROJECT_ROOT / "results" / "knowledge_conflict_summary.json"
GEMINI_SUMMARY_OUTPUT = PROJECT_ROOT / "results" / "gemini_knowledge_conflict_summary.json"
DEFAULT_MARKDOWN_OUTPUT = PROJECT_ROOT / "results" / "case_results.md"
GEMINI_MARKDOWN_OUTPUT = PROJECT_ROOT / "results" / "gemini_case_results.md"

AUTHOR_JUDGE_MODEL = "openai/gpt-5.6-luna-pro"
GEMINI_QA_MODEL = "google/gemini-3.1-pro-preview"
QWEN_QA_MODEL = "qwen3.8-max"
KIMI_QA_MODEL = "kimi-k3"
QA_MODELS = (GEMINI_QA_MODEL, QWEN_QA_MODEL, KIMI_QA_MODEL)
DEFAULT_QA_MODEL = GEMINI_QA_MODEL
CLI_THINKING_EFFORTS = ("none", "default", "low", "medium", "high")

SEEDANCE_MODEL = "doubao-seedance-2-5-260628"
ARK_BASE_URL = "https://ark.cn-beijing.volces.com/api/v3"
DEFAULT_CASE_WORKERS = 4
DEFAULT_REQUEST_WORKERS = 12
DEFAULT_REQUEST_RPM = 20.0
DEFAULT_SEEDANCE_TOTAL_WORKERS = 12

CASE_SCHEMA_VERSION = "4.0"
QUESTION_PAIR_LIMIT = 3
QUESTION_TYPES = ("implicit_prior", "explicit_prior")
QUESTION_TYPE_SET = set(QUESTION_TYPES)
QUESTION_LIMIT = QUESTION_PAIR_LIMIT * len(QUESTION_TYPES)
CONFLICT_VIDEO_LIMIT = 5
TOTAL_VIDEO_LIMIT = CONFLICT_VIDEO_LIMIT + 1
VIDEO_ROLES = {"conflict", "control"}
VIDEO_STATUSES = {"pending", "submitted", "ready", "failed"}
REVIEW_STATUSES = {"pending", "verified", "rejected"}
VERDICTS = {"video_grounded", "knowledge_trapped", "ambiguous_or_unjudgeable"}
VIDEO_EXTENSIONS = {".mp4", ".mov", ".m4v", ".webm"}

