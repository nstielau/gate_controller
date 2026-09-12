CIRCUITPY ?= /Volumes/CIRCUITPY
APP_DIR := circuitpython
PYTHON := .venv/bin/python
CONSOLE_WAIT ?= 3
CONSOLE_ARGS ?=
TEST_ARGS ?=

.PHONY: setup check test test-hardware test-hardware-smoke deploy status console fritzing fritzing-preview hold

setup:
	uv venv --allow-existing .venv
	uv pip sync --python "$(PYTHON)" tools/requirements-dev.lock

fritzing:
	uv run --cache-dir .artifacts/uv-cache tools/make_fritzing.py

fritzing-preview: fritzing
	mkdir -p .artifacts/fritzing-mini
	cp docs/xiao-breadboard.fzz .artifacts/fritzing-mini/xiao-breadboard.fzz
	/Applications/Fritzing.app/Contents/MacOS/Fritzing -svg .artifacts/fritzing-mini > .artifacts/fritzing-mini/export.log 2>&1
	cp .artifacts/fritzing-mini/xiao-breadboard_breadboard.svg docs/xiao-mini-breadboard.svg

hold:
	$(PYTHON) tools/mqtt_hold.py "$(DURATION)" $(if $(DEVICE_ID),--device-id "$(DEVICE_ID)",)

check:
	$(PYTHON) -c 'import ast, pathlib; files = [*pathlib.Path("$(APP_DIR)").rglob("*.py"), *pathlib.Path("tools").glob("*.py"), *pathlib.Path("test_suite").glob("*.py")]; [ast.parse(p.read_text(), filename=str(p)) for p in files]; print("Syntax OK:", len(files), "files")'

test: check
	$(PYTHON) -m unittest discover -s test_suite -v

test-hardware:
	$(PYTHON) tools/test_indicators.py $(TEST_ARGS)

test-hardware-smoke:
	$(PYTHON) tools/test_indicators.py --duration 20 $(TEST_ARGS)


status:
	@test -d "$(CIRCUITPY)" || (echo "CIRCUITPY drive not found at $(CIRCUITPY)"; exit 1)
	@cat "$(CIRCUITPY)/boot_out.txt"

console:
	$(PYTHON) tools/xiao_console.py --wait "$(CONSOLE_WAIT)" $(CONSOLE_ARGS)

deploy: test
	$(PYTHON) tools/deploy.py "$(CIRCUITPY)"
