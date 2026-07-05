import os
from pathlib import Path
from zoneinfo import ZoneInfo
from dotenv import load_dotenv

load_dotenv()

# Timezone
TZ = ZoneInfo("America/Los_Angeles")

# Paths
BASE_DIR = Path(__file__).parent
KNOWLEDGE_BASE_DIR = Path(os.getenv("KNOWLEDGE_BASE_DIR", BASE_DIR / "knowledge_base"))
SQLITE_DB_PATH = os.getenv("SQLITE_DB_PATH", str(BASE_DIR / "nutrition.db"))
DISKCACHE_DIR = os.getenv("DISKCACHE_DIR", str(BASE_DIR / ".cache"))
TRACES_DIR = Path(os.getenv("TRACES_DIR", "/opt/nutrition-bot/logs/traces"))

# Telegram
TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_CHAT_ID = int(os.environ["TELEGRAM_CHAT_ID"])

# Anthropic models
ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]
ANTHROPIC_MODEL_HEAVY = os.getenv("ANTHROPIC_MODEL_HEAVY", "claude-opus-4-8")
ANTHROPIC_MODEL_MID = os.getenv("ANTHROPIC_MODEL_MID", "claude-sonnet-4-6")
ANTHROPIC_MODEL_FAST = os.getenv("ANTHROPIC_MODEL_FAST", "claude-haiku-4-5-20251001")

# Google Health API (replaces Fitbit Web API)
GOOGLE_HEALTH_CLIENT_ID = os.getenv("GOOGLE_HEALTH_CLIENT_ID", "")
GOOGLE_HEALTH_CLIENT_SECRET = os.getenv("GOOGLE_HEALTH_CLIENT_SECRET", "")

# Open-Meteo (Mountain View, CA)
WEATHER_LAT = float(os.getenv("WEATHER_LAT", "37.3861"))
WEATHER_LON = float(os.getenv("WEATHER_LON", "-122.0839"))
WEATHER_LOCATION_NAME = os.getenv("WEATHER_LOCATION_NAME", "Mountain View, CA")

# Uptime Kuma push URL (optional — only needed on VM)
UPTIME_KUMA_PUSH_URL = os.getenv("UPTIME_KUMA_PUSH_URL", "")

# Step and sleep goals (override via user_profile table)
DEFAULT_STEP_GOAL = 10000
DEFAULT_SLEEP_GOAL_HRS = 7.0
