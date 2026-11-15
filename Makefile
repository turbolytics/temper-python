PYTHON ?= python
TEMPER ?= temper

.PHONY: test matrix check-matrix

test:
	$(PYTHON) -m pytest -q

matrix:
	$(TEMPER) check
	$(TEMPER) clean
	$(TEMPER) run --level unit -- $(PYTHON) -m pytest -q
	$(TEMPER) matrix --all-levels

check-matrix:
	$(TEMPER) check
	$(TEMPER) clean
	$(TEMPER) run --level unit -- $(PYTHON) -m pytest -q
	$(TEMPER) matrix --check
