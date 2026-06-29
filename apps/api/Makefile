.PHONY: verify lint format types test

# One-command local gate for the API: lint + format-check + types + tests(+coverage).
verify: lint format types test

lint:
	uv run ruff check .

format:
	uv run ruff format --check .

types:
	uv run mypy .

test:
	uv run pytest
