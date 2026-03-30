import os
from dotenv import load_dotenv

load_dotenv()

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

POSTHOG_API_KEY = os.getenv("POSTHOG_API_KEY", "")
POSTHOG_HOST = os.getenv("POSTHOG_HOST", "https://us.i.posthog.com")
POSTHOG_APP_HOST = os.getenv("POSTHOG_APP_HOST", "https://us.posthog.com")
POSTHOG_PERSONAL_API_KEY = os.getenv("POSTHOG_PERSONAL_API_KEY", "")

JUDGE_MODEL = os.getenv("JUDGE_MODEL", "anthropic/claude-sonnet-4")

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./hot_hog.db")
# Railway uses ephemeral filesystem — SQLite is fine for a conference demo.
# For persistence across deploys, set DATABASE_URL to a Postgres connection string.

# Models that are known to produce decent SVG output.
# These get randomly assigned to both the human and AI challenger.
# Verified against OpenRouter /api/v1/models as of 2026-03-30.
GENERATION_MODELS = [
    # Anthropic
    "anthropic/claude-sonnet-4",
    "anthropic/claude-sonnet-4.5",
    "anthropic/claude-haiku-4.5",
    # OpenAI
    "openai/gpt-4o",
    "openai/gpt-4o-mini",
    "openai/gpt-4.1",
    "openai/gpt-4.1-mini",
    "openai/gpt-5",
    "openai/o4-mini",
    # Google
    "google/gemini-2.5-flash",
    "google/gemini-2.5-pro",
    "google/gemini-2.0-flash-001",
    "google/gemini-3-flash-preview",
    # Meta
    "meta-llama/llama-4-maverick",
    "meta-llama/llama-4-scout",
    # DeepSeek
    "deepseek/deepseek-chat-v3-0324",
    "deepseek/deepseek-v3.2",
    # Mistral
    "mistralai/mistral-large-2512",
    "mistralai/mistral-small-2603",
    # Qwen
    "qwen/qwen3-235b-a22b",
    "qwen/qwen3-32b",
    # xAI
    "x-ai/grok-3-mini",
    # Amazon
    "amazon/nova-pro-v1",
]

# Capable models used as the AI challenger's "brain" — it uses this model
# to craft prompts that get sent to the generation model.
CHALLENGER_MODELS = [
    "anthropic/claude-sonnet-4",
    "openai/gpt-4o",
    "openai/gpt-4.1-mini",
    "google/gemini-2.5-flash",
    "google/gemini-2.0-flash-001",
    "deepseek/deepseek-chat-v3-0324",
    "x-ai/grok-3-mini",
]

ROUNDS_PER_GAME = 3
