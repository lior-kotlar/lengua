# Lengua monorepo — root task runner.
#
# One-command local quality gate. `make verify` fans out to the two app verify
# targets and exits 0 only when both pass:
#
#   * api  — `uv run python scripts/verify.py` in apps/api
#            (ruff lint, ruff format --check, mypy, pytest w/ branch coverage)
#   * web  — `pnpm verify` in apps/web
#            (eslint, prettier --check, tsc --noEmit, vitest w/ coverage, vite build)
#
# No `make` on your machine (e.g. Windows)? Run the identical cross-platform engine:
#
#   python scripts/verify.py
#
# pnpm is invoked via `corepack pnpm` when pnpm isn't on PATH (corepack ships with Node
# and honors the packageManager pin in apps/web/package.json).

# Use pnpm if it's on PATH, otherwise fall back to `corepack pnpm`.
PNPM := $(shell command -v pnpm >/dev/null 2>&1 && echo pnpm || echo corepack pnpm)

.PHONY: verify verify-api verify-web

## verify: run the api + web lint/type/test/build gate (the full local gate)
verify: verify-api verify-web
	@echo "\nverify OK — api + web all green"

## verify-api: backend gate (ruff + mypy + pytest w/ coverage) in apps/api
verify-api:
	@echo "\n========== api verify =========="
	cd apps/api && uv run python scripts/verify.py

## verify-web: frontend gate (eslint + prettier + tsc + vitest + build) in apps/web
verify-web:
	@echo "\n========== web verify =========="
	cd apps/web && $(PNPM) verify
