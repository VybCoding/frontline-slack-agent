.PHONY: install demo dev audit test lint synth deploy clean

install:            ## create .venv and install the package
	python3 -m venv .venv
	.venv/bin/pip install -e ".[dev]" -q
	@test -f .env || cp .env.example .env
	@echo "ready. run: make demo"

demo:               ## end-to-end run against mocks; no credentials required
	.venv/bin/python scripts/demo.py

dev:                ## run against a real Slack workspace via Socket Mode
	.venv/bin/python -m frontline_agent.runtime.local

audit:              ## pretty-print the local audit log
	@.venv/bin/python -c "import json,sys; \
	[print(json.dumps(r, indent=2)) for r in \
	 __import__('frontline_agent.audit.log', fromlist=['x']).read_local_audit()]"

test:
	.venv/bin/pytest -q

lint:
	.venv/bin/ruff check src infra scripts tests

synth:              ## render CloudFormation without deploying
	cd infra && ../.venv/bin/cdk synth

deploy:             ## deploy audit stack first, then the agent
	cd infra && ../.venv/bin/cdk deploy FrontlineAgentAudit FrontlineAgent

clean:
	rm -rf .audit .memory .pytest_cache .ruff_cache infra/cdk.out
