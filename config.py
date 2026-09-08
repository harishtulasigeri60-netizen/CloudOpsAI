import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
INSTANCE_DIR = BASE_DIR / "instance"
REPORT_DIR = BASE_DIR / "generated_reports"
INSTANCE_DIR.mkdir(exist_ok=True)
REPORT_DIR.mkdir(exist_ok=True)

SECRET_KEY = os.getenv("CLOUDOPSAI_SECRET", "")
DB_PATH = Path(os.getenv("CLOUDOPSAI_DB", str(INSTANCE_DIR / "cloudopsai.db")))
REGION = os.getenv("AWS_REGION", "ap-south-1")
TOPIC_ARN = os.getenv("CLOUDOPSAI_TOPIC_ARN", "")
BUCKET_NAME = os.getenv("CLOUDOPSAI_BUCKET", "")
SESSION_COOKIE_NAME = "cloudopsai_session"
MAX_CONTENT_LENGTH = 64 * 1024
