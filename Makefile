.DEFAULT_GOAL := total
.PHONY: init

SHELL := /bin/bash
ENTRY_FILE := entry.yml
play := ansible-playbook $(ENTRY_FILE)

total:
	$(play)

init:
	$(play) -t init

skip-init:
	$(play) --skip-tags init

zsh python node golang docker ruby minikube k8s:
	$(play) -t $@

lint:
	ansible-lint ./roles
