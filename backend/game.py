import json
import logging
import random
import threading
import uuid
import datetime
from concurrent.futures import ThreadPoolExecutor

from .config import APP_BASE_URL, GENERATION_MODELS, CHALLENGER_MODELS, JUDGE_MODELS, ROUNDS_PER_GAME
from .appeal import judge_appeal
from .models import SessionLocal, Game, Round
from .openrouter import generate_svg
from .challenger import run_challenger_round, consider_appeal
from .judge import judge_game
from .posthog_setup import posthog_client

log = logging.getLogger("hot-hog")


def _game_url(game_id: str) -> str:
    """Public URL for a game's results page, used as a `game_url` custom
    property on LLM events so PostHog traces link back to the game."""
    return f"{APP_BASE_URL.rstrip('/')}/results/{game_id}"


def create_game(player_name: str, session_id: str | None = None) -> dict:
    """Start a new game: pick random models, persist to DB."""
    game_id = uuid.uuid4().hex[:12]
    generation_model = random.choice(GENERATION_MODELS)
    challenger_model = random.choice(CHALLENGER_MODELS)
    judge_model = random.choice(JUDGE_MODELS)

    db = SessionLocal()
    try:
        game = Game(
            id=game_id,
            player_name=player_name,
            generation_model=generation_model,
            challenger_model=challenger_model,
            judge_model=judge_model,
            current_round=0,
        )
        db.add(game)
        db.commit()
    finally:
        db.close()

    # Explicit $ai_trace root event so the LLM Analytics trace list shows
    # "<player>-<model>" owned by the player, instead of the default
    # pseudo-trace named after whichever child span fires first.
    trace_props = {
        "$ai_trace_id": game_id,
        "$ai_span_name": f"{player_name}-{generation_model}",
        "game_id": game_id,
        "game_url": _game_url(game_id),
        "generation_model": generation_model,
        "challenger_model": challenger_model,
        "judge_model": judge_model,
    }
    if session_id:
        # Links the trace to the session replay and groups multiple games
        # by the same browser session in the LLM Analytics sessions view.
        trace_props["$session_id"] = session_id
        trace_props["$ai_session_id"] = session_id
    posthog_client.capture(
        distinct_id=player_name,
        event="$ai_trace",
        properties=trace_props,
    )

    props = {
        "game_id": game_id,
        "generation_model": generation_model,
        "challenger_model": challenger_model,
        "judge_model": judge_model,
        "$ai_trace_id": game_id,
    }
    if session_id:
        props["$session_id"] = session_id

    posthog_client.capture(
        distinct_id=player_name,
        event="game_started",
        properties=props,
    )

    return {
        "game_id": game_id,
        "generation_model": generation_model,
        "challenger_model": challenger_model,
        "judge_model": judge_model,
        "rounds_total": ROUNDS_PER_GAME,
    }


