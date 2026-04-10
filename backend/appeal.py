"""
Supreme Court of Hot Dogs — the appeal judge.

When the losing side files an appeal, a *different* judge model reviews
ALL the evidence (both SVGs, the original scores + roasts, and the
appellant's written plea) and decides whether to uphold or overturn.
"""
import json
import logging
import random

from .config import JUDGE_MODELS
from .openrouter import chat_completion
from .posthog_setup import posthog_client, prompts
from .tools import JUDGE_TOOLS

log = logging.getLogger("hot-hog")

_APPEAL_FALLBACK = """\
You are the SUPREME JUDGE of the Hot Dog on a Bicycle appeal court.
An appeal has been filed against the original judge's ruling.

You will receive:
1. Both SVGs (A and B)
2. The original judge's scores, roasts, and verdict
3. The appellant's written plea explaining why the ruling was unfair

Your job:
- Review ALL evidence with fresh eyes
- Consider the appellant's arguments — are they valid?
- You may re-score if you believe the original judge made errors
- Be fair but also entertaining

You have access to one tool:
- get_critic_persona — returns a random critic persona. Call it ONCE
  before judging to pick the voice you'll write in.

Your final response MUST be valid JSON only, no other text:
{
  "verdict": "upheld" | "overturned",
  "svg_a": {"accuracy": N, "creativity": N, "quality": N, "humor": N, "total": N},
  "svg_b": {"accuracy": N, "creativity": N, "quality": N, "humor": N, "total": N},
  "new_winner": "A" | "B" | "tie",
  "reasoning": "2-3 sentences explaining your decision with flair and drama.",
  "response_to_appellant": "A direct, witty 1-2 sentence reply to the appellant's plea."
}
"""


def judge_appeal(
    svg_a: str,
    svg_b: str,
    original_scores: dict,
    appeal_text: str,
    appellant_side: str,
    *,
    trace_id: str | None = None,
    distinct_id: str = "appeal-judge",
    session_id: str | None = None,
    game_url: str | None = None,
    exclude_model: str | None = None,
) -> dict:
    """
    A supreme judge reviews the appeal. Uses a *different* model from the
    original judge to avoid bias.
    """
    system_prompt = prompts.get("hot-hog-appeal-judge", fallback=_APPEAL_FALLBACK)

    # Pick a different judge model than the original
    available = [m for m in JUDGE_MODELS if m != exclude_model]
    if not available:
        available = JUDGE_MODELS
    appeal_model = random.choice(available)

    original_summary = (
        f"Original verdict: {original_scores.get('commentary', 'No commentary')}\n"
        f"SVG A scores: accuracy={original_scores.get('human_scores', {}).get('accuracy', '?')}, "
        f"creativity={original_scores.get('human_scores', {}).get('creativity', '?')}, "
        f"quality={original_scores.get('human_scores', {}).get('quality', '?')}, "
        f"humor={original_scores.get('human_scores', {}).get('humor', '?')}, "
        f"total={original_scores.get('human_scores', {}).get('total', '?')}\n"
        f"SVG A roast: {original_scores.get('human_scores', {}).get('roast', 'N/A')}\n"
        f"SVG B scores: accuracy={original_scores.get('ai_scores', {}).get('accuracy', '?')}, "
        f"creativity={original_scores.get('ai_scores', {}).get('creativity', '?')}, "
        f"quality={original_scores.get('ai_scores', {}).get('quality', '?')}, "
        f"humor={original_scores.get('ai_scores', {}).get('humor', '?')}, "
        f"total={original_scores.get('ai_scores', {}).get('total', '?')}\n"
        f"SVG B roast: {original_scores.get('ai_scores', {}).get('roast', 'N/A')}"
    )

    messages = [
        {"role": "system", "content": system_prompt},
        {
            "role": "user",
            "content": (
                "An appeal has been filed. Please review all evidence.\n\n"
                f"=== SVG A ===\n{svg_a}\n\n"
                f"=== SVG B ===\n{svg_b}\n\n"
                f"=== ORIGINAL JUDGE'S RULING ===\n{original_summary}\n\n"
                f"=== APPEAL FROM THE {appellant_side.upper()} SIDE ===\n{appeal_text}"
            ),
        },
    ]

    appeal_props = {"appeal_judge_model": appeal_model}
    if game_url:
        appeal_props["game_url"] = game_url

    raw = chat_completion(
        model=appeal_model,
        messages=messages,
        trace_id=trace_id,
        distinct_id=distinct_id,
        session_id=session_id,
        span_name="appeal_scoring",
        prompt_name="hot-hog-appeal-judge",
        properties=appeal_props,
        tools=JUDGE_TOOLS,
    )

    # Parse JSON (same robust approach as judge.py)
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
            log.warning("Appeal JSON parse failed for model=%s trace=%s", appeal_model, trace_id)
            appeal_err_props = {
                "$ai_trace_id": trace_id,
                "model": appeal_model,
                "stage": "appeal_scoring",
                "error_type": "appeal_json_parse_failed",
                "raw_response_preview": raw[:500],
            }
            if game_url:
                appeal_err_props["game_url"] = game_url
            posthog_client.capture_exception(
                first_err,
                distinct_id=distinct_id,
                properties=appeal_err_props,
            )
            # Fallback: uphold original verdict
            parsed = {
                "verdict": "upheld",
                "svg_a": {"accuracy": 5, "creativity": 5, "quality": 5, "humor": 5, "total": 20},
                "svg_b": {"accuracy": 5, "creativity": 5, "quality": 5, "humor": 5, "total": 20},
                "new_winner": "tie",
                "reasoning": "The supreme judge got distracted eating a hot dog and upheld the original ruling by default.",
                "response_to_appellant": "Your plea was... interesting. But the original ruling stands.",
            }

    parsed["appeal_judge_model"] = appeal_model
    return parsed
