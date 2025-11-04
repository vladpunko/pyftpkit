.DEFAULT: help

VENV_DIR := .venv

PYTHON := $(VENV_DIR)/bin/python
PYTHON_VERSION ?= 3.10
PIP := $(VENV_DIR)/bin/pip

.PHONY: help
help:
	@echo 'help         - show help'
	@echo 'build        - build project packages'
	@echo 'install      - install the built wheel package'
	@echo 'containers   - build docker images on the current machine'
	@echo 'hooks        - install all git hooks'
	@echo 'tests        - run project tests'
	@echo 'lint         - inspect project source code for problems and errors'
	@echo 'clean        - clean up project environment and all the build artifacts'

.PHONY:
venv: $(VENV_DIR)/bin/activate
$(VENV_DIR)/bin/activate:
	@python3 -m venv $(VENV_DIR)
	@$(PIP) install --upgrade pip setuptools wheel
	@$(PIP) install --group dev --group tests .
	@touch $(VENV_DIR)/bin/activate

build: venv
	@$(PYTHON) -m build

install: build
	@$(PYTHON) -m pip install --force-reinstall dist/*.whl

containers: venv
	@env TAG=$(shell $(PYTHON) -c 'print(__import__("pyftpkit").__version__)') docker buildx bake

hooks: venv
	@$(PYTHON) -m pre_commit install --config .githooks.yml

tests: venv
	@$(PYTHON) -m tox -e $(PYTHON_VERSION)

lint: venv
	@$(PYTHON) -m tox -e lint

.PHONY: clean
clean:
	git clean -X -d --force
