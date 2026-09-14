CIRCUITPY ?= /Volumes/CIRCUITPY
APP_DIR := circuitpython
PYTHON := .venv/bin/python
CONSOLE_WAIT ?= 3
CONSOLE_ARGS ?=
TEST_ARGS ?=
JAVA_BIN ?= /opt/homebrew/opt/openjdk@21/bin

.PHONY: setup check lint precommit-install precommit test test-hardware test-hardware-smoke deploy status console fritzing fritzing-preview hold featherwing-check featherwing-fab

setup:
	uv venv --allow-existing .venv
	uv pip sync --python "$(PYTHON)" tools/requirements-dev.lock

lint:
	uvx --from ruff ruff check circuitpython tools test_suite

precommit-install:
	uvx --from pre-commit pre-commit install

precommit:
	uvx --from pre-commit pre-commit run --all-files

fritzing:
	uv run --cache-dir artifacts/uv-cache tools/make_fritzing.py

fritzing-preview: fritzing
	mkdir -p artifacts/fritzing-mini
	cp docs/xiao-breadboard.fzz artifacts/fritzing-mini/xiao-breadboard.fzz
	/Applications/Fritzing.app/Contents/MacOS/Fritzing -svg artifacts/fritzing-mini > artifacts/fritzing-mini/export.log 2>&1
	cp artifacts/fritzing-mini/xiao-breadboard_breadboard.svg docs/xiao-mini-breadboard.svg

hold:
	$(PYTHON) tools/mqtt_hold.py "$(DURATION)" $(if $(DEVICE_ID),--device-id "$(DEVICE_ID)",)

featherwing-check:
	$(PYTHON) tools/featherwing_fab.py

featherwing-fab: featherwing-check

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

.PHONY: web-setup web-build web-test web-test-unit web-test-browser web-test-emulator web-test-mqtt web-test-live web-deploy web-status web-secrets web-grant web-revoke

web-setup:
	npm ci
	npm --prefix firebase/functions ci
	npx playwright install chromium webkit

web-build:
	npm run build

web-test-unit:
	npm test

web-test-browser:
	npm run test:web

web-test-emulator:
	PATH="$(JAVA_BIN):$(PATH)" npm run test:emulator

web-test: web-test-unit web-test-browser web-test-emulator

web-test-mqtt:
	$(PYTHON) tools/test_web_mqtt.py

web-test-live:
	npm run test:live

web-deploy: web-test
	npm run deploy

web-status:
	$(PYTHON) tools/firebase_cloud.py status

web-secrets:
	$(PYTHON) tools/firebase_cloud.py secrets

web-grant:
	@test -n "$(EMAIL)" || (echo 'Usage: make web-grant EMAIL=user@example.com [DEVICE_ID=b3640c]'; exit 1)
	node_modules/.bin/node firebase/functions/admin.cjs grant "$(EMAIL)" "$(or $(DEVICE_ID),b3640c)"

web-revoke:
	@test -n "$(EMAIL)" || (echo 'Usage: make web-revoke EMAIL=user@example.com [DEVICE_ID=b3640c]'; exit 1)
	node_modules/.bin/node firebase/functions/admin.cjs revoke "$(EMAIL)" "$(or $(DEVICE_ID),b3640c)"

.PHONY: admin-seed ota-bucket-setup ota-enroll ota-provision firmware-build firmware-release firmware-import
admin-seed:
	node_modules/.bin/node tools/firmware_admin.cjs seed-admin

ota-bucket-setup:
	node_modules/.bin/node tools/firmware_admin.cjs bucket-setup

ota-enroll:
	@test -n "$(DEVICE_ID)" || (echo 'Set DEVICE_ID'; exit 1)
	node_modules/.bin/node tools/firmware_admin.cjs enroll "$(DEVICE_ID)"

ota-provision:
	@test -n "$(DEVICE_ID)" || (echo 'Set DEVICE_ID'; exit 1)
	$(PYTHON) tools/ota_provision.py "artifacts/ota/$(DEVICE_ID).env" --board "$(CIRCUITPY)" $(OTA_ARGS)

firmware-build:
	$(PYTHON) tools/firmware_release.py "$(VERSION)"

firmware-release:
	$(PYTHON) tools/firmware_release.py "$(VERSION)" --publish

firmware-import:
	node_modules/.bin/node tools/firmware_admin.cjs import-release "$(VERSION)"
