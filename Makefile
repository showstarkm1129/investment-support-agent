PYTHON ?= python3
NPM ?= npm

FLOW ?= close_report
TARGET ?= TARGET-SAMPLE-6501
SCRIPT ?= semiconductor_sector_morning
PROVIDER ?= manual
MODE ?= prepare

.PHONY: help install-dev test test-pytest test-unittest validate validate-static validate-generated validate-contracts validate-samples validate-flow-scripts check-artifacts lint lint-python lint-md typecheck format format-python reports app flow flow-script test-e2e test-e2e-ui test-e2e-report check-links clean

help:
	@awk 'BEGIN {FS = ":.*## "}; /^[a-zA-Z0-9_-]+:.*## / {printf "%-24s %s\n", $$1, $$2}' $(MAKEFILE_LIST)

install-dev: ## Install Python and Node development tools.
	$(PYTHON) -m pip install -e ".[dev]"
	$(NPM) install

test: ## Run Python tests, using pytest when installed and unittest otherwise.
	$(PYTHON) scripts/run_tests.py

test-pytest: ## Run Python tests with pytest.
	$(PYTHON) -m pytest tests

test-unittest: ## Run Python tests with unittest.
	$(PYTHON) -m unittest discover -s tests

validate: validate-static validate-contracts check-artifacts ## Run the default local validation suite.

validate-static: ## Run static project checks without generated artifact diff checks.
	$(PYTHON) scripts/validate_static.py --skip-generated

validate-generated: ## Run static project checks including generated artifact freshness.
	$(PYTHON) scripts/validate_static.py

validate-contracts: ## Validate contract schemas and known sample JSON.
	$(PYTHON) scripts/validate_contracts.py

validate-samples: validate-contracts ## Alias for sample JSON contract validation.

validate-flow-scripts: ## Validate flow script JSON files against the flow script schema.
	$(PYTHON) scripts/validate_contracts.py --flow-scripts-only

check-artifacts: ## Check run, data, and report artifacts for expected files and contracts.
	$(PYTHON) scripts/check_artifacts.py

lint: lint-python lint-md ## Run Python and Markdown lint checks.

lint-python: ## Run Ruff lint checks for Python scripts and tests.
	$(PYTHON) -m ruff check scripts tests

lint-md: ## Run Markdown lint checks.
	$(NPM) run lint:md

typecheck: ## Run mypy type checks.
	$(PYTHON) -m mypy

format: format-python ## Format editable source files.

format-python: ## Format Python scripts and tests with Ruff.
	$(PYTHON) -m ruff format scripts tests

reports: ## Generate sample reports.
	$(PYTHON) scripts/generate_reports.py

app: ## Generate static app pages from sample data.
	$(PYTHON) scripts/generate_app_pages.py

flow: ## Prepare a flow run. Override FLOW and TARGET as needed.
	$(PYTHON) scripts/run_flow.py --flow $(FLOW) --target-id $(TARGET) --provider $(PROVIDER) --mode $(MODE)

flow-script: ## Prepare or simulate a configured flow script. Override SCRIPT, PROVIDER, MODE as needed.
	$(PYTHON) scripts/run_flow.py --script $(SCRIPT) --provider $(PROVIDER) --mode $(MODE)

test-e2e: ## Run Playwright end-to-end tests.
	$(NPM) run test:e2e

test-e2e-ui: ## Open Playwright UI mode.
	$(NPM) run test:e2e:ui

test-e2e-report: ## Open the latest Playwright HTML report.
	$(NPM) run test:e2e:report

check-links: ## Check local Markdown links; HTML links are covered by validate-static.
	$(NPM) run check:links

clean: ## Remove local cache and test output directories.
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
	rm -rf .pytest_cache .ruff_cache .mypy_cache test-results playwright-report blob-report
