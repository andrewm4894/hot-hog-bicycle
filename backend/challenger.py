from .config import ROUNDS_PER_GAME
from .openrouter import chat_completion, generate_svg
from .posthog_setup import prompts
from .tools import CHALLENGER_TOOLS

_CHALLENGER_FALLBACK = """\
You are competing to create the best SVG of a hot dog riding a bicycle.
You have 3 attempts. Each round, you write a prompt that will be sent to an SVG-generating model.
Your goal is to craft prompts that produce an accurate, creative, and visually appealing SVG.

You have access to brainstorming tools:
- get_hot_dog_fact / get_bicycle_fact — grab real-world trivia to ground your prompt
- get_art_style — commit to a specific visual style
- get_color_palette — get a themed hex palette
- get_composition_idea — get a camera angle / framing suggestion

Call any tools you think will help, then write the final prompt. You don't
have to use tools — skip them if you already know what you want.

Tips for good prompts:
- Be specific about colors, proportions, and spatial relationships
- Describe the hot dog's posture on the bicycle
- Mention details like wheels, handlebars, mustard, ketchup, bun texture
- Think about what makes SVG art look good (clean shapes, good use of viewBox)
- Each round, refine based on what worked or didn't in the previous SVG

Your final response must be ONLY the prompt text, nothing else. No quotes, no explanation.
"""


def _get_challenger_system_prompt() -> str:
    template = prompts.get("hot-hog-challenger", fallback=_CHALLENGER_FALLBACK)
    return prompts.compile(template, {"total_rounds": str(ROUNDS_PER_GAME)})


def generate_challenger_prompt(
    challenger_model: str,
    round_number: int,
    previous_rounds: list[dict],
    *,
    trace_id: str | None = None,
    distinct_id: str = "ai-challenger",
) -> str:
    """
    Use the challenger model to craft a prompt for the generation model.
    The challenger sees its previous prompts and SVG results to iterate.
    """
    system_prompt = _get_challenger_system_prompt()
    messages = [{"role": "system", "content": system_prompt}]

    if not previous_rounds:
        messages.append({
            "role": "user",
            "content": (
                f"Round {round_number}/{ROUNDS_PER_GAME}. Write your first prompt to generate "
                "an SVG of a hot dog riding a bicycle."
            ),
        })
    else:
        history = ""
        for r in previous_rounds:
            history += f"\n--- Round {r['round']} ---\n"
            history += f"Your prompt: {r['prompt']}\n"
            if r.get("svg"):
                svg_preview = r["svg"][:2000] + ("..." if len(r["svg"]) > 2000 else "")
                history += f"Resulting SVG:\n{svg_preview}\n"
            else:
                history += "Result: Failed to generate valid SVG.\n"

        messages.append({
            "role": "user",
            "content": (
                f"Round {round_number}/{ROUNDS_PER_GAME}. Here are your previous attempts:\n"
                f"{history}\n\n"
                "Now write an improved prompt. Focus on what could be better."
            ),
        })

    prompt = chat_completion(
        model=challenger_model,
        messages=messages,
        trace_id=trace_id,
        distinct_id=distinct_id,
        span_name="challenger_prompt_generation",
        prompt_name="hot-hog-challenger",
        properties={
            "round_number": round_number,
            "challenger_model": challenger_model,
        },
        tools=CHALLENGER_TOOLS,
    )

    return prompt.strip().strip('"').strip("'")


def run_challenger_round(
    challenger_model: str,
    generation_model: str,
    round_number: int,
    previous_rounds: list[dict],
    *,
    generation_history: list[dict] | None = None,
    trace_id: str | None = None,
) -> dict:
    """
    Run one round for the AI challenger:
    1. Generate a prompt using the challenger model
    2. Send that prompt to the generation model for SVG output (with history)
    """
    prompt = generate_challenger_prompt(
        challenger_model=challenger_model,
        round_number=round_number,
        previous_rounds=previous_rounds,
        trace_id=trace_id,
    )

    svg, raw = generate_svg(
        model=generation_model,
        prompt=prompt,
        history=generation_history,
        trace_id=trace_id,
        distinct_id="ai-challenger",
        properties={
            "round_number": round_number,
            "is_human": False,
            "challenger_model": challenger_model,
        },
    )

    return {
        "round": round_number,
        "prompt": prompt,
        "svg": svg,
        "raw_response": raw,
    }
