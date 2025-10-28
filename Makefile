.DEFAULT: help

VENV_DIR := .venv

PYTHON := $(VENV_DIR)/bin/python
PYTHON_VERSION ?= 3.10
PIP := $(VENV_DIR)/bin/pip

.PHONY: help
help:
	@echo 'help         - show help'
	@echo 'bootstrap    - install dependencies required for building the extension'
	@echo 'build        - build project packages'
	@echo 'install      - install the built wheel package'
	@echo 'hooks        - install all git hooks'
	@echo 'tests        - run project tests'
	@echo 'lint         - inspect project source code for problems and errors'
	@echo 'clean        - clean up project environment and all the build artifacts'

.PHONY:
venv: $(VENV_DIR)/bin/activate
$(VENV_DIR)/bin/activate:
	@python3 -m venv $(VENV_DIR)
	@$(PIP) install --upgrade pip setuptools wheel
	@$(PIP) install -r requirements.txt
	@$(PIP) install -r requirements-dev.txt
	@$(PIP) install -r requirements-tests.txt
	@touch $(VENV_DIR)/bin/activate

bootstrap: venv
	@repo init \
		--manifest-branch=master \
		--manifest-name=manifest.xml \
		--manifest-url=https://github.com/vladpunko/pyftpkit.git
	@repo sync

build: bootstrap
	@$(PYTHON) -m build --wheel

install: build
	@$(PYTHON) -m pip install --force-reinstall dist/*.whl

hooks: venv
	@$(PYTHON) -m pre_commit install --config .githooks.yml

tests: bootstrap
	@$(PYTHON) -m tox -e $(PYTHON_VERSION)

lint: bootstrap
	@$(PYTHON) -m tox -e lint

.PHONY: clean
clean:
	git clean -X -d --force
