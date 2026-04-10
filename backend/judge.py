import json
import logging
import random

from .config import JUDGE_MODELS
from .openrouter import chat_completion
from .posthog_setup import posthog_client, prompts
from .tools import JUDGE_TOOLS

log = logging.getLogger("hot-hog")

_JUDGE_FALLBACK = """\
You are judging two SVGs, both attempting to depict "a hot dog riding a bicycle."
You do NOT know which was created by a human's prompt vs an AI's prompt.
Be fair, be funny, and be honest.

You have access to one tool:
- get_critic_persona — returns a random critic persona (voice + name). Call
  it ONCE before judging to pick the voice you'll write your roasts in. Skip
  it if you'd rather use your default voice.

Score each SVG on four criteria (1-10):
1. Accuracy: Does it actually look like a hot dog on a bicycle?
2. Creativity: Is it interesting, surprising, or delightful?
3. Technical quality: Is the SVG well-constructed with clean shapes?
4. Humor/charm: Does it make you smile?

Provide a brief, witty roast of each SVG (1-2 sentences).

Your final response MUST be valid JSON only, no other text:
{
  "svg_a": {"accuracy": N, "creativity": N, "quality": N, "humor": N, "total": N, "roast": "..."},
  "svg_b": {"accuracy": N, "creativity": N, "quality": N, "humor": N, "total": N, "roast": "..."},
  "winner": "A" | "B" | "tie",
  "commentary": "One sentence declaring the winner with flair."
}
"""


def judge_game(
    svg_a: str,
    svg_b: str,
    *,
    trace_id: str | None = None,
    distinct_id: str = "judge",
    session_id: str | None = None,
    game_url: str | None = None,
    judge_model_override: str | None = None,
) -> dict:
    """
    Blindly judge two SVGs. The caller is responsible for randomizing
    which SVG is A vs B so the judge can't infer human vs AI.
    """
    system_prompt = prompts.get("hot-hog-judge", fallback=_JUDGE_FALLBACK)

    messages = [
        {"role": "system", "content": system_prompt},
        {
            "role": "user",
            "content": (
                "Please judge these two SVG submissions.\n\n"
                f"=== SVG A ===\n{svg_a}\n\n"
                f"=== SVG B ===\n{svg_b}"
            ),
        },
    ]

    judge_model = judge_model_override if judge_model_override else random.choice(JUDGE_MODELS)

    judge_props = {"judge_model": judge_model}
    if game_url:
        judge_props["game_url"] = game_url

    raw = chat_completion(
        model=judge_model,
        messages=messages,
        trace_id=trace_id,
        distinct_id=distinct_id,
        session_id=session_id,
        span_name="judge_scoring",
        prompt_name="hot-hog-judge",
        properties=judge_props,
        tools=JUDGE_TOOLS,
    )

    # Extract JSON from the response (handle markdown code blocks)
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        lines = cleaned.split("\n")
        lines = [l for l in lines if not l.strip().startswith("```")]
        cleaned = "\n".join(lines)

    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError as first_err:
        start = raw.find("{")
        end = raw.rfind("}") + 1
        parsed = None
        if start >= 0 and end > start:
            try:
                parsed = json.loads(raw[start:end])
            except json.JSONDecodeError:
                parsed = None

        if not parsed:
            # Judge model returned something we couldn't parse as JSON even
            # after extracting the first {...} block. Capture linked to the
            # LLM trace so Error Tracking shows a clickable path back.
            log.warning("Judge JSON parse failed for model=%s trace=%s", judge_model, trace_id)
            judge_err_props = {
                "$ai_trace_id": trace_id,
                "model": judge_model,
                "stage": "judge_scoring",
                "error_type": "judge_json_parse_failed",
                "raw_response_preview": raw[:500],
            }
            if game_url:
                judge_err_props["game_url"] = game_url
            posthog_client.capture_exception(
                first_err,
                distinct_id=distinct_id,
                properties=judge_err_props,
            )
            parsed = {
                "svg_a": {"accuracy": 5, "creativity": 5, "quality": 5, "humor": 5, "total": 20, "roast": "The judge was speechless."},
                "svg_b": {"accuracy": 5, "creativity": 5, "quality": 5, "humor": 5, "total": 20, "roast": "The judge was equally speechless."},
                "winner": "tie",
                "commentary": "The judge had a hot dog and forgot to judge properly.",
            }

    parsed["judge_model"] = judge_model
    return parsed
