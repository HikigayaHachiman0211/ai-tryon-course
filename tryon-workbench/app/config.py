"""Centralized configuration and shared state for the try-on service."""

import os
import re
from zoneinfo import ZoneInfo
from typing import Dict, Any, List

# ===== GCP / Vertex / Project Config =====
GCP_PROJECT_ID = os.environ.get("GCP_PROJECT_ID", "")
GCP_LOCATION = os.environ.get("GCP_LOCATION", "asia-east1")
VERTEX_LOCATION = os.environ.get("VERTEX_LOCATION", "global")
VERTEX_AI_API_KEY = os.environ.get("VERTEX_AI_API_KEY", "")
DEFAULT_API_KEY = os.environ.get("GEMINI_API_KEY", "vertex-ai")
RECOMMEND_APP_URL = str(os.environ.get("VITE_RECOMMEND_APP_URL", "") or "").strip()
TRYON_EMBED_MODE = str(os.environ.get("VITE_TRYON_EMBED_MODE", "standalone") or "standalone").strip().lower()
if TRYON_EMBED_MODE not in ("standalone", "embed"):
    TRYON_EMBED_MODE = "standalone"
RESULTS_GCS_BUCKET = str(os.environ.get("RESULTS_GCS_BUCKET", "") or "").strip()
RESULTS_GCS_PREFIX = str(os.environ.get("RESULTS_GCS_PREFIX", "tryon-results") or "tryon-results").strip().strip("/")
INTAKE_MAX_IMAGE_BYTES = 15 * 1024 * 1024
IMAGE_DATA_URL_RE = re.compile(r"^data:(image/[a-zA-Z0-9.+-]+);base64,(.+)$", re.IGNORECASE | re.DOTALL)

# ===== Model Config =====
MODEL_MAP: Dict[str, Dict[str, Any]] = {
    "flash": {
        "ids": ["gemini-3.1-flash-image-preview", "gemini-2.5-flash-image"],
        "name": "Nano Banana 2",
    },
    "pro": {
        "ids": ["gemini-3-pro-image-preview", "gemini-3-pro-image"],
        "name": "Nano Banana Pro",
    },
}
DEFAULT_MODEL = "flash"

MODEL_PRICING: Dict[str, float] = {
    "flash": 0.067,
    "pro": 0.134,
}

MODEL_LIMITS: Dict[str, Dict[str, int]] = {
    "flash": {"rpm": 100, "tpm": 200000, "rpd": 1000},
    "pro": {"rpm": 20, "tpm": 100000, "rpd": 250},
}

# ===== Paths =====
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__))) if os.path.basename(os.path.dirname(os.path.abspath(__file__))) == "app" else os.path.dirname(os.path.abspath(__file__))
# When imported from Cloud/app/config.py, BASE_DIR should be Cloud/
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# Recalculate: this file is Cloud/app/config.py, so BASE_DIR = Cloud/
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

WORKSPACE_DIR = os.path.dirname(BASE_DIR)
CREDENTIALS_PATH = os.path.join(BASE_DIR, "gcp-credentials.json")
PROMPT_PATH = os.path.join(BASE_DIR, "prompt.txt")
LOCAL_PROXY_CONFIG_PATH = os.path.join(BASE_DIR, "local_proxy_config.json")
AI_STUDIO_CONFIG_PATH = os.path.join(BASE_DIR, "ai_studio_config.json")
LOCAL_ANTIGRAVITY_DIRS = [
    os.path.join(os.path.expanduser("~"), ".antigravity_tools"),
    os.path.join(WORKSPACE_DIR, ".antigravity_tools"),
]

UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")
ASSET_DIR = os.path.join(BASE_DIR, "assets")
HISTORY_DIR = os.path.join(BASE_DIR, "history")
HISTORY_FILES_DIR = os.path.join(HISTORY_DIR, "files")
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(ASSET_DIR, exist_ok=True)
os.makedirs(HISTORY_FILES_DIR, exist_ok=True)

# ===== Local Proxy Defaults =====
DEFAULT_LOCAL_PROXY_CONFIG: Dict[str, Any] = {
    "enabled": False,
    "base_url": "http://127.0.0.1:8045",
    "api_key": "",
    "timeout_seconds": 180,
    "flash_model": "gemini-3.1-flash-image",
    "pro_model": "gemini-3-pro-image",
}

DEFAULT_AI_STUDIO_CONFIG: Dict[str, Any] = {
    "api_key": "",
    "flash_model": "gemini-3.1-flash-image-preview",
    "pro_model": "gemini-3-pro-image-preview",
}

# ===== Timezone =====
PT_ZONE = ZoneInfo("America/Los_Angeles")
CST_ZONE = ZoneInfo("Asia/Shanghai")

# ===== Error Analysis =====
ERROR_ANALYSIS_MODEL = os.environ.get(
    "ERROR_ANALYSIS_MODEL",
    "publishers/google/models/gemini-3.1-flash-lite-preview",
)

VERTEX_DOC_LINKS = [
    "https://cloud.google.com/vertex-ai/generative-ai/docs/model-reference/api-errors",
    "https://cloud.google.com/vertex-ai/generative-ai/docs/start/quickstarts/quickstart-multimodal",
    "https://ai.google.dev/gemini-api/docs/quickstart?hl=zh-cn",
    "https://ai.google.dev/gemini-api/docs/image-generation?hl=zh-cn",
    "https://ai.google.dev/gemini-api/docs/pricing?hl=zh-cn",
    "https://ai.google.dev/gemini-api/docs/safety-settings",
]

# ===== Cleanup Config =====
# Maximum age (seconds) for temp files in uploads/assets before auto-cleanup
TEMP_FILE_MAX_AGE_SECONDS = int(os.environ.get("TEMP_FILE_MAX_AGE_SECONDS", str(12 * 3600)))
# Maximum number of history entries per user/session
HISTORY_MAX_ENTRIES = int(os.environ.get("HISTORY_MAX_ENTRIES", "200"))
# Maximum number of in-memory error log entries
ERROR_LOG_MAX_ENTRIES = 500
# Max in-memory tasks before pruning old completed ones
TASK_STORE_MAX_ENTRIES = int(os.environ.get("TASK_STORE_MAX_ENTRIES", "500"))
