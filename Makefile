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

zsh java python node golang docker ruby k8s:
	$(play) -t $@

minikube:
	$(play) -t "minikube,kubernetes_tools"

lint:
	mkdir -p log/
	ansible-lint ./roles
