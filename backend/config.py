import os
from dotenv import load_dotenv

load_dotenv()

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

# Public base URL the app is served from — used to build `game_url` custom
# properties on LLM events so PostHog traces can link back to the game page.
APP_BASE_URL = os.getenv("APP_BASE_URL", "https://hot-hog-app-production.up.railway.app")

POSTHOG_API_KEY = os.getenv("POSTHOG_API_KEY", "")
POSTHOG_HOST = os.getenv("POSTHOG_HOST", "https://us.i.posthog.com")
POSTHOG_APP_HOST = os.getenv("POSTHOG_APP_HOST", "https://us.posthog.com")
POSTHOG_PERSONAL_API_KEY = os.getenv("POSTHOG_PERSONAL_API_KEY", "")

JUDGE_MODEL = os.getenv("JUDGE_MODEL", "")  # If empty, randomly chosen from JUDGE_MODELS

JUDGE_MODELS = [
    "anthropic/claude-sonnet-4.6",
    "anthropic/claude-sonnet-4",
    "openai/gpt-5",
    "openai/gpt-4.1",
    "google/gemini-2.5-pro",
    "google/gemini-3.1-pro-preview",
]

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./hot_hog.db")
# Railway uses ephemeral filesystem — SQLite is fine for a conference demo.
# For persistence across deploys, set DATABASE_URL to a Postgres connection string.

# Models that are known to produce decent SVG output.
# These get randomly assigned to both the human and AI challenger.
# Verified against OpenRouter /api/v1/models as of 2026-03-30.
GENERATION_MODELS = [
    # Anthropic
    "anthropic/claude-sonnet-4.6",
    "anthropic/claude-sonnet-4",
    "anthropic/claude-haiku-4.5",
    "anthropic/claude-opus-4.5",
    # OpenAI
    "openai/gpt-5",
    "openai/gpt-5.4",
    "openai/gpt-5.4-mini",
    "openai/gpt-4.1",
    "openai/gpt-4.1-mini",
    "openai/gpt-4o",
    "openai/o4-mini",
    # Google
    "google/gemini-3.1-pro-preview",
    "google/gemini-3-flash-preview",
    "google/gemini-2.5-pro",
    "google/gemini-2.5-flash",
    "google/gemma-4-31b-it",
    # Meta
    "meta-llama/llama-4-maverick",
    "meta-llama/llama-4-scout",
    # DeepSeek
    "deepseek/deepseek-v3.2",
    "deepseek/deepseek-chat-v3-0324",
    # Mistral
    "mistralai/mistral-large-2512",
    "mistralai/mistral-small-2603",
    # Qwen
    "qwen/qwen3.5-122b-a10b",
    "qwen/qwen3.5-27b",
    "qwen/qwen3-235b-a22b",
    # xAI
    "x-ai/grok-4.20",
    "x-ai/grok-3-mini",
    # Amazon
    "amazon/nova-premier-v1",
    "amazon/nova-pro-v1",
    # Z-AI (GLM)
    "z-ai/glm-5",
    "z-ai/glm-4.7",
]

# Capable models used as the AI challenger's "brain" — it uses this model
# to craft prompts that get sent to the generation model.
CHALLENGER_MODELS = [
    "anthropic/claude-sonnet-4.6",
    "anthropic/claude-sonnet-4",
    "openai/gpt-5",
    "openai/gpt-4.1-mini",
    "google/gemini-2.5-flash",
    "google/gemini-3-flash-preview",
    "deepseek/deepseek-v3.2",
    "x-ai/grok-3-mini",
]

ROUNDS_PER_GAME = 3

# Models known to support OpenAI-style function/tool calling on OpenRouter.
# The challenger and judge only get `tools=[...]` if their assigned model
# is in this set — for others we fall back to a plain chat completion.
TOOL_CAPABLE_MODELS = {
    # Anthropic
    "anthropic/claude-sonnet-4.6",
    "anthropic/claude-sonnet-4",
    "anthropic/claude-haiku-4.5",
    "anthropic/claude-opus-4.5",
    # OpenAI
    "openai/gpt-5",
    "openai/gpt-5.4",
    "openai/gpt-5.4-mini",
    "openai/gpt-4.1",
    "openai/gpt-4.1-mini",
    "openai/gpt-4o",
    "openai/o4-mini",
    # Google
    "google/gemini-3.1-pro-preview",
    "google/gemini-3-flash-preview",
    "google/gemini-2.5-pro",
    "google/gemini-2.5-flash",
    # xAI
    "x-ai/grok-4.20",
    "x-ai/grok-3-mini",
    # DeepSeek
    "deepseek/deepseek-v3.2",
}
