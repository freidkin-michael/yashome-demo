# make test ENGINE=<engine checkout> [PYTHON=<python with the engine's requirements>]
ENGINE ?= ../yashome
PYTHON ?= python3
test:
	PYTHON=$(PYTHON) sh run_tests.sh $(ENGINE)
.PHONY: test
