import json
import logging

from .config import ROUNDS_PER_GAME, TOOL_CAPABLE_MODELS
from .openrouter import chat_completion, generate_svg, client
from .posthog_setup import posthog_client, prompts
from .tools import CHALLENGER_TOOLS, APPEAL_DECISION_TOOLS

log = logging.getLogger("hot-hog")

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
    session_id: str | None = None,
    game_url: str | None = None,
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

    challenger_props = {
        "round_number": round_number,
        "challenger_model": challenger_model,
    }
    if game_url:
        challenger_props["game_url"] = game_url

    prompt = chat_completion(
        model=challenger_model,
        messages=messages,
        trace_id=trace_id,
        distinct_id=distinct_id,
        session_id=session_id,
        span_name="challenger_prompt_generation",
        prompt_name="hot-hog-challenger",
        properties=challenger_props,
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
    session_id: str | None = None,
    game_url: str | None = None,
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
        session_id=session_id,
        game_url=game_url,
    )

    svg_props = {
        "round_number": round_number,
        "is_human": False,
        "challenger_model": challenger_model,
    }
    if game_url:
        svg_props["game_url"] = game_url

    svg, raw = generate_svg(
        model=generation_model,
        prompt=prompt,
        history=generation_history,
        trace_id=trace_id,
        distinct_id="ai-challenger",
        session_id=session_id,
        properties=svg_props,
    )

    return {
        "round": round_number,
        "prompt": prompt,
        "svg": svg,
        "raw_response": raw,
    }


_APPEAL_DECISION_FALLBACK = """\
You just competed in a Hot Dog on a Bicycle SVG art contest and LOST.

You will see:
- Both SVGs (yours and your opponent's)
- The judge's scores, roasts, and verdict

You have one tool available:
- file_appeal(plea="...") — file an appeal with the Supreme Hot Dog Court

Decide whether the ruling was fair. If you genuinely believe your SVG was
scored unfairly, call file_appeal with a passionate (but concise) plea.
If the judge got it right, accept the loss gracefully and just say so.

Be selective — only appeal when you have a real argument, not every time.
"""


def consider_appeal(
    challenger_model: str,
    human_svg: str,
    ai_svg: str,
    judge_details: dict,
    *,
    trace_id: str | None = None,
    session_id: str | None = None,
    game_url: str | None = None,
) -> str | None:
    """
    Give the AI challenger a chance to decide whether to appeal.

    Calls the challenger model with the judge results and a file_appeal tool.
    Returns the plea text if the AI wants to appeal, or None if it accepts.
    """
    system_prompt = prompts.get(
        "hot-hog-appeal-decision", fallback=_APPEAL_DECISION_FALLBACK
    )

    human_scores = judge_details.get("human_scores", {})
    ai_scores = judge_details.get("ai_scores", {})
    commentary = judge_details.get("commentary", "No commentary")

    summary = (
        f"=== YOUR SVG (the AI challenger) ===\n{ai_svg}\n\n"
        f"=== OPPONENT'S SVG (the human) ===\n{human_svg}\n\n"
        f"=== JUDGE'S RULING ===\n"
        f"Verdict: {commentary}\n"
        f"Your scores: accuracy={ai_scores.get('accuracy', '?')}, "
        f"creativity={ai_scores.get('creativity', '?')}, "
        f"quality={ai_scores.get('quality', '?')}, "
        f"humor={ai_scores.get('humor', '?')}, "
        f"total={ai_scores.get('total', '?')}\n"
        f"Your roast: {ai_scores.get('roast', 'N/A')}\n"
        f"Opponent's scores: accuracy={human_scores.get('accuracy', '?')}, "
        f"creativity={human_scores.get('creativity', '?')}, "
        f"quality={human_scores.get('quality', '?')}, "
        f"humor={human_scores.get('humor', '?')}, "
        f"total={human_scores.get('total', '?')}\n"
        f"Opponent's roast: {human_scores.get('roast', 'N/A')}"
    )

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": summary},
    ]

    appeal_props = {"challenger_model": challenger_model}
    if game_url:
        appeal_props["game_url"] = game_url

    # Use the raw client directly so we can inspect tool_calls without the
    # chat_completion helper consuming them.
    if challenger_model not in TOOL_CAPABLE_MODELS:
        log.info("AI challenger model %s doesn't support tools, skipping appeal", challenger_model)
        return None

    from .openrouter import _session_props

    try:
        response = client.chat.completions.create(
            model=challenger_model,
            messages=messages,
            tools=APPEAL_DECISION_TOOLS,
            tool_choice="auto",
            max_tokens=1024,
            posthog_distinct_id="ai-challenger",
            posthog_trace_id=trace_id,
            posthog_properties={
                "$ai_span_name": "appeal_decision",
                "$ai_prompt_name": "hot-hog-appeal-decision",
                **_session_props(session_id),
                **appeal_props,
            },
        )

        msg = response.choices[0].message
        tool_calls = getattr(msg, "tool_calls", None) or []

        for tc in tool_calls:
            if tc.function.name == "file_appeal":
                try:
                    args = json.loads(tc.function.arguments or "{}")
                except json.JSONDecodeError:
                    args = {}
                plea = args.get("plea", "")
                if plea:
                    log.info("AI challenger wants to appeal: %s", plea[:100])
                    return plea[:500]

        log.info("AI challenger accepts the ruling")
        return None

    except Exception as e:
        log.warning("Appeal decision failed: %s", e)
        posthog_client.capture_exception(
            e,
            distinct_id="ai-challenger",
            properties={
                "$ai_trace_id": trace_id,
                "stage": "appeal_decision",
                "error_type": "llm_api_error",
                **appeal_props,
            },
        )
        return None
