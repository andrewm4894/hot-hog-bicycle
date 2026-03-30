from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel

from .models import init_db
from .game import create_game, create_game_from_fork, play_human_round, judge_and_reveal, get_leaderboard, get_game_state, get_results, get_gallery


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title="Hot Hog on a Bicycle", lifespan=lifespan)


# --- API models ---

class StartGameRequest(BaseModel):
    player_name: str
    session_id: str | None = None


class PlayRoundRequest(BaseModel):
    prompt: str
    fresh_start: bool = False
    session_id: str | None = None


class ForkGameRequest(BaseModel):
    player_name: str
    fork_round_id: int
    session_id: str | None = None


# --- API routes ---

@app.post("/api/game/start")
def api_start_game(req: StartGameRequest):
    result = create_game(req.player_name, session_id=req.session_id)
    return result


@app.get("/api/game/{game_id}")
def api_get_game(game_id: str):
    state = get_game_state(game_id)
    if not state:
        raise HTTPException(status_code=404, detail="Game not found")
    return state


@app.post("/api/game/{game_id}/round")
def api_play_round(game_id: str, req: PlayRoundRequest):
    try:
        result = play_human_round(game_id, req.prompt, fresh_start=req.fresh_start, session_id=req.session_id)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/game/{game_id}/judge")
def api_judge_game(game_id: str):
    try:
        result = judge_and_reveal(game_id)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/game/{game_id}/results")
def api_get_results(game_id: str):
    results = get_results(game_id)
    if not results:
        raise HTTPException(status_code=404, detail="Results not available yet")
    return results


@app.get("/api/leaderboard")
def api_leaderboard():
    return get_leaderboard()


@app.get("/api/gallery")
def api_gallery():
    return get_gallery()


@app.post("/api/game/fork")
def api_fork_game(req: ForkGameRequest):
    try:
        result = create_game_from_fork(req.player_name, req.fork_round_id, session_id=req.session_id)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# --- Static frontend ---

app.mount("/static", StaticFiles(directory="frontend/static"), name="static")


@app.get("/")
def index():
    return FileResponse("frontend/index.html")


@app.get("/play/{game_id}")
def play(game_id: str):
    return FileResponse("frontend/game.html")


@app.get("/results/{game_id}")
def results(game_id: str):
    return FileResponse("frontend/results.html")


@app.get("/leaderboard")
def leaderboard():
    return FileResponse("frontend/leaderboard.html")


@app.get("/gallery")
def gallery():
    return FileResponse("frontend/gallery.html")
