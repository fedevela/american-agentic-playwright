.PHONY: test coverage test-missing trigger trigger-manual trigger-prompt

# Testing Targets
test:
	source .venv/bin/activate && pytest tests/

coverage:
	source .venv/bin/activate && pytest tests/ --cov=trigger_workflow --cov-report=term

test-missing:
	source .venv/bin/activate && pytest tests/ --cov=trigger_workflow --cov-report=term-missing

# Trigger Targets
# Use like: make trigger LABEL="phase:keter" ISSUE="123" REPO="owner/repo"
# Or let it auto-resolve if no parameters are provided
trigger:
	source .venv/bin/activate && python trigger.py \
		$(if $(LABEL),--label $(LABEL)) \
		$(if $(PHASE),--phase $(PHASE)) \
		$(if $(ISSUE),--issue $(ISSUE)) \
		$(if $(REPO),--repo $(REPO))

trigger-manual:
	source .venv/bin/activate && python trigger.py --manual \
		$(if $(LABEL),--label $(LABEL)) \
		$(if $(PHASE),--phase $(PHASE)) \
		$(if $(ISSUE),--issue $(ISSUE)) \
		$(if $(REPO),--repo $(REPO))

trigger-prompt:
	source .venv/bin/activate && python trigger.py --prompt-only \
		$(if $(LABEL),--label $(LABEL)) \
		$(if $(PHASE),--phase $(PHASE)) \
		$(if $(ISSUE),--issue $(ISSUE)) \
		$(if $(REPO),--repo $(REPO))