def play_human_round(game_id: str, prompt: str, fresh_start: bool = False, session_id: str | None = None, model_override: str | None = None) -> dict:
    """
    Handle one human round:
    1. Generate SVG from the human's prompt
    2. Run the AI challenger's round in parallel
    3. Persist both to DB
    """
    db = SessionLocal()
    try:
        game = db.query(Game).filter(Game.id == game_id).first()
        if not game:
            raise ValueError(f"Game {game_id} not found")

        total_rounds = game.rounds_total or ROUNDS_PER_GAME
        round_number = game.current_round + 1
        if round_number > total_rounds:
            raise ValueError("All rounds already played")

        trace_id = game_id

        # Gather history for both tracks before spawning threads
        prev_human_rounds = (
            db.query(Round)
            .filter(Round.game_id == game_id, Round.is_human == True)
            .order_by(Round.round_number)
            .all()
        )
        prev_ai_rounds = (
            db.query(Round)
            .filter(Round.game_id == game_id, Round.is_human == False)
            .order_by(Round.round_number)
            .all()
        )

        # Conversation history for the generation model (prompt + SVG pairs)
        human_gen_history = [
            {"prompt": r.prompt_text, "svg": r.svg_output}
            for r in prev_human_rounds
        ] if not fresh_start else []

        ai_challenger_history = [
            {"round": r.round_number, "prompt": r.prompt_text, "svg": r.svg_output}
            for r in prev_ai_rounds
        ]
        ai_gen_history = [
            {"prompt": r.prompt_text, "svg": r.svg_output}
            for r in prev_ai_rounds
        ]

        # Capture values before threading (avoid lazy-load issues)
        if model_override and model_override in GENERATION_MODELS:
            game.generation_model = model_override
            db.commit()
        gen_model = game.generation_model
        chal_model = game.challenger_model
        player_name = game.player_name

        # Run human SVG gen and AI challenger in parallel
        game_url = _game_url(game_id)
        with ThreadPoolExecutor(max_workers=2) as pool:
            round_props = {
                "game_id": game_id,
                "game_url": game_url,
                "round_number": round_number,
            }
            if session_id:
                round_props["$session_id"] = session_id

            human_future = pool.submit(
                generate_svg,
                model=gen_model,
                prompt=prompt,
                history=human_gen_history,
                trace_id=trace_id,
                distinct_id=player_name,
                session_id=session_id,
                properties={**round_props, "is_human": True},
            )
            ai_future = pool.submit(
                run_challenger_round,
                challenger_model=chal_model,
                generation_model=gen_model,
                round_number=round_number,
                previous_rounds=ai_challenger_history,
                generation_history=ai_gen_history,
                trace_id=trace_id,
                session_id=session_id,
                game_url=game_url,
            )

            human_svg, human_raw = human_future.result()
            ai_result = ai_future.result()

        # Save human round
        human_round = Round(
            game_id=game_id,
            round_number=round_number,
            is_human=True,
            prompt_text=prompt,
            svg_output=human_svg,
            raw_response=human_raw,
        )
        db.add(human_round)

        # Save AI round
        ai_round = Round(
            game_id=game_id,
            round_number=round_number,
            is_human=False,
            prompt_text=ai_result["prompt"],
            svg_output=ai_result["svg"],
            raw_response=ai_result["raw_response"],
        )
        db.add(ai_round)

        # Update game state
        game.current_round = round_number
        if round_number == total_rounds:
            game.human_svg_final = human_svg
            game.ai_svg_final = ai_result["svg"]

        db.commit()

        round_event_props = {
            "game_id": game_id,
            "round_number": round_number,
            "generation_model": game.generation_model,
            "$ai_trace_id": trace_id,
        }
        if session_id:
            round_event_props["$session_id"] = session_id

        posthog_client.capture(
            distinct_id=game.player_name,
            event="round_completed",
            properties=round_event_props,
        )

        is_final = round_number == total_rounds

        return {
            "round_number": round_number,
            "rounds_total": total_rounds,
            "human_svg": human_svg,
            "ai_prompt": ai_result["prompt"],
            "ai_svg": ai_result["svg"],
            "is_final_round": is_final,
            "game_status": "ready_to_judge" if is_final else "playing",
        }
    finally:
        db.close()


