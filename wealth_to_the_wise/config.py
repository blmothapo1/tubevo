# Wealth to the Wise — YouTube Automation Pipeline
# Environment variables consumed by this project.
# Copy .env.example → .env and fill in your real values.

# ──────────────────────────────────────────────
# .env.example  (committed to repo as reference)
# ──────────────────────────────────────────────
# YOUTUBE_CLIENT_SECRETS=client_secrets.json
# OPENAI_API_KEY=sk-...
# DEFAULT_VIDEO_CATEGORY=22
# DEFAULT_TAGS=wealth,money,frugality,financial literacy,success habits,personal finance
# CHANNEL_TONE=confident, direct, no-fluff financial educator who tells the viewer exactly what to do

import os
import logging
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()  # reads .env in the project root (or wherever the process is started)

# ── Logging ──────────────────────────────────
LOG_DIR = Path("output")
LOG_DIR.mkdir(exist_ok=True)
LOG_FILE = LOG_DIR / "pipeline.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger("wealth_to_the_wise")

# ── YouTube / OAuth ──────────────────────────
CLIENT_SECRETS_FILE: str = os.getenv("YOUTUBE_CLIENT_SECRETS", "client_secrets.json")
OAUTH_TOKEN_FILE: str = os.getenv("YOUTUBE_OAUTH_TOKEN", "token.json")
YOUTUBE_API_SERVICE_NAME: str = "youtube"
YOUTUBE_API_VERSION: str = "v3"
YOUTUBE_UPLOAD_SCOPE: list[str] = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube",
]

# ── OpenAI ───────────────────────────────────
OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")

# ── Defaults for every upload ────────────────
DEFAULT_VIDEO_CATEGORY: str = os.getenv("DEFAULT_VIDEO_CATEGORY", "22")  # "22" = People & Blogs
DEFAULT_TAGS: list[str] = [
    t.strip()
    for t in os.getenv(
        "DEFAULT_TAGS",
        "wealth,money,frugality,financial literacy,success habits,personal finance",
    ).split(",")
]
DEFAULT_PRIVACY: str = os.getenv("DEFAULT_PRIVACY", "private")  # private until you're ready

# ── YouTube playlist ─────────────────────────
# Set this to a playlist ID (e.g. "PLxxxxxxxxxxxxxxxx") to auto-add every
# uploaded video to that playlist.  Leave empty to skip playlist assignment.
DEFAULT_PLAYLIST_ID: str = os.getenv("DEFAULT_PLAYLIST_ID", "")

# ── Pexels (stock footage) ───────────────────
PEXELS_API_KEY: str = os.getenv("PEXELS_API_KEY", "")

# ── Video file size limit (MB) ───────────────
# If the rendered video exceeds this size, it will be re-encoded at a lower
# bitrate before upload.  YouTube accepts up to 256 GB, but smaller files
# upload faster and are more practical.  Default: 200 MB.
MAX_VIDEO_SIZE_MB: int = int(os.getenv("MAX_VIDEO_SIZE_MB", "200"))

# ── Channel voice / tone (fed into prompts) ──
CHANNEL_TONE: str = os.getenv(
    "CHANNEL_TONE",
    (
        "You are 'Wealth to the Wise', a confident and direct financial educator. "
        "No fluff, no filler. You tell the viewer exactly what to do. "
        "Your topics revolve around wealth-building, frugality, success habits, "
        "and financial literacy. Every sentence earns its place."
    ),
)
