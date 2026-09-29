"""Runtime configuration, read from environment variables (see .env.example)."""
from __future__ import annotations

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{BASE_DIR / 'tosca_analyzer.db'}")
MAX_UPLOAD_MB = int(os.getenv("MAX_UPLOAD_MB", "200"))
CORS_ORIGINS = [o.strip() for o in os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",") if o.strip()]
# When set, every /api call must send "Authorization: Bearer <API_TOKEN>".
API_TOKEN = os.getenv("API_TOKEN", "")
FRONTEND_DIST = Path(os.getenv("FRONTEND_DIST", BASE_DIR.parent / "frontend" / "dist"))

# Defaults for settings that can also be changed from the Settings screen.
DEFAULT_SETTINGS = {
    "docs_version": os.getenv("TOSCA_DOCS_VERSION", "2026.1"),
    "docs_live_check": os.getenv("DOCS_LIVE_CHECK", "true").lower() == "true",
    "jira": {
        "base_url": os.getenv("JIRA_BASE_URL", ""),
        "deployment": os.getenv("JIRA_DEPLOYMENT", "cloud"),  # cloud | server
        "email": os.getenv("JIRA_EMAIL", ""),
        "api_token": os.getenv("JIRA_API_TOKEN", ""),
        "test_steps_source": os.getenv("JIRA_STEPS_SOURCE", "auto"),  # auto | xray_cloud | xray_server | zephyr_scale | description
        "acceptance_field": os.getenv("JIRA_ACCEPTANCE_FIELD", ""),  # e.g. customfield_10035
        "xray_client_id": os.getenv("XRAY_CLIENT_ID", ""),
        "xray_client_secret": os.getenv("XRAY_CLIENT_SECRET", ""),
        "zephyr_token": os.getenv("ZEPHYR_TOKEN", ""),
    },
    "rally": {
        "base_url": os.getenv("RALLY_BASE_URL", "https://rally1.rallydev.com"),
        "api_key": os.getenv("RALLY_API_KEY", ""),
        "workspace": os.getenv("RALLY_WORKSPACE", ""),
    },
}
SECRET_KEYS = {"api_token", "xray_client_secret", "zephyr_token", "api_key"}
