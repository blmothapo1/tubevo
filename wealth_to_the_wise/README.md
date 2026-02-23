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
│   ├── config.py           #   Pydantic Settings (env vars)
│   ├── database.py         #   Async SQLAlchemy (SQLite dev / PostgreSQL prod)
│   ├── models.py           #   User, VideoRecord, OAuthToken
│   ├── routers/
│   │   ├── auth.py         #   Signup / login / refresh / profile
│   │   ├── billing.py      #   Stripe checkout / webhook / portal
│   │   ├── videos.py       #   Generate + history + stats
│   │   ├── youtube.py      #   Google OAuth: authorize / callback / status / disconnect
│   │   └── health.py       #   Health check
│   └── tests/              #   pytest suite (40 tests)
├── frontend/               # Vite + React 19 + Tailwind v4
│   ├── src/pages/          #   Landing, Dashboard, Videos, Schedule, Settings, Onboarding
│   ├── src/components/     #   Sidebar, Topbar, DashboardLayout (mobile responsive)
│   └── vercel.json         #   Vercel deployment config
├── Dockerfile              # Production Docker image (Railway)
└── .github/workflows/ci.yml  # GitHub Actions CI (backend tests + frontend build)
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
# 40 tests: auth (16), billing (4), videos (6), youtube (8), app (6)
```

## Deployment

| Service | Platform | Domain | Database |
|---------|----------|--------|----------|
| **Frontend** | Vercel | [tubevo.us](https://tubevo.us) | — |
| **Backend** | Railway | api.tubevo.us | PostgreSQL (Railway) |

### Key Environment Variables (Railway)

| Variable | Description |
|----------|-------------|
| `DATABASE_URL` | `${{Postgres.DATABASE_URL}}` (auto-linked) |
| `JWT_SECRET_KEY` | Token signing key |
| `CORS_ORIGINS` | `https://tubevo.us,https://www.tubevo.us` |
| `GOOGLE_CLIENT_ID` | Google OAuth for YouTube |
| `GOOGLE_CLIENT_SECRET` | Google OAuth secret |
| `GOOGLE_REDIRECT_URI` | `https://tubevo.us/auth/google/callback` |
| `STRIPE_SECRET_KEY` | Stripe billing |
| `OPENAI_API_KEY` | Script generation |
| `PEXELS_API_KEY` | Stock footage |
| `ELEVENLABS_API_KEY` | TTS voiceovers |

See [`.env.example`](.env.example) for the full reference with descriptions.

## License

Private — all rights reserved.
