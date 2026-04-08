import logging
import re

from posthog.ai.openai import OpenAI

from .config import OPENROUTER_API_KEY, OPENROUTER_BASE_URL, TOOL_CAPABLE_MODELS
from .posthog_setup import posthog_client, prompts
from .tools import execute_tool

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


def _session_props(session_id: str | None) -> dict:
    """
    Build the session-linking properties for an LLM event.

    `$session_id` links the event to the matching session replay (per
    https://posthog.com/docs/llm-analytics/link-session-replay).
    `$ai_session_id` groups multiple traces (games) by that same browser
    session in LLM Analytics.

    When `session_id` is None (e.g. autoplay bot with no browser session)
    we intentionally set neither — grouping by session isn't meaningful
    there, and an empty `$session_id` would pollute the replay link.
    """
    if not session_id:
        return {}
    return {
        "$session_id": session_id,
        "$ai_session_id": session_id,
    }


def generate_svg(
    model: str,
    prompt: str,
    *,
    history: list[dict] | None = None,
    trace_id: str | None = None,
    distinct_id: str = "anonymous",
    session_id: str | None = None,
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
                **_session_props(session_id),
                **ph_props,
            },
        )

        raw_text = response.choices[0].message.content or ""
        match = SVG_PATTERN.search(raw_text)
        svg = match.group(0) if match else None

        if svg is None:
            # API call succeeded but the model didn't produce a parseable
            # <svg>...</svg> block. Capture as an exception linked to the
            # LLM trace so it shows up in Error Tracking with a clickable
            # path back to the failing generation.
            err = ValueError("No <svg>...</svg> block found in model response")
            log.warning("SVG extraction failed for model=%s trace=%s", model, trace_id)
            posthog_client.capture_exception(
                err,
                distinct_id=distinct_id,
                properties={
                    "$ai_trace_id": trace_id,
                    "model": model,
                    "stage": "svg_generation",
                    "error_type": "svg_extraction_failed",
                    "raw_response_preview": raw_text[:500],
                    **_session_props(session_id),
                    **ph_props,
                },
            )

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
                "error_type": "llm_api_error",
                **_session_props(session_id),
                **ph_props,
            },
        )
        return None, f"Error: {e}"


MAX_TOOL_ITERATIONS = 5


def chat_completion(
    model: str,
    messages: list[dict],
    *,
    trace_id: str | None = None,
    distinct_id: str = "anonymous",
    session_id: str | None = None,
    span_name: str = "chat",
    prompt_name: str | None = None,
    properties: dict | None = None,
    tools: list | None = None,
) -> str:
    """
    General chat completion via OpenRouter with PostHog tracing.
    Used for the challenger agent and the judge.

    If `tools` is provided AND the model is in TOOL_CAPABLE_MODELS, we run a
    tool-use loop: up to MAX_TOOL_ITERATIONS turns where the model may call
    tools before producing its final text response. Each iteration is a
    separate `$ai_generation` event sharing the same trace_id, so PostHog's
    Tools tab auto-populates from `$ai_tools_called`.
    """
    ph_props = properties or {}
    if prompt_name:
        ph_props["$ai_prompt_name"] = prompt_name

    use_tools = bool(tools) and model in TOOL_CAPABLE_MODELS

    # Mutable working copy so we can append tool-call + tool-result turns
    working_messages = list(messages)

    try:
        for iteration in range(MAX_TOOL_ITERATIONS + 1):
            create_kwargs = dict(
                model=model,
                messages=working_messages,
                max_tokens=4096,
                posthog_distinct_id=distinct_id,
                posthog_trace_id=trace_id,
                posthog_properties={
                    "$ai_span_name": span_name,
                    "tool_loop_iteration": iteration,
                    **_session_props(session_id),
                    **ph_props,
                },
            )
            if use_tools:
                create_kwargs["tools"] = tools
                create_kwargs["tool_choice"] = "auto"

            response = client.chat.completions.create(**create_kwargs)
            msg = response.choices[0].message

            tool_calls = getattr(msg, "tool_calls", None) or []
            if not tool_calls:
                return msg.content or ""

            # Model wants to call one or more tools — append the assistant
            # turn (with tool_calls) and then each tool's result.
            working_messages.append({
                "role": "assistant",
                "content": msg.content or "",
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments or "{}",
                        },
                    }
                    for tc in tool_calls
                ],
            })
            for tc in tool_calls:
                result = execute_tool(tc.function.name, tc.function.arguments or "{}")
                working_messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": result,
                })

        # Iteration cap hit — nudge the model for a final text answer.
        log.warning("Tool loop hit max iterations for span=%s model=%s", span_name, model)
        working_messages.append({
            "role": "user",
            "content": "Stop calling tools. Now give me your final answer directly.",
        })
        final = client.chat.completions.create(
            model=model,
            messages=working_messages,
            max_tokens=4096,
            posthog_distinct_id=distinct_id,
            posthog_trace_id=trace_id,
            posthog_properties={
                "$ai_span_name": span_name,
                "tool_loop_iteration": "final_forced",
                **_session_props(session_id),
                **ph_props,
            },
        )
        return final.choices[0].message.content or ""

    except Exception as e:
        log.error("Chat completion failed (%s): %s", span_name, e)
        posthog_client.capture_exception(
            e,
            distinct_id=distinct_id,
            properties={
                "$ai_trace_id": trace_id,
                "model": model,
                "stage": span_name,
                "error_type": "llm_api_error",
                **_session_props(session_id),
                **ph_props,
            },
        )
        raise
