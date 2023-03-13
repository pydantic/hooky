.DEFAULT_GOAL := all
paths = src tests

.PHONY: install
install:
	pip install -U pip pre-commit pip-tools
	pip install -r requirements/all.txt
	pre-commit install

.PHONY: format
format:
	pyupgrade --py310-plus --exit-zero-even-if-changed `find $(paths) -name "*.py" -type f`
	isort $(paths)
	black $(paths)

.PHONY: lint
lint:
	ruff $(paths)
	isort $(paths) --check-only --df
	black $(paths) --check --diff

.PHONY: test
test:
	coverage run -m pytest

.PHONY: testcov
testcov: test
	@coverage report
	@echo "building coverage html"
	@coverage html

.PHONY: all
all: format lint test
