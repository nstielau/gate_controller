CIRCUITPY ?= /Volumes/CIRCUITPY
APP_DIR := circuitpython
PYTHON := .venv/bin/python
CONSOLE_WAIT ?= 3
CONSOLE_ARGS ?=
TEST_ARGS ?=

.PHONY: setup check test test-hardware test-hardware-smoke deploy status console

setup:
	uv venv --allow-existing .venv
	uv pip sync --python "$(PYTHON)" tools/requirements-dev.lock

check:
	$(PYTHON) -c 'import ast, pathlib; files = [*pathlib.Path("$(APP_DIR)").rglob("*.py"), *pathlib.Path("tools").glob("*.py"), *pathlib.Path("test_suite").glob("*.py")]; [ast.parse(p.read_text(), filename=str(p)) for p in files]; print("Syntax OK:", len(files), "files")'

test: check
	$(PYTHON) -m unittest discover -s test_suite -v

test-hardware:
	$(PYTHON) tools/test_mqtt_cycles.py $(TEST_ARGS)

test-hardware-smoke:
	$(PYTHON) tools/test_mqtt_cycles.py --cycles 1 --intervals 300 --timeout 20 --soak 15 $(TEST_ARGS)

status:
	@test -d "$(CIRCUITPY)" || (echo "CIRCUITPY drive not found at $(CIRCUITPY)"; exit 1)
	@cat "$(CIRCUITPY)/boot_out.txt"

console:
	$(PYTHON) tools/xiao_console.py --wait "$(CONSOLE_WAIT)" $(CONSOLE_ARGS)

deploy: test
	$(PYTHON) tools/deploy.py "$(CIRCUITPY)"
