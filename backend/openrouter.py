import logging
import re

from posthog.ai.openai import OpenAI

from .config import OPENROUTER_API_KEY, OPENROUTER_BASE_URL
from .posthog_setup import posthog_client, prompts

log = logging.getLogger("hot-hog")

# Single OpenAI-compatible client pointed at OpenRouter,
# wrapped with PostHog's AI wrapper for automatic LLM Analytics.
client = OpenAI(
    api_key=OPENROUTER_API_KEY,
    base_url=OPENROUTER_BASE_URL,
    posthog_client=posthog_client,
    default_headers={
        "HTTP-Referer": "https://posthog.com",
        "X-Title": "Hot Hog on a Bicycle",
    },
)

SVG_PATTERN = re.compile(r"<svg[\s\S]*?</svg>", re.IGNORECASE)

# Hardcoded fallback in case PostHog prompt fetch fails
_SVG_SYSTEM_FALLBACK = (
    "You are an SVG artist. When asked to draw something, "
    "respond with a single SVG image wrapped in <svg>...</svg> tags. "
    "Use a viewBox of '0 0 400 400'. Make it colorful and fun. "
    "Only output the SVG, no other text."
)


def generate_svg(
    model: str,
    prompt: str,
    *,
    history: list[dict] | None = None,
    trace_id: str | None = None,
    distinct_id: str = "anonymous",
    properties: dict | None = None,
) -> tuple[str | None, str]:
    """
    Send a prompt to a model via OpenRouter and extract SVG from the response.
    Optionally includes conversation history from previous rounds so the model
    can iteratively refine.

    history: list of {"prompt": str, "svg": str|None} from previous rounds.

    Returns (svg_content, raw_response_text).
    svg_content is None if no valid SVG was found.
    """
    ph_props = properties or {}

    system_prompt = prompts.get("hot-hog-svg-system", fallback=_SVG_SYSTEM_FALLBACK)

    messages = [{"role": "system", "content": system_prompt}]

    # Build conversation from previous rounds
    if history:
        for prev in history:
            messages.append({"role": "user", "content": prev["prompt"]})
            if prev.get("svg"):
                messages.append({"role": "assistant", "content": prev["svg"]})
            else:
                messages.append({"role": "assistant", "content": "(failed to generate valid SVG)"})

    messages.append({"role": "user", "content": prompt})

    try:
        response = client.chat.completions.create(
            model=model,
            messages=messages,
            max_tokens=4096,
            posthog_distinct_id=distinct_id,
            posthog_trace_id=trace_id,
            posthog_properties={
                "$ai_span_name": "svg_generation",
                "$ai_prompt_name": "hot-hog-svg-system",
                "$ai_session_id": trace_id,
                **ph_props,
            },
        )

        raw_text = response.choices[0].message.content or ""
        match = SVG_PATTERN.search(raw_text)
        svg = match.group(0) if match else None
        return svg, raw_text

    except Exception as e:
        log.error("SVG generation failed: %s", e)
        posthog_client.capture_exception(
            e,
            distinct_id=distinct_id,
            properties={
                "$ai_trace_id": trace_id,
                "model": model,
                "stage": "svg_generation",
                **ph_props,
            },
        )
        return None, f"Error: {e}"


def chat_completion(
    model: str,
    messages: list[dict],
    *,
    trace_id: str | None = None,
    distinct_id: str = "anonymous",
    span_name: str = "chat",
    prompt_name: str | None = None,
    properties: dict | None = None,
) -> str:
    """
    General chat completion via OpenRouter with PostHog tracing.
    Used for the challenger agent and the judge.
    """
    ph_props = properties or {}
    if prompt_name:
        ph_props["$ai_prompt_name"] = prompt_name

    try:
        response = client.chat.completions.create(
            model=model,
            messages=messages,
            max_tokens=4096,
            posthog_distinct_id=distinct_id,
            posthog_trace_id=trace_id,
            posthog_properties={
                "$ai_span_name": span_name,
                "$ai_session_id": trace_id,
                **ph_props,
            },
        )

        return response.choices[0].message.content or ""

    except Exception as e:
        log.error("Chat completion failed (%s): %s", span_name, e)
        posthog_client.capture_exception(
            e,
            distinct_id=distinct_id,
            properties={
                "$ai_trace_id": trace_id,
                "model": model,
                "stage": span_name,
                **ph_props,
            },
        )
        raise
