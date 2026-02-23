# Wealth to the Wise — Automated YouTube Upload Pipeline

A fully modular Python pipeline that generates video scripts with OpenAI, produces YouTube metadata (title, description, tags), and uploads finished videos via the YouTube Data API v3.

## Project Structure

```
wealth_to_the_wise/
├── main.py                 # Pipeline orchestrator (CLI entry point)
├── script_generator.py     # OpenAI-powered script & metadata generation
├── uploader.py             # YouTube Data API v3 resumable upload
├── config.py               # .env-based configuration
├── requirements.txt        # Python dependencies
├── .env.example            # Template — copy to .env
├── client_secrets.json     # ⬅ YOU provide this (Google OAuth2 credentials)
└── output/                 # Auto-created; holds scripts & metadata
```

## Quick Start

### 1. Install dependencies
```bash
cd wealth_to_the_wise
pip install -r requirements.txt
```

### 2. Set up credentials
1. **Google OAuth2** — Go to [Google Cloud Console](https://console.cloud.google.com/apis/credentials), create an OAuth 2.0 Client ID (Desktop app), and download the JSON. Save it as `client_secrets.json` in this folder.
2. **OpenAI API Key** — Get one from [platform.openai.com](https://platform.openai.com/api-keys).
3. Copy `.env.example` → `.env` and fill in your keys.

### 3. Run the pipeline
```bash
# Interactive — prompts for topic and video file
python main.py

# With arguments
python main.py "5 Frugal Habits That Build Wealth Fast" --video /path/to/video.mp4
```

## How It Works

| Step | What happens |
|------|-------------|
| **1** | You provide a topic (CLI arg or prompt) |
| **2** | OpenAI generates a tight, punchy 3-minute script |
| **3** | OpenAI generates an SEO-optimised title, description & tags |
| **4** | Pipeline pauses for you to record voiceover & edit video |
| **5** | You provide the finished `.mp4` path |
| **6** | Video is uploaded to YouTube via resumable upload with progress |

## Extending the Pipeline

The code has clearly marked **PLUG-IN** points for:

- **ElevenLabs voiceover** → `step_generate_voiceover()` in `main.py`
- **Auto-scheduling** → `step_schedule_upload()` in `main.py` (uses the `schedule` library)
- **Thumbnail generation** → add a new step function and call it before upload

Each step is a standalone function — add, remove, or reorder without touching the rest.

## Configuration Reference

| Env Variable | Default | Description |
|---|---|---|
| `YOUTUBE_CLIENT_SECRETS` | `client_secrets.json` | Path to Google OAuth2 client secrets |
| `YOUTUBE_OAUTH_TOKEN` | `token.json` | Cached OAuth2 token (auto-created) |
| `OPENAI_API_KEY` | — | Your OpenAI API key |
| `DEFAULT_VIDEO_CATEGORY` | `22` | YouTube category ID |
| `DEFAULT_TAGS` | wealth,money,… | Comma-separated default tags |
| `DEFAULT_PRIVACY` | `private` | Upload privacy status |
| `CHANNEL_TONE` | (see .env.example) | Prompt persona for script generation |
