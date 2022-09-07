.DEFAULT_GOAL := all
paths = src tests

.PHONY: install
install:
	pip install -U pip pre-commit
	pip install -r requirements.txt
	pip install -r tests/requirements.txt
	pip install -r tests/requirements-linting.txt
	pre-commit install

.PHONY: format
format:
	isort $(paths)
	black $(paths)

.PHONY: lint
lint:
	flake8 $(paths)
	isort $(paths) --check-only --df
	black $(paths) --check --diff

.PHONY: test
test:
	coverage run -m pytest


.PHONY: all
all: format lint test
