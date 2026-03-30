# CLAUDE.md

## Project Overview

"Hot Hog on a Bicycle" — a conference demo app for PostHog LLM Analytics. Attendees at the Hot Hog Intelligence hot dog stand compete against an AI agent to prompt-engineer the best SVG of a hot dog riding a bicycle.

Inspired by Simon Willison's [pelican-bicycle](https://github.com/simonw/pelican-bicycle) SVG benchmark.

## Commands

```bash
make install    # uv sync to install deps
make dev        # Run with auto-reload (localhost:8000)
make run        # Run in production mode
make test       # Run tests
```

## Architecture

- **Backend**: Python FastAPI, serves API + static frontend
- **Frontend**: Plain HTML/CSS/JS served by FastAPI (no build step)
- **LLM calls**: All via OpenRouter (OpenAI-compatible API), wrapped with PostHog's `posthog.ai.openai.OpenAI` for automatic LLM Analytics
- **Database**: SQLite via SQLAlchemy
- **PostHog**: Every LLM call auto-captures `$ai_generation` events with traces/spans

## Game Flow

1. User starts game → random OpenRouter model assigned
2. 3 rounds: user writes prompt → model generates SVG (AI challenger does same in parallel)
3. AI judge blindly scores both final SVGs
4. Reveal: side-by-side comparison with scores

## Key Files

- `backend/main.py` — FastAPI app, API routes, static file serving
- `backend/config.py` — Model lists, settings
- `backend/game.py` — Game engine (rounds, SVG extraction)
- `backend/challenger.py` — AI challenger agent logic
- `backend/judge.py` — Blind judging
- `backend/openrouter.py` — OpenRouter client (PostHog-instrumented)
- `backend/models.py` — SQLAlchemy models
- `frontend/` — Static HTML/CSS/JS

## Environment

Copy `.env.example` to `.env` and set `OPENROUTER_API_KEY`, `POSTHOG_API_KEY`, `POSTHOG_HOST`.
