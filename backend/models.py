import datetime
import logging
from sqlalchemy import create_engine, Column, String, Integer, Float, Text, DateTime, Boolean, inspect, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker

log = logging.getLogger("hot-hog")

from .config import DATABASE_URL


class Base(DeclarativeBase):
    pass


class Game(Base):
    __tablename__ = "games"

    id = Column(String, primary_key=True)
    player_name = Column(String, nullable=False)
    generation_model = Column(String, nullable=False)
    challenger_model = Column(String, nullable=False)
    judge_model = Column(String, nullable=True)
    current_round = Column(Integer, default=0)
    rounds_total = Column(Integer, nullable=True)  # NULL = use ROUNDS_PER_GAME default
    human_svg_final = Column(Text, nullable=True)
    ai_svg_final = Column(Text, nullable=True)
    human_score = Column(Float, nullable=True)
    ai_score = Column(Float, nullable=True)
    human_roast = Column(Text, nullable=True)
    ai_roast = Column(Text, nullable=True)
    judge_details = Column(Text, nullable=True)  # JSON: full per-category scores + commentary
    winner = Column(String, nullable=True)  # "human" | "ai" | "tie"
    status = Column(String, default="playing")  # "playing" | "judging" | "complete"
    created_at = Column(DateTime, default=lambda: datetime.datetime.now(datetime.timezone.utc))
    completed_at = Column(DateTime, nullable=True)

    # Appeal process
    appeal_text = Column(Text, nullable=True)  # Losing player's plea
    appeal_appellant = Column(String, nullable=True)  # "human" | "ai"
    appeal_judge_model = Column(String, nullable=True)
    appeal_verdict = Column(String, nullable=True)  # "upheld" | "overturned"
    appeal_details = Column(Text, nullable=True)  # JSON: full appeal judge response
    appeal_new_winner = Column(String, nullable=True)  # winner after appeal (if overturned)
    appealed_at = Column(DateTime, nullable=True)


class Round(Base):
    __tablename__ = "rounds"

    id = Column(Integer, primary_key=True, autoincrement=True)
    game_id = Column(String, nullable=False, index=True)
    round_number = Column(Integer, nullable=False)
    is_human = Column(Boolean, nullable=False)
    prompt_text = Column(Text, nullable=False)
    svg_output = Column(Text, nullable=True)
    raw_response = Column(Text, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.datetime.now(datetime.timezone.utc))


engine = create_engine(DATABASE_URL, echo=False)
SessionLocal = sessionmaker(bind=engine)


def init_db():
    Base.metadata.create_all(engine)
    # Auto-migrate: add columns that may not exist in older databases
    inspector = inspect(engine)
    game_columns = {c["name"] for c in inspector.get_columns("games")}
    with engine.begin() as conn:
        if "rounds_total" not in game_columns:
            log.info("Migrating: adding rounds_total column to games")
            conn.execute(text("ALTER TABLE games ADD COLUMN rounds_total INTEGER"))
        appeal_cols = {
            "appeal_text": "TEXT",
            "appeal_appellant": "VARCHAR",
            "appeal_judge_model": "VARCHAR",
            "appeal_verdict": "VARCHAR",
            "appeal_details": "TEXT",
            "appeal_new_winner": "VARCHAR",
            "appealed_at": "TIMESTAMP",
        }
        for col_name, col_type in appeal_cols.items():
            if col_name not in game_columns:
                log.info("Migrating: adding %s column to games", col_name)
                conn.execute(text(f"ALTER TABLE games ADD COLUMN {col_name} {col_type}"))


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
