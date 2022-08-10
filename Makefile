.DEFAULT_GOAL := all
isort = isort src tests
black = black src tests

.PHONY: install
install:
	pip install -U pip pre-commit
	pip install -r requirements.txt
	pip install -r tests/requirements.txt
	pip install -r tests/requirements-linting.txt
	pre-commit install

.PHONY: format
format:
	$(isort)
	$(black)

.PHONY: lint
lint:
	flake8 --max-line-length 120 src tests
	$(isort) --check-only --df
	$(black) --check --diff

.PHONY: test
test:
	coverage run -m pytest


.PHONY: all
all: format lint test
