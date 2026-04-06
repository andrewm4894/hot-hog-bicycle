"""
Auto-play a full game for continuous LLM analytics data.
Run as: uv run python -m backend.autoplay
"""

import random
import time
import logging

from .config import GENERATION_MODELS
from .game import create_game, play_human_round, judge_and_reveal
from .posthog_setup import posthog_client

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger("autoplay")

BOT_NAMES = [
    "AutoHog", "SausageBot", "BunRunner", "MustardAI",
    "KetchupKid", "WienerWiz", "FrankFurter", "RelishRobot",
    "HotDogHero", "GrillMaster", "BicycleBot", "PedalPusher",
]

PROMPTS_ROUND_1 = [
    "Draw a cute hot dog with mustard riding a red bicycle through a sunny park",
    "A cheerful frankfurter in a bun pedaling a vintage bicycle, cartoon style",
    "Hot dog character with arms and legs cycling on a mountain bike, colorful SVG",
    "A sausage in a bun riding a bicycle with spinning wheels, simple and fun",
    "Funny hot dog with sunglasses riding a racing bicycle, vibrant colors",
    "A wiener on a tandem bicycle with a bottle of ketchup, whimsical style",
]

PROMPTS_ROUND_2 = [
    "Make the hot dog bigger and add more detail to the bicycle wheels with spokes",
    "Add a helmet on the hot dog and make the bicycle red, improve proportions",
    "Make it more detailed — add a background with clouds and a road",
    "Improve the colors, add mustard dripping, make wheels rounder",
    "Add motion lines to show speed, make the hot dog look determined",
    "Make the bun more realistic with sesame seeds, add pedals to the bike",
]

PROMPTS_ROUND_3 = [
    "Final version: polish everything, make colors pop, ensure hot dog is clearly on the bicycle",
    "Clean up the SVG, make sure proportions are right, add a fun expression on the hot dog",
    "Make it look professional — clean lines, good viewBox usage, vibrant but harmonious colors",
    "Final polish: add a shadow under the bicycle, make the hot dog smile, clean shapes",
    "Last attempt: make it the best SVG possible, focus on clarity and charm",
    "Refine everything — the hot dog should look happy and the bicycle should be recognizable",
]


def play_auto_game():
    name = random.choice(BOT_NAMES)
    model = random.choice(GENERATION_MODELS)
    log.info(f"Starting auto-game: player={name}, model={model}")

    result = create_game(name)
    game_id = result["game_id"]
    log.info(f"Game created: {game_id} (model: {result['generation_model']})")

    prompt_sets = [PROMPTS_ROUND_1, PROMPTS_ROUND_2, PROMPTS_ROUND_3]

    for round_num, prompts in enumerate(prompt_sets, 1):
        prompt = random.choice(prompts)
        log.info(f"Round {round_num}: {prompt[:60]}...")

        try:
            round_result = play_human_round(game_id, prompt)
            has_svg = bool(round_result.get("human_svg"))
            log.info(f"Round {round_num} done: human_svg={'yes' if has_svg else 'no'}")
        except Exception as e:
            log.error(f"Round {round_num} failed: {e}")
            continue

        time.sleep(2)

    log.info("Judging game...")
    try:
        judge_result = judge_and_reveal(game_id)
        log.info(
            f"Game {game_id} complete: winner={judge_result['winner']}, "
            f"human={judge_result['human']['scores'].get('total', '?')}/40, "
            f"ai={judge_result['ai']['scores'].get('total', '?')}/40"
        )
    except Exception as e:
        log.error(f"Judging failed: {e}")

    posthog_client.flush()
    log.info("Done")


if __name__ == "__main__":
    play_auto_game()
