.PHONY: film dry-run validate test install

film:
	python -m pipeline.run --no-gpu

dry-run:
	python -m pipeline.run --dry-run

validate:
	python -m pipeline.run --dry-run

test:
	pytest tests/ -v

install:
	pip install -r requirements.txt
