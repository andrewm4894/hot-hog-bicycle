.PHONY: install run dev test clean sync deploy autoplay

install:
	uv sync

sync:
	uv sync

run:
	uv run uvicorn backend.main:app --host $${APP_HOST:-0.0.0.0} --port $${APP_PORT:-8000}

dev:
	uv run uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000

test:
	uv run pytest tests/ -v

deploy:
	railway up

autoplay:
	uv run python -m backend.autoplay

clean:
	rm -rf .venv __pycache__ *.db
