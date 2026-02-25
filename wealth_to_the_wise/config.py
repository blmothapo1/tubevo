# Tubevo — YouTube Automation Pipeline
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
import re
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()  # reads .env in the project root (or wherever the process is started)

# ── Logging ──────────────────────────────────
LOG_DIR = Path("output")
LOG_DIR.mkdir(exist_ok=True)
LOG_FILE = LOG_DIR / "pipeline.log"

# ── Phase 8: API key masking filter for all log output ───────────────
# Matches common API key patterns so they never leak to log files,
# Railway logs, or error messages sent to the frontend.
_SECRET_PATTERNS = re.compile(
    r"("
    r"sk-[A-Za-z0-9_-]{10,}"           # OpenAI keys
    r"|xi-[A-Za-z0-9_-]{10,}"          # ElevenLabs keys (header value)
    r"|[A-Za-z0-9]{30,64}"             # Generic long tokens (Pexels, etc.)
    r"|eyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+"  # JWTs
    r")"
)

# More targeted pattern for known key prefixes (used in mask_secrets)
_KEY_PREFIX_PATTERNS = re.compile(
    r"("
    r"sk-[A-Za-z0-9_-]{10,}"
    r"|sk-proj-[A-Za-z0-9_-]{10,}"
    r"|xi-[A-Za-z0-9_-]{10,}"
    r"|AIza[A-Za-z0-9_-]{30,}"         # Google API keys
    r")"
)


def mask_secrets(text: str) -> str:
    """Replace known API key patterns in *text* with a safe redaction.

    This is called by the logging filter automatically, and can also be
    used directly to sanitise error messages before storing them in the
    DB or sending them to the frontend.
    """
    if not text:
        return text

    def _redact(match: re.Match) -> str:
        val = match.group(0)
        # Keep a short prefix for debugging, mask the rest
        if val.startswith(("sk-", "xi-")):
            return val[:6] + "***"
        if val.startswith("AIza"):
            return val[:8] + "***"
        if val.startswith("eyJ"):
            return "eyJ***"
        # Generic long token — show first 4, mask rest
        return val[:4] + "***"
    return _KEY_PREFIX_PATTERNS.sub(_redact, text)


class _KeyMaskingFilter(logging.Filter):
    """Logging filter that scrubs API keys from log messages."""

    def filter(self, record: logging.LogRecord) -> bool:
        if record.msg and isinstance(record.msg, str):
            record.msg = mask_secrets(record.msg)
        if record.args:
            if isinstance(record.args, dict):
                record.args = {
                    k: mask_secrets(str(v)) if isinstance(v, str) else v
                    for k, v in record.args.items()
                }
            elif isinstance(record.args, tuple):
                record.args = tuple(
                    mask_secrets(str(a)) if isinstance(a, str) else a
                    for a in record.args
                )
        return True


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(),
    ],
)

# Apply key-masking filter to the root logger so ALL handlers benefit
logging.getLogger().addFilter(_KeyMaskingFilter())

logger = logging.getLogger("tubevo")

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
        "You are 'Tubevo', a confident and direct financial educator. "
        "No fluff, no filler. You tell the viewer exactly what to do. "
        "Your topics revolve around wealth-building, frugality, success habits, "
        "and financial literacy. Every sentence earns its place."
    ),
)
