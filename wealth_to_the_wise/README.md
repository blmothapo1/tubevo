# Tubevo — YouTube on Autopilot

> **[tubevo.us](https://tubevo.us)**

AI-powered video generation, scheduling, and upload automation for YouTube creators.
Built with a Python CLI pipeline (Phase 1) and a full SaaS platform (Phase 2).

## Architecture

```
wealth_to_the_wise/
├── main.py                 # CLI pipeline orchestrator
├── script_generator.py     # OpenAI-powered script & metadata
├── voiceover.py            # ElevenLabs TTS
├── stock_footage.py        # Pexels stock footage
├── video_builder.py        # MoviePy video assembly
├── thumbnail.py            # Auto-generated thumbnails
├── uploader.py             # YouTube Data API v3 upload
├── config.py               # .env configuration (Phase 1)
├── backend/                # FastAPI SaaS backend
│   ├── app.py              #   App factory + middleware
│   ├── auth.py             #   JWT authentication
│   ├── models.py           #   SQLAlchemy models (User, VideoRecord)
│   ├── routers/
│   │   ├── auth.py         #   Signup / login / refresh / profile
│   │   ├── billing.py      #   Stripe checkout / webhook / portal
│   │   ├── videos.py       #   Generate + history + stats
│   │   └── health.py       #   Health check
│   └── tests/              #   pytest suite (32 tests)
├── frontend/               # Vite + React 19 + Tailwind v4
│   ├── src/pages/          #   Dashboard, Videos, Schedule, Settings
│   └── vercel.json         #   Vercel deployment config
└── .github/workflows/ci.yml  # GitHub Actions CI
```

## Quick Start

### 1. Install dependencies
```bash
cd wealth_to_the_wise
pip install -r requirements.txt -r requirements-backend.txt
cd frontend && npm install && cd ..
```

### 2. Configure
```bash
cp .env.example .env
# Fill in your API keys (OpenAI, ElevenLabs, Pexels, Stripe, JWT secret)
```

### 3. Run (development)
```bash
# Backend (FastAPI)
uvicorn backend.app:app --reload --port 8000

# Frontend (Vite dev server — proxies /api, /auth, /billing to :8000)
cd frontend && npm run dev
```

### 4. Run tests
```bash
python -m pytest backend/tests/ -v
```

## Deployment

| Service | Deploys to | Domain |
|---------|-----------|--------|
| **Frontend** | Vercel | [tubevo.us](https://tubevo.us) |
| **Backend** | Railway | api.tubevo.us |

Set `VITE_API_URL=https://api.tubevo.us` in the frontend's Vercel env vars.
Set `CORS_ORIGINS=https://tubevo.us,https://www.tubevo.us` in Railway env vars.

## Environment Variables

See [`.env.example`](.env.example) for the full reference with descriptions.

## License

Private — all rights reserved.
