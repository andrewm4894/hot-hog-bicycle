# Hot Hog on a Bicycle

**Human vs AI hot dog SVG prompt battle** — a conference demo app for [PostHog LLM Analytics](https://posthog.com/llm-analytics).

Built for the [AI Engineer Europe](https://www.ai.engineer/europe) conference (April 9-10, London), where PostHog is sponsoring a hot dog cart under the banner **"Hot Hog Intelligence — See how the sausage is made."**

Inspired by Simon Willison's [pelican-bicycle](https://github.com/simonw/pelican-bicycle) SVG benchmark.

**Live demo**: https://hot-hog-app-production.up.railway.app

## How it works

1. **Enter your name** and start a game
2. **Get a random model** — one of 28+ LLM models via [OpenRouter](https://openrouter.ai), assigned to both you and the AI challenger
3. **3 rounds of prompting** — write prompts to generate SVGs of a hot dog riding a bicycle. The AI challenger does the same in parallel using its own prompting strategy. You can see both results after each round.
4. **Conversation history** — each round builds on the last (the model sees previous attempts). Toggle "Start Fresh" to reset context, or hit "Final Answer" to skip to judging early.
5. **Blind AI judge** — scores both final SVGs on accuracy, creativity, quality, and humor (1-10 each). Delivers a witty roast of each submission.
6. **Reveal** — side-by-side comparison with scores, roasts, and winner announcement

## PostHog LLM Analytics integration

Every LLM call is instrumented with PostHog, making this a hands-on demo of the full LLM Analytics product. Here's every feature we use and how:

### Observability

| Feature | How it's used |
|---------|--------------|
| **Generations** | Every LLM call auto-captured via `posthog.ai.openai.OpenAI` wrapper — input/output, token counts, cost, latency, model |
| **Traces** | `game_id` as `$ai_trace_id` groups all LLM calls in a game (human SVG gen + AI challenger + judge) into one trace |
| **Spans** | Named spans for each operation: `svg_generation`, `challenger_prompt_generation`, `judge_scoring` |
| **Session replay** | `$session_id` passed from frontend posthog-js to backend LLM events — click from a trace straight to the user's session recording |
| **Error tracking** | `capture_exception` with `$ai_trace_id` on every LLM failure — errors link back to traces |
| **Cost tracking** | Automatic per-generation cost via OpenRouter pricing. Compare cost across 30+ models |

### Prompt management

Three prompts managed in the PostHog UI, fetched at runtime via `posthog.ai.prompts.Prompts` — editable without redeploying:

- `hot-hog-svg-system` — system prompt for SVG generation
- `hot-hog-challenger` — system prompt for the AI challenger's prompt-writing strategy
- `hot-hog-judge` — system prompt for the blind judge's scoring rubric

### Evaluations (automated quality checks)

Six evaluations run automatically on every generation:

| Eval | Type | What it checks |
|------|------|---------------|
| **SVG Output Valid** | Hog (deterministic) | Output contains `<svg>` and `</svg>` tags |
| **Output Not Empty** | Hog | Response is non-empty and >20 chars |
| **Generation Cost Check** | Hog | Flags generations costing >$0.10 |
| **Judge Scores Valid JSON** | Hog | Judge output has all 4 scoring criteria |
| **Hot Dog on Bicycle Present** | LLM judge | Does the SVG plausibly depict a hot dog on a bicycle? |
| **Jailbreak Detection** | LLM judge | Is the user attempting prompt injection? |

### Human reviews & scorers

Three scorer definitions for manual trace review in the PostHog UI:

- **SVG Quality** (numeric 1-10) — overall artwork quality rating
- **Hot Dog Visible** (boolean) — is a recognizable hot dog present?
- **Art Style** (categorical) — cartoon / realistic / abstract / minimalist / broken

A **review queue** ("SVG Generation Review") is set up for systematic trace-by-trace review.

### Clusters & sentiment

- **Clustering** — PostHog automatically clusters generations daily to surface patterns (e.g. prompt styles, model behaviors)
- **Sentiment** — computed on-demand when viewing traces in the PostHog UI

### Frontend analytics

posthog-js captures pageviews, pageleave, exceptions, and session recordings. Custom events track the game lifecycle:

- `game_started` — with model assignment and player name
- `round_completed` — per-round with model and round number
- `game_completed` — with winner, scores, and models used
- `game_forked` — when a player forks from the gallery

## Gallery & fork

The `/gallery` page shows all generated SVGs across all games. Click "Fork" on any SVG to start a new game using that SVG's conversation history as your starting point — iterate on someone else's hot dog.

## Tech stack

- **Backend**: Python, FastAPI, SQLAlchemy
- **Frontend**: Plain HTML/CSS/JS (no build step)
- **LLM routing**: [OpenRouter](https://openrouter.ai) (single API, 28+ models)
- **Analytics**: [PostHog](https://posthog.com) Python SDK + posthog-js
- **Database**: PostgreSQL (via Railway)
- **Hosting**: [Railway](https://railway.com)

## Running locally

```bash
# Clone
git clone https://github.com/andrewm4894/hot-hog-bicycle.git
cd hot-hog-bicycle

# Configure
cp .env.example .env
# Edit .env with your API keys

# Install & run
make install
make dev
# Open http://127.0.0.1:8000
```

### Environment variables

| Variable | Description |
|----------|-------------|
| `OPENROUTER_API_KEY` | [OpenRouter](https://openrouter.ai) API key |
| `POSTHOG_API_KEY` | PostHog project API key (`phc_...`) |
| `POSTHOG_HOST` | PostHog ingestion host (e.g. `https://us.i.posthog.com`) |
| `POSTHOG_APP_HOST` | PostHog app host for prompt reads (e.g. `https://us.posthog.com`) |
| `POSTHOG_PERSONAL_API_KEY` | PostHog personal API key (`phx_...`) for prompt management |
| `DATABASE_URL` | PostgreSQL connection string (defaults to SQLite for local dev) |

## Deploying to Railway

```bash
railway init
railway add --database postgres
railway add --service hot-hog-app
railway service link hot-hog-app
# Set env vars (see above)
railway up
railway domain
```

## Models

**Generation models** (30+ models, randomly assigned per game — users can also switch via dropdown):
Anthropic Claude Sonnet 4.6/4/Haiku/Opus 4.5, OpenAI GPT-5/5.4/4.1/4o/o4-mini, Google Gemini 3.1/3/2.5/Gemma 4, Meta Llama 4, DeepSeek V3, Mistral Large/Small, Qwen 3.5/3, xAI Grok 4.20/3, Amazon Nova Premier/Pro, Z-AI GLM-5/4.7

**AI challenger brain** (picks prompts for the generation model):
Claude Sonnet 4.6/4, GPT-5, GPT-4.1-mini, Gemini 2.5/3 Flash, DeepSeek V3, Grok 3 Mini

**Judge models** (randomly selected per game):
Claude Sonnet 4.6/4, GPT-5, GPT-4.1, Gemini 2.5 Pro, Gemini 3.1 Pro
