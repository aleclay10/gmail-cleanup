import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CREDENTIALS_DIR = os.path.join(BASE_DIR, "credentials")
OUTPUT_DIR = os.path.join(BASE_DIR, "output")

CLIENT_SECRET_FILE = os.path.join(CREDENTIALS_DIR, "client_secret.json")
TOKEN_FILE = os.path.join(CREDENTIALS_DIR, "token.json")
CHECKPOINT_FILE = os.path.join(OUTPUT_DIR, "checkpoint.json")
REPORT_FILE = os.path.join(OUTPUT_DIR, "report.html")

GMAIL_SCOPES = ["https://www.googleapis.com/auth/gmail.modify"]

LABEL_IMPORTANT = "AI/Important"
LABEL_LOW_PRIORITY = "AI/Low Priority"

BATCH_SIZE = 25
LLM_WORKERS = 4
CHECKPOINT_INTERVAL = 10

DEFAULT_QUERY = "is:unread"

SETTINGS_FILE = os.path.join(BASE_DIR, "settings.json")

OLLAMA_URL = "http://localhost:11434"
OLLAMA_MODEL = "qwen2.5-coder:14b"
