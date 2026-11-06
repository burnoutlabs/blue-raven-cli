# Blue Raven CLI task runner (uv)

set dotenv-load := false

# Default: show available recipes
default:
    @just --list

# Install dependencies and set up environment
setup:
    uv sync

# Format code (mutates working tree — use locally)
fmt:
    uv run ruff format .
    uv run ruff check --fix .

# Verify formatting (non-mutating — use in CI)
fmt-check:
    uv run ruff format --check .

# Run linters
lint:
    uv run ruff check .

# Format + lint (non-mutating — safe for CI)
check: fmt-check lint

# Run tests
test:
    uv run pytest

# Remove build artifacts
clean:
    rm -rf .venv dist build .pytest_cache .ruff_cache
