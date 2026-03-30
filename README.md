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

Every LLM call is instrumented with PostHog, making this a hands-on demo of the full LLM Analytics product:

| Feature | How it's used |
|---------|--------------|
| **Traces** | Full game trace: human prompts, AI challenger prompts, judge scoring |
| **Spans** | Individual operations: `svg_generation`, `challenger_prompt_generation`, `judge_scoring` |
| **Generations** | Every LLM call with input/output, tokens, cost, latency |
| **Sessions** | `$ai_session_id` groups all traces within a game |
| **Prompt management** | 3 prompts managed in PostHog UI (`hot-hog-svg-system`, `hot-hog-challenger`, `hot-hog-judge`) — editable without redeploying |
| **Session replay** | `$session_id` links backend LLM events to frontend session recordings |
| **Error tracking** | Exceptions captured with `$ai_trace_id` for click-through from errors to traces |
| **Cost tracking** | Per-game, per-model cost comparison across 28+ models |

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
| `JUDGE_MODEL` | Model used for blind judging (default: `anthropic/claude-sonnet-4`) |
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

**Generation models** (randomly assigned per game):
Anthropic Claude Sonnet/Haiku, OpenAI GPT-4o/4.1/5/o4-mini, Google Gemini 2.0/2.5/3, Meta Llama 4, DeepSeek V3, Mistral Large, Qwen3, Grok 3, Amazon Nova Pro

**AI challenger brain** (picks prompts for the generation model):
Claude Sonnet 4, GPT-4o, GPT-4.1-mini, Gemini 2.5 Flash, Gemini 2.0 Flash, DeepSeek V3, Grok 3 Mini
