import json
import random

from .config import JUDGE_MODEL, JUDGE_MODELS
from .openrouter import chat_completion
from .posthog_setup import prompts

_JUDGE_FALLBACK = """\
You are judging two SVGs, both attempting to depict "a hot dog riding a bicycle."
You do NOT know which was created by a human's prompt vs an AI's prompt.
Be fair, be funny, and be honest.

Score each SVG on four criteria (1-10):
1. Accuracy: Does it actually look like a hot dog on a bicycle?
2. Creativity: Is it interesting, surprising, or delightful?
3. Technical quality: Is the SVG well-constructed with clean shapes?
4. Humor/charm: Does it make you smile?

Provide a brief, witty roast of each SVG (1-2 sentences).

You MUST respond with valid JSON only, no other text:
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

    judge_model = JUDGE_MODEL if JUDGE_MODEL else random.choice(JUDGE_MODELS)

    raw = chat_completion(
        model=judge_model,
        messages=messages,
        trace_id=trace_id,
        distinct_id=distinct_id,
        span_name="judge_scoring",
        prompt_name="hot-hog-judge",
        properties={"judge_model": judge_model},
    )

    # Extract JSON from the response (handle markdown code blocks)
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        lines = cleaned.split("\n")
        lines = [l for l in lines if not l.strip().startswith("```")]
        cleaned = "\n".join(lines)

    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError:
        start = raw.find("{")
        end = raw.rfind("}") + 1
        if start >= 0 and end > start:
            try:
                parsed = json.loads(raw[start:end])
            except json.JSONDecodeError:
                parsed = None

        if not parsed:
            parsed = {
                "svg_a": {"accuracy": 5, "creativity": 5, "quality": 5, "humor": 5, "total": 20, "roast": "The judge was speechless."},
                "svg_b": {"accuracy": 5, "creativity": 5, "quality": 5, "humor": 5, "total": 20, "roast": "The judge was equally speechless."},
                "winner": "tie",
                "commentary": "The judge had a hot dog and forgot to judge properly.",
            }

    parsed["judge_model"] = judge_model
    return parsed
