SHELL := /bin/bash
export PATH := $(CURDIR)/.venv/bin:$(CURDIR)/.tools/bin:$(PATH)

TARGET ?= http://127.0.0.1:8080

.DEFAULT_GOAL := help
.PHONY: help tools validate test up down runtime gate scenario collect zap release-check bicep clean

help: ## list targets
	@grep -E '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | awk -F ':.*## ' '{printf "  %-15s %s\n", $$1, $$2}'

tools: ## install the venv and pinned linters into the repo
	scripts/bootstrap.sh

validate: ## static gates: yaml, shell, dockerfile, secrets, manifest, compose policy, dependencies
	checks/gate.sh static

test: ## unit tests for the gates and the sample service
	python -m pytest -q

up: ## build and start the validation stack
	scripts/repro.sh up

down: ## stop the stack and remove its volume
	scripts/repro.sh down

runtime: ## smoke + OWASP gates against the running stack
	CRV_TARGET=$(TARGET) checks/gate.sh runtime

gate: ## everything: static gates, start the stack, runtime gates
	checks/gate.sh static
	scripts/repro.sh up
	CRV_TARGET=$(TARGET) checks/gate.sh runtime

scenario: ## reproduce a failure, e.g. make scenario NAME=readonly-data
	scripts/repro.sh scenario $(NAME)

collect: ## save logs and state of the running stack to out/repro/
	scripts/repro.sh collect

zap: ## OWASP ZAP baseline scan against the running stack
	scripts/zap-baseline.sh

release-check: ## git gate for cutting a release (clean tree, annotated tag at HEAD)
	checks/git_state.sh

bicep: ## compile the Azure templates
	@if command -v bicep > /dev/null; then bicep build infra/main.bicep --stdout > /dev/null; \
	else az bicep build --file infra/main.bicep --stdout > /dev/null; fi
	@echo "infra/main.bicep compiles"

clean: ## remove reports and evidence
	rm -rf out
