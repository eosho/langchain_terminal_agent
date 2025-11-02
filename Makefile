.PHONY: install lint-fix pre-commit clean

install:
	uv sync --all-groups
	uv run pre-commit install

lint-fix:
	find src -name "*.py" -type f -exec uv run pyupgrade --py311-plus {} + || true
	uv run autoflake --recursive --remove-all-unused-imports --remove-unused-variables --in-place src
	uv run isort src --profile black
	uv run black src
	uv run mypy src --check-untyped-defs

pre-commit:
	uv run pre-commit run --all-files

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".mypy_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