def judge_and_reveal(game_id: str, session_id: str | None = None) -> dict:
    """
    Judge the final SVGs blindly and reveal results.
    Randomize which is A/B so the judge can't infer.
    """
    db = SessionLocal()
    try:
        game = db.query(Game).filter(Game.id == game_id).first()
        if not game:
            raise ValueError(f"Game {game_id} not found")

        # If final SVGs not set (early finalization), use latest rounds
        if not game.human_svg_final or not game.ai_svg_final:
            latest_human = (
                db.query(Round)
                .filter(Round.game_id == game_id, Round.is_human == True, Round.svg_output.isnot(None))
                .order_by(Round.round_number.desc())
                .first()
            )
            latest_ai = (
                db.query(Round)
                .filter(Round.game_id == game_id, Round.is_human == False, Round.svg_output.isnot(None))
                .order_by(Round.round_number.desc())
                .first()
            )
            if not latest_human or not latest_ai:
                raise ValueError("Need at least one successful round from both sides before judging")
            game.human_svg_final = latest_human.svg_output
            game.ai_svg_final = latest_ai.svg_output

        game.status = "judging"
        db.commit()

        trace_id = game_id

        # Randomize assignment to prevent bias
        human_is_a = random.choice([True, False])
        if human_is_a:
            svg_a, svg_b = game.human_svg_final, game.ai_svg_final
        else:
            svg_a, svg_b = game.ai_svg_final, game.human_svg_final

        result = judge_game(
            svg_a=svg_a,
            svg_b=svg_b,
            trace_id=trace_id,
            distinct_id="judge",
            session_id=session_id,
            game_url=_game_url(game_id),
            judge_model_override=game.judge_model,
        )

        # Map scores back to human/AI
        if human_is_a:
            human_scores = result.get("svg_a", {})
            ai_scores = result.get("svg_b", {})
            raw_winner = result.get("winner", "tie")
            if raw_winner == "A":
                winner = "human"
            elif raw_winner == "B":
                winner = "ai"
            else:
                winner = "tie"
        else:
            human_scores = result.get("svg_b", {})
            ai_scores = result.get("svg_a", {})
            raw_winner = result.get("winner", "tie")
            if raw_winner == "A":
                winner = "ai"
            elif raw_winner == "B":
                winner = "human"
            else:
                winner = "tie"

        # Persist results
        game.human_score = human_scores.get("total", 0)
        game.ai_score = ai_scores.get("total", 0)
        game.human_roast = human_scores.get("roast", "")
        game.ai_roast = ai_scores.get("roast", "")
        game.judge_details = json.dumps({
            "human_scores": human_scores,
            "ai_scores": ai_scores,
            "commentary": result.get("commentary", ""),
        })
        game.winner = winner
        game.judge_model = result.get("judge_model", "unknown")
        game.status = "complete"
        game.completed_at = datetime.datetime.now(datetime.timezone.utc)
        db.commit()

        completed_props = {
            "game_id": game_id,
            "winner": winner,
            "human_score": game.human_score,
            "ai_score": game.ai_score,
            "generation_model": game.generation_model,
            "challenger_model": game.challenger_model,
            "$ai_trace_id": trace_id,
        }
        if session_id:
            completed_props["$session_id"] = session_id
        posthog_client.capture(
            distinct_id=game.player_name,
            event="game_completed",
            properties=completed_props,
        )

        human_rounds = (
            db.query(Round)
            .filter(Round.game_id == game_id, Round.is_human == True)
            .order_by(Round.round_number)
            .all()
        )
        ai_rounds = (
            db.query(Round)
            .filter(Round.game_id == game_id, Round.is_human == False)
            .order_by(Round.round_number)
            .all()
        )

        resp = {
            "game_id": game_id,
            "winner": winner,
            "human": {
                "svg": game.human_svg_final,
                "scores": human_scores,
                "rounds": [
                    {
                        "round_number": r.round_number,
                        "prompt": r.prompt_text,
                        "svg": r.svg_output,
                    }
                    for r in human_rounds
                ],
            },
            "ai": {
                "svg": game.ai_svg_final,
                "scores": ai_scores,
                "rounds": [
                    {
                        "round_number": r.round_number,
                        "prompt": r.prompt_text,
                        "svg": r.svg_output,
                    }
                    for r in ai_rounds
                ],
            },
            "commentary": result.get("commentary", ""),
            "generation_model": game.generation_model,
            "challenger_model": game.challenger_model,
            "judge_model": game.judge_model,
            "appeal": None,
        }

        # If the AI lost, let it decide in the background whether to appeal
        if winner == "human":
            threading.Thread(
                target=ai_consider_appeal,
                args=(game_id,),
                kwargs={"session_id": session_id},
                daemon=True,
            ).start()

        return resp
    finally:
        db.close()


def get_leaderboard(limit: int = 20) -> list[dict]:
    """Get recent completed games for the leaderboard."""
    db = SessionLocal()
    try:
        games = (
            db.query(Game)
            .filter(Game.status == "complete")
            .order_by(Game.completed_at.desc())
            .limit(limit)
            .all()
        )
        return [
            {
                "game_id": g.id,
                "player_name": g.player_name,
                "winner": g.winner,
                "human_score": g.human_score,
                "ai_score": g.ai_score,
                "human_svg": g.human_svg_final,
                "ai_svg": g.ai_svg_final,
                "human_roast": g.human_roast,
                "ai_roast": g.ai_roast,
                "generation_model": g.generation_model,
                "challenger_model": g.challenger_model,
                "completed_at": g.completed_at.isoformat() if g.completed_at else None,
            }
            for g in games
        ]
    finally:
        db.close()


