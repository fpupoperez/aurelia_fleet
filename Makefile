.PHONY: test test-all eval hooks

PYTHON ?= backend/.venv/bin/python

test:
	$(PYTHON) scripts/select_tests.py

test-all:
	cd backend && ../$(PYTHON) -m pytest
	cd frontend && npm test

eval:
	cd backend && ../$(PYTHON) -m app.evaluation

hooks:
	$(PYTHON) -m pre_commit install --hook-type pre-commit --hook-type pre-push
