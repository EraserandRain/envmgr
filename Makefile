.ONESHELL:
.DEFAULT_GOAL := total
.PHONY: init

SHELL := /bin/bash
ENTRY_FILE := entry.yaml
play := ansible-playbook $(ENTRY_FILE)
create_log_dir := (mkdir -p log/ || true)

total: init skip-init

dependency:
	@$(create_log_dir)
	ansible-galaxy install -r requirements.yaml

lint:
	@$(create_log_dir)
	ansible-lint ./roles

init: dependency
	$(play) -t init

skip-init:
	$(play) --skip-tags init

zsh java python node golang docker ruby minikube k8s kubernetes_tools:
	$(play) -t $@