def get_game_state(game_id: str) -> dict | None:
    """Get the current state of a game."""
    db = SessionLocal()
    try:
        game = db.query(Game).filter(Game.id == game_id).first()
        if not game:
            return None

        human_rounds = (
            db.query(Round)
            .filter(Round.game_id == game_id, Round.is_human == True)
            .order_by(Round.round_number)
            .all()
        )
        ai_rounds = (
            db.query(Round)
            .filter(Round.game_id == game_id, Round.is_human == False)
            .order_by(Round.round_number)
            .all()
        )

        return {
            "game_id": game.id,
            "player_name": game.player_name,
            "generation_model": game.generation_model,
            "current_round": game.current_round,
            "rounds_total": game.rounds_total or ROUNDS_PER_GAME,
            "status": game.status,
            "rounds": [
                {
                    "round_number": r.round_number,
                    "prompt": r.prompt_text,
                    "svg": r.svg_output,
                }
                for r in human_rounds
            ],
            "ai_rounds": [
                {
                    "round_number": r.round_number,
                    "prompt": r.prompt_text,
                    "svg": r.svg_output,
                }
                for r in ai_rounds
            ],
        }
    finally:
        db.close()


def get_gallery(limit: int = 50) -> list[dict]:
    """Get all SVGs across all games for the gallery."""
    db = SessionLocal()
    try:
        rounds = (
            db.query(Round)
            .filter(Round.svg_output.isnot(None))
            .order_by(Round.created_at.desc())
            .limit(limit)
            .all()
        )
        # Batch-fetch game info
        game_ids = list({r.game_id for r in rounds})
        games = {g.id: g for g in db.query(Game).filter(Game.id.in_(game_ids)).all()}

        return [
            {
                "round_id": r.id,
                "game_id": r.game_id,
                "round_number": r.round_number,
                "is_human": r.is_human,
                "prompt": r.prompt_text,
                "svg": r.svg_output,
                "model": games[r.game_id].generation_model if r.game_id in games else "unknown",
                "player_name": games[r.game_id].player_name if r.game_id in games else "unknown",
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rounds
        ]
    finally:
        db.close()


def create_game_from_fork(player_name: str, fork_round_id: int, session_id: str | None = None) -> dict:
    """Start a new game forked from an existing round's conversation history."""
    db = SessionLocal()
    try:
        # Get the round to fork from
        fork_round = db.query(Round).filter(Round.id == fork_round_id).first()
        if not fork_round:
            raise ValueError(f"Round {fork_round_id} not found")

        source_game = db.query(Game).filter(Game.id == fork_round.game_id).first()
        if not source_game:
            raise ValueError("Source game not found")

        # Get all rounds up to and including the fork point (same track: human or AI)
        history_rounds = (
            db.query(Round)
            .filter(
                Round.game_id == fork_round.game_id,
                Round.is_human == fork_round.is_human,
                Round.round_number <= fork_round.round_number,
            )
            .order_by(Round.round_number)
            .all()
        )

        # Create new game with same generation model
        # Forked games get ROUNDS_PER_GAME extra rounds from the fork point
        game_id = uuid.uuid4().hex[:12]
        challenger_model = random.choice(CHALLENGER_MODELS)
        judge_model = random.choice(JUDGE_MODELS)
        forked_rounds = len(history_rounds)

        game = Game(
            id=game_id,
            player_name=player_name,
            generation_model=source_game.generation_model,
            challenger_model=challenger_model,
            judge_model=judge_model,
            current_round=forked_rounds,
            rounds_total=forked_rounds + ROUNDS_PER_GAME,
        )
        db.add(game)

        # Copy history rounds into new game as human rounds
        for i, r in enumerate(history_rounds):
            new_round = Round(
                game_id=game_id,
                round_number=i + 1,
                is_human=True,
                prompt_text=r.prompt_text,
                svg_output=r.svg_output,
                raw_response=r.raw_response,
            )
            db.add(new_round)

            # Also create stub AI rounds so the challenger has context
            ai_round = Round(
                game_id=game_id,
                round_number=i + 1,
                is_human=False,
                prompt_text="(forked game — no AI prompt)",
                svg_output=None,
                raw_response=None,
            )
            db.add(ai_round)

        db.commit()

        # Explicit $ai_trace root event — see create_game for rationale.
        trace_props = {
            "$ai_trace_id": game_id,
            "$ai_span_name": f"{player_name}-{source_game.generation_model}",
            "game_id": game_id,
            "game_url": _game_url(game_id),
            "generation_model": source_game.generation_model,
            "challenger_model": challenger_model,
            "judge_model": judge_model,
            "forked_from_game": fork_round.game_id,
        }
        if session_id:
            trace_props["$session_id"] = session_id
            trace_props["$ai_session_id"] = session_id
        posthog_client.capture(
            distinct_id=player_name,
            event="$ai_trace",
            properties=trace_props,
        )

        props = {
            "game_id": game_id,
            "generation_model": source_game.generation_model,
            "challenger_model": challenger_model,
            "judge_model": judge_model,
            "forked_from_game": fork_round.game_id,
            "forked_from_round": fork_round_id,
            "$ai_trace_id": game_id,
        }
        if session_id:
            props["$session_id"] = session_id

        posthog_client.capture(
            distinct_id=player_name,
            event="game_forked",
            properties=props,
        )

        return {
            "game_id": game_id,
            "generation_model": source_game.generation_model,
            "challenger_model": challenger_model,
            "rounds_total": forked_rounds + ROUNDS_PER_GAME,
            "current_round": forked_rounds,
            "forked_from": fork_round.game_id,
        }
    finally:
        db.close()


def ai_consider_appeal(game_id: str, session_id: str | None = None) -> None:
    """
    Background task: let the AI challenger decide whether to appeal.
    If it decides yes, automatically file the appeal.
    """
    db = SessionLocal()
    try:
        game = db.query(Game).filter(Game.id == game_id).first()
        if not game or game.status != "complete":
            return
        if game.winner != "human":
            return  # AI only appeals when it lost
        if game.appeal_verdict:
            return  # Already appealed

        details = {}
        if game.judge_details:
            details = json.loads(game.judge_details)

        plea = consider_appeal(
            challenger_model=game.challenger_model,
            human_svg=game.human_svg_final or "",
            ai_svg=game.ai_svg_final or "",
            judge_details=details,
            trace_id=game_id,
            session_id=session_id,
            game_url=_game_url(game_id),
        )

        if plea:
            log.info("AI auto-appeal for game %s: filing appeal", game_id)
            appeal_game(game_id, plea, session_id=session_id)
        else:
            log.info("AI accepts ruling for game %s", game_id)
    except Exception:
        log.exception("AI appeal consideration failed for game %s", game_id)
    finally:
        db.close()


def appeal_game(game_id: str, appeal_text: str, session_id: str | None = None) -> dict:
    """
    File an appeal on behalf of the losing side.
    A different supreme judge reviews all evidence + the appellant's plea.
    """
    db = SessionLocal()
    try:
        game = db.query(Game).filter(Game.id == game_id).first()
        if not game:
            raise ValueError(f"Game {game_id} not found")
        if game.status != "complete":
            raise ValueError("Game is not complete yet")
        if game.appeal_verdict:
            raise ValueError("Appeal already filed for this game")
        if game.winner == "tie":
            raise ValueError("Cannot appeal a tie — both sides are equally guilty")

        # The loser is the appellant
        appellant = "ai" if game.winner == "human" else "human"

        # Load original judge details
        details = {}
        if game.judge_details:
            details = json.loads(game.judge_details)

        trace_id = game_id

        # Randomize SVG assignment (same as original judging)
        human_is_a = random.choice([True, False])
        if human_is_a:
            svg_a, svg_b = game.human_svg_final, game.ai_svg_final
            appellant_label = "A" if appellant == "human" else "B"
        else:
            svg_a, svg_b = game.ai_svg_final, game.human_svg_final
            appellant_label = "B" if appellant == "human" else "A"

        result = judge_appeal(
            svg_a=svg_a,
            svg_b=svg_b,
            original_scores=details,
            appeal_text=appeal_text,
            appellant_side=appellant_label,
            human_is_a=human_is_a,
            trace_id=trace_id,
            distinct_id="appeal-judge",
            session_id=session_id,
            game_url=_game_url(game_id),
            exclude_model=game.judge_model,
        )

        verdict = result.get("verdict", "upheld")

        # Map new_winner back from A/B to human/ai
        raw_new_winner = result.get("new_winner", "tie")
        if human_is_a:
            if raw_new_winner == "A":
                new_winner = "human"
            elif raw_new_winner == "B":
                new_winner = "ai"
            else:
                new_winner = "tie"
        else:
            if raw_new_winner == "A":
                new_winner = "ai"
            elif raw_new_winner == "B":
                new_winner = "human"
            else:
                new_winner = "tie"

        # Map scores back
        if human_is_a:
            appeal_human_scores = result.get("svg_a", {})
            appeal_ai_scores = result.get("svg_b", {})
        else:
            appeal_human_scores = result.get("svg_b", {})
            appeal_ai_scores = result.get("svg_a", {})

        # Persist appeal results
        game.appeal_text = appeal_text
        game.appeal_appellant = appellant
        game.appeal_judge_model = result.get("appeal_judge_model", "unknown")
        game.appeal_verdict = verdict
        game.appeal_details = json.dumps({
            "human_scores": appeal_human_scores,
            "ai_scores": appeal_ai_scores,
            "reasoning": result.get("reasoning", ""),
            "response_to_appellant": result.get("response_to_appellant", ""),
        })
        game.appeal_new_winner = new_winner if verdict == "overturned" else game.winner
        game.appealed_at = datetime.datetime.now(datetime.timezone.utc)
        db.commit()

        # PostHog event
        appeal_props = {
            "game_id": game_id,
            "appellant": appellant,
            "verdict": verdict,
            "original_winner": game.winner,
            "appeal_new_winner": game.appeal_new_winner,
            "appeal_judge_model": game.appeal_judge_model,
            "$ai_trace_id": trace_id,
        }
        if session_id:
            appeal_props["$session_id"] = session_id
        posthog_client.capture(
            distinct_id=game.player_name,
            event="appeal_completed",
            properties=appeal_props,
        )

        return {
            "game_id": game_id,
            "appellant": appellant,
            "verdict": verdict,
            "original_winner": game.winner,
            "new_winner": game.appeal_new_winner,
            "appeal_judge_model": game.appeal_judge_model,
            "human_scores": appeal_human_scores,
            "ai_scores": appeal_ai_scores,
            "reasoning": result.get("reasoning", ""),
            "response_to_appellant": result.get("response_to_appellant", ""),
        }
    finally:
        db.close()


def get_results(game_id: str) -> dict | None:
    """Get the full results of a completed game from stored data."""
    db = SessionLocal()
    try:
        game = db.query(Game).filter(Game.id == game_id).first()
        if not game or game.status != "complete":
            return None

        details = {}
        if game.judge_details:
            details = json.loads(game.judge_details)

        human_rounds = (
            db.query(Round)
            .filter(Round.game_id == game_id, Round.is_human == True)
            .order_by(Round.round_number)
            .all()
        )
        ai_rounds = (
            db.query(Round)
            .filter(Round.game_id == game_id, Round.is_human == False)
            .order_by(Round.round_number)
            .all()
        )

        return {
            "game_id": game_id,
            "winner": game.winner,
            "human": {
                "svg": game.human_svg_final,
                "scores": details.get("human_scores", {
                    "total": game.human_score,
                    "roast": game.human_roast,
                }),
                "rounds": [
                    {
                        "round_number": r.round_number,
                        "prompt": r.prompt_text,
                        "svg": r.svg_output,
                    }
                    for r in human_rounds
                ],
            },
            "ai": {
                "svg": game.ai_svg_final,
                "scores": details.get("ai_scores", {
                    "total": game.ai_score,
                    "roast": game.ai_roast,
                }),
                "rounds": [
                    {
                        "round_number": r.round_number,
                        "prompt": r.prompt_text,
                        "svg": r.svg_output,
                    }
                    for r in ai_rounds
                ],
            },
            "commentary": details.get("commentary", ""),
            "generation_model": game.generation_model,
            "challenger_model": game.challenger_model,
            "judge_model": game.judge_model,
            "completed_at": game.completed_at.isoformat() if game.completed_at else None,
            "appeal": _build_appeal_response(game),
        }
    finally:
        db.close()


def _build_appeal_response(game: Game) -> dict | None:
    """Build the appeal sub-object for API responses, or None if no appeal."""
    if not game.appeal_verdict:
        return None
    appeal_details = {}
    if game.appeal_details:
        appeal_details = json.loads(game.appeal_details)
    return {
        "appellant": game.appeal_appellant,
        "appeal_text": game.appeal_text,
        "verdict": game.appeal_verdict,
        "new_winner": game.appeal_new_winner,
        "appeal_judge_model": game.appeal_judge_model,
        "human_scores": appeal_details.get("human_scores", {}),
        "ai_scores": appeal_details.get("ai_scores", {}),
        "reasoning": appeal_details.get("reasoning", ""),
        "response_to_appellant": appeal_details.get("response_to_appellant", ""),
    }
